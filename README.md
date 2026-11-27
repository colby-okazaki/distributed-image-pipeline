# Distributed Image Processing Pipeline

A batch image-processing system: users upload a batch of images, each image becomes an independent job on a queue, and a pool of workers processes them with OpenCV and writes results back to object storage. The focus is on reliability: no lost or duplicated results when workers crash mid-batch.

> Status: early scaffold. The services start, but the endpoints and processing logic are still being built. See [TODO.md](TODO.md).

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

## Project layout

```
backend/    FastAPI service
worker/     SQS consumer and OpenCV processing
frontend/   React + Vite UI
infra/      PostgreSQL schema and LocalStack init script
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

LocalStack creates the S3 buckets and the SQS queue plus dead-letter queue on startup, so local development costs nothing on AWS.
