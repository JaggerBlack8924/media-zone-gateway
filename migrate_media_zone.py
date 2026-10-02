from __future__ import annotations

import argparse
import json
import os

from fastapi import FastAPI, HTTPException

from media_gateway import (
    GatewayTransportError,
    InfraiDnsClient,
    InfraiError,
    MediaZoneRequest,
    MediaZoneResult,
    publish_media_zone,
)


app = FastAPI(title="Media streaming DNS gateway")


def require_api_key() -> str:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set INFRAI_API_KEY before publishing a media zone")
    return api_key


@app.post("/media-zones", response_model=MediaZoneResult)
def create_media_zone(request: MediaZoneRequest) -> MediaZoneResult:
    try:
        with InfraiDnsClient(require_api_key()) as client:
            return publish_media_zone(client, request)
    except InfraiError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except GatewayTransportError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish DNS routes for a media streaming zone")
    parser.add_argument("domain")
    parser.add_argument("--ingestion-target", required=True)
    parser.add_argument("--processing-target", required=True)
    parser.add_argument("--delivery-target", required=True)
    parser.add_argument("--ttl", type=int, default=300)
    args = parser.parse_args()
    request = MediaZoneRequest(
        domain=args.domain,
        ingestion_target=args.ingestion_target,
        processing_target=args.processing_target,
        delivery_target=args.delivery_target,
        ttl=args.ttl,
    )
    with InfraiDnsClient(require_api_key()) as client:
        result = publish_media_zone(client, request)
    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    main()
