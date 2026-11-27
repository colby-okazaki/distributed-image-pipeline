# Distributed Image Processing Pipeline — Todo List

## Setup / Local Dev
- [ ] Scaffold FastAPI backend project structure
- [ ] Scaffold React frontend project structure
- [ ] Set up Docker Compose for local dev
- [ ] Set up LocalStack to simulate S3 + SQS locally (avoid AWS cost during dev)
- [ ] Design PostgreSQL schema: jobs, batch items, status, timestamps, result locations

## Backend — Core API
- [ ] POST endpoint: create upload session for a batch
- [ ] Generate presigned S3 upload URLs (do NOT proxy image bytes through FastAPI)
- [ ] POST endpoint: confirm uploads completed, create job + batch-item records in PostgreSQL
- [ ] Publish one SQS message per image job
- [ ] GET endpoint: job/batch status (reads from PostgreSQL, Redis as cache in front)
- [ ] GET endpoint: fetch/download processed results

## Worker
- [ ] Build worker process that pulls jobs from SQS
- [ ] Implement first OpenCV operation (e.g., resize)
- [ ] Implement second OpenCV operation (e.g., face/object detection) — optional/stretch
- [ ] Write processed results back to S3
- [ ] Update job status in PostgreSQL AFTER successful S3 result write
- [ ] Delete/ack SQS message ONLY AFTER PostgreSQL update succeeds (strict ordering: S3 → Postgres → SQS ack)
- [ ] Containerize worker with Docker

## Reliability
- [ ] Add retry logic for failed jobs
- [ ] Configure SQS visibility timeout correctly
- [ ] Add dead-letter queue for jobs that repeatedly fail
- [ ] Make processing idempotent (safe to reprocess without corrupting/duplicating results)
- [ ] Add Redis caching for job-status lookups — cache only, PostgreSQL must remain correct source of truth if Redis is down/cleared

## Frontend
- [ ] Build upload UI (request presigned URLs, upload batch directly to S3)
- [ ] Build live job/batch progress view (polling status endpoint)
- [ ] Build results gallery/download view
- [ ] Basic error states (failed job, partial batch failure)

## AWS Deployment (real, not LocalStack)
- [ ] Create real S3 bucket
- [ ] Create real SQS queue (+ dead-letter queue)
- [ ] Set up AWS Budget alert (e.g., $5 threshold) before deploying anything real
- [ ] Launch single free-tier EC2 instance (t2.micro/t3.micro)
- [ ] Deploy API + worker containers on EC2 via Docker
- [ ] Point frontend at deployed API, verify end-to-end on real AWS
- [ ] Confirm nothing is left running 24/7 unintentionally after testing

## Testing / Chaos Test
- [ ] Run a real batch (e.g., several hundred images) end-to-end
- [ ] Chaos test: kill worker(s) mid-batch generally, verify no lost/duplicated results
- [ ] Specifically test crash BETWEEN S3 result write and PostgreSQL update (the race condition flagged in review) — confirm it's handled correctly
- [ ] Record exact numbers from chaos test (crashes, retries, jobs lost/duplicated) for resume bullet
- [ ] Measure throughput (images processed per minute/second)

## Polish / Wrap-up
- [ ] Write README (architecture, how to run locally, how it's deployed)
- [ ] Record short demo video/gif as backup
- [ ] Write final 3 resume bullets using real measured numbers
- [ ] Tear down / stop AWS resources if not actively demoing
