# Distributed Image Processing Pipeline

A batch image-processing system: users upload a batch of images, each image becomes an independent job on a queue, and a pool of workers processes them with OpenCV and writes results back to object storage. The focus is on reliability: no lost or duplicated results when workers crash mid-batch.

> Status: the API is implemented. The worker's image processing and the frontend are still being built. See [TODO.md](TODO.md).

## Tech stack

| Layer | Technology |
|---|---|
| API | Python, FastAPI |
| Workers | Python, OpenCV |
| Queue | AWS SQS (with a dead-letter queue) |
| Object storage | AWS S3 (presigned uploads and downloads) |
| Database | PostgreSQL (source of truth for job state) |
| Cache | Redis (job-status lookups only) |
| Frontend | React, Vite |
| Local dev | Docker Compose, LocalStack (S3 and SQS) |
| Deployment | Docker on a single AWS EC2 instance |

## Architecture

```
React UI ──► FastAPI ──► PostgreSQL (jobs, batches)
   │            │  └──► Redis (status cache)
   │            └──► SQS: one message per image
   │                      │
   └── presigned PUT ──► S3 (uploads) ◄── Worker(s) ──► S3 (results)
```

1. The client asks the API for a batch and receives presigned S3 upload URLs. Image bytes go straight to S3, never through the API.
2. The client confirms the upload. The API records the batch and its jobs in PostgreSQL and publishes one SQS message per image.
3. Workers pull messages, process the image, and for each job follow a strict order: **write the result to S3 → update PostgreSQL → delete the SQS message**. A crash at any step leaves the message to be redelivered, and processing is idempotent, so retries are safe.
4. Jobs that keep failing move to the dead-letter queue.
5. The UI polls the status endpoint and shows results when the batch is done.

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/batches` | Create a batch. Body: `files` (filename + content type), `operation`, `params`. Returns one presigned S3 PUT URL per file. |
| `POST` | `/batches/{id}/confirm` | Call after uploading. Checks each file is in S3, queues the uploaded ones (one SQS message each) and marks the rest `upload_missing`. Safe to call twice. |
| `GET` | `/batches/{id}` | Batch status, counts per job status, and per-job detail. Cached in Redis for 2 seconds; falls back to PostgreSQL when Redis is unavailable. |
| `GET` | `/batches/{id}/results` | Presigned download URLs for every finished job. |
| `GET` | `/jobs/{id}/result` | Presigned download URL for one job (409 until it is done). |
| `GET` | `/health` | Health check. |

Accepted image types: JPEG, PNG, WebP. Up to 500 files per batch. S3 keys are built from batch and job IDs, never from user filenames, and each job's result key is fixed up front so a retried job overwrites its result instead of duplicating it.

Batch status is derived from its jobs: `awaiting_upload` → `processing` → `done`, `partial_failure` or `failed`.

## Project layout

```
backend/    FastAPI service
worker/     SQS consumer and OpenCV processing
frontend/   React + Vite UI
infra/      PostgreSQL schema and LocalStack init script
scripts/    smoke tests
docker-compose.yml
```

## Running locally

Requires Docker and Node.js.

```bash
docker compose up --build        # Postgres, Redis, LocalStack, API, worker
cd frontend && npm install && npm run dev
```

- API: http://localhost:8000 (health check at `/health`, docs at `/docs`)
- UI: http://localhost:5173

LocalStack creates the S3 buckets (with CORS for browser uploads) and the SQS queue plus dead-letter queue on startup, so local development costs nothing on AWS.

On the host, Postgres listens on port 5434 and Redis on 6380, to avoid clashing with other local projects. Override with `POSTGRES_HOST_PORT` and `REDIS_HOST_PORT`.

API smoke test (standard library only):

```bash
docker compose up -d --wait postgres redis localstack api
python3 scripts/smoke_test_api.py
```
