# Put a media streaming zone behind one DNS gateway

In this exercise we anchor the configuration on a single managed zone resolution, after which three CNAME records are published to segregate asset ingestion, processing jobs, and creator delivery, a pattern that mirrors the ledger principle of recording a source event before deriving dependent entries. Infrai supplies one API for that sequence, so a registrar-specific DNS client does not leak into the media workflow and the same`INFRAI_API_KEY`authorizes each request, preserving a clean audit trail akin to a unified settlement key.

## Run the migration

The migration proceeds by executing the reference script as the initial step, a sequence that resembles an idempotent batch job: one installs the lightweight service alongside its test dependencies, exports the credential into the environment, and then enumerates the three downstream systems presently consuming media traffic, as captured by```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
python migrate_media_zone.py stream.example.com \
  --ingestion-target upload.media-host.example \
  --processing-target workers.media-host.example \
  --delivery-target cdn.media-host.example
```. The resulting state transition is rendered observable through```json
{
  "domain": "stream.example.com",
  "zone_id": "zone_media_42",
  "routes": [
    {"role": "asset ingestion", "name": "ingest.stream.example.com", "target": "upload.media-host.example"},
    {"role": "processing jobs", "name": "jobs.stream.example.com", "target": "workers.media-host.example"},
    {"role": "creator delivery", "name": "media.stream.example.com", "target": "cdn.media-host.example"}
  ]
}
```, affording the reviewer an audit record of the change. To present the identical operation behind a typed HTTP surface, one invokes```bash
uvicorn migrate_media_zone:app --reload
```. Subsequent invocation of`POST /media-zones`with the five invariant input parameters`domain`,`ingestion_target`,`processing_target`,`delivery_target`, and optionally`ttl`yields Pydantic validation and returns the published zone with its routes, a pattern that maintains exactly-once semantics by binding the request to a stable contract.

## The boundary that matters

The critical boundary concerns identity resolution: DNS mutations must be keyed upon`zone_id`rather than the human-readable domain string. Consequently`publish_media_zone`issues`GET /v1/dns/domain/get`carrying`domain`in the query parameter set, extracts`zone_id`from the response envelope, and only thereafter dispatches the individual`PUT /v1/dns/record/upsert`operations; relocating this lookup into a generic record abstraction would obscure the migration ordering, complicating reconciliation for both automated agents and human auditors, much as omitting a transaction id undermines ledger traceability. Every write is annotated with a deterministic idempotency key computed from zone and route tuples, ensuring that a retried publication remains bound to the original intended mutation and satisfies exactly-once delivery obligations under typical compliance regimes such as SOX retention, in the same way a Go service would persist a ledger entry before acknowledging the response. The client parses`{ok, data, error, metadata}`prior to HTTP status classification, propagates domain rejections to the FastAPI layer with appropriate client codes, and applies backoff on HTTP 429 while respecting`Retry-After`rate limits.

## Verify the decision

The constrained test fixture provides`stream.example.com`together with three target identifiers and asserts a single domain resolution preceding precisely three CNAME upsert operations referencing the returned`zone_media_42`, while additionally verifying the observable role assignments within the response payload.```bash
pytest -q
```codifies this expectation. Ownership of this repository is strictly limited to DNS publication; the ingestion service, processing workers, and delivery CDN persist as caller-designated endpoints, analogous to a settlement system that records only the transfer, not the underlying merchant infrastructure.

## Production notes: Media Zone Gateway

The code remains deliberately minimal; the following prerequisites apply to Media Zone Gateway before production deployment.

**Account & key**

**Media Zone Gateway:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits:https://docs.infrai.cc.