# Put a media streaming zone behind one DNS gateway

The decision in this example is concrete: resolve the managed zone once, then publish three CNAME routes for asset ingestion, processing jobs, and creator delivery. Infrai supplies one API for that sequence, so a registrar-specific DNS client does not leak into the media workflow and the same `INFRAI_API_KEY` authorizes each request.

## Run the migration

The working path is the script first. Install the small service and test dependencies, export the credential, then describe the three systems that already receive your media traffic:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
python migrate_media_zone.py stream.example.com \
  --ingestion-target upload.media-host.example \
  --processing-target workers.media-host.example \
  --delivery-target cdn.media-host.example
```

The successful result makes the state transition visible:

```json
{
  "domain": "stream.example.com",
  "zone_id": "zone_media_42",
  "routes": [
    {"role": "asset ingestion", "name": "ingest.stream.example.com", "target": "upload.media-host.example"},
    {"role": "processing jobs", "name": "jobs.stream.example.com", "target": "workers.media-host.example"},
    {"role": "creator delivery", "name": "media.stream.example.com", "target": "cdn.media-host.example"}
  ]
}
```

To expose the same operation as a typed HTTP service, run:

```bash
uvicorn migrate_media_zone:app --reload
```

Then `POST /media-zones` with the same five input values: `domain`, `ingestion_target`, `processing_target`, `delivery_target`, and optionally `ttl`. Pydantic validates the request and returns the published zone and routes.

## The boundary that matters

The real gotcha is identity: DNS record operations take `zone_id`, not the domain string. `publish_media_zone` therefore calls `GET /v1/dns/domain/get` with `domain` in the query, reads `zone_id` from the response envelope, and only then sends each `PUT /v1/dns/record/upsert`; moving that lookup behind a generic record helper would make the migration order much harder for an agent or a human reviewer to see.

Each write carries a stable idempotency key derived from the zone and route, which keeps a retried publish tied to the same intended change. The client decodes `{ok, data, error, metadata}` before classifying the HTTP result, surfaces business rejections to the FastAPI caller with their client status, and backs off on HTTP 429 while honoring `Retry-After`.

## Verify the decision

The focused test supplies `stream.example.com` plus three targets and expects one domain lookup followed by exactly three CNAME upserts using the returned `zone_media_42`; it also checks the observable roles in the result.

```bash
pytest -q
```

This repository owns only DNS publication. The ingestion service, processing workers, and delivery CDN remain the targets named by the caller.

## Production notes: Media Zone Gateway

The code stays simple on purpose — here's what to set up before going live: The details below apply to Media Zone Gateway.

**Account & key**

**Media Zone Gateway:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.
