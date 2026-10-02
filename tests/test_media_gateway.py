import json

import httpx

from media_gateway import InfraiDnsClient, MediaZoneRequest, publish_media_zone


def test_media_workflow_resolves_zone_before_upserting_routes() -> None:
    observed: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        observed.append(
            {
                "method": request.method,
                "path": request.url.path,
                "query": dict(request.url.params),
                "body": body,
                "idempotency_key": request.headers.get("Idempotency-Key"),
            }
        )
        if request.url.path == "/v1/dns/domain/get":
            return httpx.Response(200, json={"ok": True, "data": {"zone_id": "zone_media_42"}})
        return httpx.Response(200, json={"ok": True, "data": {"record_id": "record_1"}})

    client = InfraiDnsClient("test-key", transport=httpx.MockTransport(handler))
    try:
        result = publish_media_zone(
            client,
            MediaZoneRequest(
                domain="stream.example.com",
                ingestion_target="upload.media-host.example",
                processing_target="workers.media-host.example",
                delivery_target="cdn.media-host.example",
            ),
        )
    finally:
        client.close()

    assert observed[0] == {
        "method": "GET",
        "path": "/v1/dns/domain/get",
        "query": {"domain": "stream.example.com"},
        "body": None,
        "idempotency_key": None,
    }
    writes = observed[1:]
    assert [call["method"] for call in writes] == ["PUT", "PUT", "PUT"]
    assert [call["body"]["name"] for call in writes] == [
        "ingest.stream.example.com",
        "jobs.stream.example.com",
        "media.stream.example.com",
    ]
    assert all(call["body"]["zone_id"] == "zone_media_42" for call in writes)
    assert all(call["body"]["record_type"] == "CNAME" for call in writes)
    assert all(call["idempotency_key"] for call in writes)
    assert result.zone_id == "zone_media_42"
    assert [route.role for route in result.routes] == [
        "asset ingestion",
        "processing jobs",
        "creator delivery",
    ]
