from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Distributed Image Pipeline API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Planned endpoints:
#   POST /batches                      create upload session, return presigned S3 PUT URLs
#   POST /batches/{batch_id}/confirm   record jobs in Postgres, publish one SQS message per image
#   GET  /batches/{batch_id}           batch + job status (Postgres, Redis cache in front)
#   GET  /jobs/{job_id}/result         presigned GET URL for the processed image
