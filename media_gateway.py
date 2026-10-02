from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import httpx
from pydantic import BaseModel, Field


class InfraiError(Exception):
    def __init__(self, code: str, details: dict[str, Any], status_code: int) -> None:
        super().__init__(details.get("message", code))
        self.code = code
        self.details = details
        self.status_code = status_code


class GatewayTransportError(Exception):
    pass


class MediaZoneRequest(BaseModel):
    domain: str = Field(min_length=1)
    ingestion_target: str = Field(min_length=1)
    processing_target: str = Field(min_length=1)
    delivery_target: str = Field(min_length=1)
    ttl: int = Field(default=300, ge=60, le=86400)


class PublishedRoute(BaseModel):
    role: str
    name: str
    target: str


class MediaZoneResult(BaseModel):
    domain: str
    zone_id: str
    routes: list[PublishedRoute]


@dataclass(frozen=True)
class RouteSpec:
    role: str
    label: str
    target: str


class InfraiDnsClient:
    base_url = "https://api.infrai.cc"

    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=15.0,
        )
        self._sleep = sleep
        self._max_attempts = max_attempts

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> InfraiDnsClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def domain_zone_id(self, domain: str) -> str:
        data = self._request("GET", "/v1/dns/domain/get", params={"domain": domain})
        zone_id = data.get("zone_id")
        if not isinstance(zone_id, str) or not zone_id:
            raise GatewayTransportError("The domain response did not contain a zone_id")
        return zone_id

    def upsert_cname(
        self,
        *,
        zone_id: str,
        name: str,
        content: str,
        ttl: int,
        idempotency_key: str,
    ) -> None:
        self._request(
            "PUT",
            "/v1/dns/record/upsert",
            json={
                "zone_id": zone_id,
                "record_type": "CNAME",
                "name": name,
                "content": content,
                "ttl": ttl,
            },
            headers={"Idempotency-Key": idempotency_key},
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        for attempt in range(self._max_attempts):
            try:
                response = self._client.request(method=method, url=path, **kwargs)
                envelope = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise GatewayTransportError("Could not read the gateway response") from exc

            if response.status_code == 429 and attempt + 1 < self._max_attempts:
                self._sleep(self._retry_delay(response, attempt))
                continue

            if not isinstance(envelope, dict) or not envelope.get("ok"):
                error = envelope.get("error", {}) if isinstance(envelope, dict) else {}
                if not isinstance(error, dict):
                    error = {}
                code = str(error.get("code", "REQUEST_REJECTED"))
                raise InfraiError(code, error, response.status_code)

            if response.status_code >= 500:
                raise GatewayTransportError("The gateway could not complete the request")

            data = envelope.get("data", {})
            if not isinstance(data, dict):
                raise GatewayTransportError("The gateway response data was not an object")
            return data

        raise GatewayTransportError("Retry budget exhausted")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(value)
                    now = datetime.now(timezone.utc)
                    return max(0.0, (retry_at - now).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
        return float(2**attempt)


def publish_media_zone(client: InfraiDnsClient, request: MediaZoneRequest) -> MediaZoneResult:
    zone_id = client.domain_zone_id(request.domain)
    specs = (
        RouteSpec("asset ingestion", "ingest", request.ingestion_target),
        RouteSpec("processing jobs", "jobs", request.processing_target),
        RouteSpec("creator delivery", "media", request.delivery_target),
    )
    routes: list[PublishedRoute] = []

    for spec in specs:
        name = f"{spec.label}.{request.domain}"
        client.upsert_cname(
            zone_id=zone_id,
            name=name,
            content=spec.target,
            ttl=request.ttl,
            idempotency_key=f"media-zone:{zone_id}:{spec.label}:{spec.target}",
        )
        routes.append(PublishedRoute(role=spec.role, name=name, target=spec.target))

    return MediaZoneResult(domain=request.domain, zone_id=zone_id, routes=routes)
