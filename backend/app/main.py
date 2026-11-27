import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from psycopg.types.json import Jsonb

from . import aws, cache
from .config import settings
from .db import pool
from .schemas import (
    ALLOWED_CONTENT_TYPES,
    BatchResults,
    BatchStatus,
    CreateBatchRequest,
    CreateBatchResponse,
    ResultLink,
    UploadTarget,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    pool.open(wait=True, timeout=30)
    yield
    pool.close()


app = FastAPI(title="Distributed Image Pipeline API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/batches", response_model=CreateBatchResponse, status_code=201)
def create_batch(req: CreateBatchRequest) -> CreateBatchResponse:
    """Create a batch and one job per file, and return a presigned S3 PUT URL for each.

    Image bytes go straight from the client to S3; they never pass through this API.
    """
    if len(req.files) > settings.max_files_per_batch:
        raise HTTPException(422, f"at most {settings.max_files_per_batch} files per batch")
    bad = sorted({f.content_type for f in req.files} - ALLOWED_CONTENT_TYPES.keys())
    if bad:
        raise HTTPException(422, f"unsupported content types: {bad}; allowed: {sorted(ALLOWED_CONTENT_TYPES)}")

    batch_id = uuid.uuid4()
    rows, uploads = [], []
    for f in req.files:
        job_id = uuid.uuid4()
        ext = ALLOWED_CONTENT_TYPES[f.content_type]
        # Keys are derived from IDs, never from the user's filename.
        source_key = f"uploads/{batch_id}/{job_id}{ext}"
        result_key = f"results/{batch_id}/{job_id}{ext}"
        rows.append((job_id, batch_id, f.filename, f.content_type, source_key, result_key))
        uploads.append(UploadTarget(
            job_id=job_id,
            filename=f.filename,
            content_type=f.content_type,
            upload_url=aws.presign_upload(source_key, f.content_type),
        ))

    with pool.connection() as conn, conn.transaction():
        conn.execute(
            "INSERT INTO batches (id, operation, params) VALUES (%s, %s, %s)",
            (batch_id, req.operation, Jsonb(req.params.model_dump())),
        )
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO jobs (id, batch_id, filename, content_type, source_key, result_key)"
                " VALUES (%s, %s, %s, %s, %s, %s)",
                rows,
            )

    return CreateBatchResponse(batch_id=batch_id, expires_in=settings.presign_expiry_seconds, uploads=uploads)


@app.post("/batches/{batch_id}/confirm", response_model=BatchStatus)
def confirm_batch(batch_id: UUID) -> BatchStatus:
    """Mark uploads complete: verify each object is in S3, queue those jobs, publish one SQS message each.

    Safe to call more than once: a batch that is already queued is returned as is.
    """
    with pool.connection() as conn, conn.transaction():
        batch = conn.execute(
            "SELECT id, operation, params, status FROM batches WHERE id = %s FOR UPDATE", (batch_id,)
        ).fetchone()
        if batch is None:
            raise HTTPException(404, "batch not found")

        if batch["status"] == "awaiting_upload":
            jobs = conn.execute(
                "SELECT id, source_key, result_key FROM jobs WHERE batch_id = %s", (batch_id,)
            ).fetchall()
            with ThreadPoolExecutor(max_workers=16) as ex:
                present = list(ex.map(lambda j: aws.upload_exists(j["source_key"]), jobs))

            uploaded = [j for j, ok in zip(jobs, present) if ok]
            missing = [j["id"] for j, ok in zip(jobs, present) if not ok]
            if not uploaded:
                raise HTTPException(409, "no uploaded files found for this batch")

            conn.execute(
                "UPDATE jobs SET status = 'queued', updated_at = now() WHERE id = ANY(%s)",
                ([j["id"] for j in uploaded],),
            )
            if missing:
                conn.execute(
                    "UPDATE jobs SET status = 'upload_missing', error = 'file was not uploaded',"
                    " updated_at = now() WHERE id = ANY(%s)",
                    (missing,),
                )
            conn.execute(
                "UPDATE batches SET status = 'queued', queued_at = now() WHERE id = %s", (batch_id,)
            )
            # Publish before commit: if SQS fails the transaction rolls back and the client can retry.
            # A partial publish followed by a retry can send a job twice; the worker is idempotent.
            aws.publish_jobs(
                {
                    "job_id": str(j["id"]),
                    "batch_id": str(batch_id),
                    "source_key": j["source_key"],
                    "result_key": j["result_key"],
                    "operation": batch["operation"],
                    "params": batch["params"],
                }
                for j in uploaded
            )
            log.info("batch %s queued: %d jobs, %d missing", batch_id, len(uploaded), len(missing))

    cache.invalidate(str(batch_id))
    return _load_status(batch_id)


@app.get("/batches/{batch_id}", response_model=BatchStatus)
def get_batch(batch_id: UUID) -> BatchStatus:
    cached = cache.get_status(str(batch_id))
    if cached is not None:
        return BatchStatus.model_validate(cached)
    status = _load_status(batch_id)
    cache.set_status(str(batch_id), status.model_dump(mode="json"))
    return status


@app.get("/batches/{batch_id}/results", response_model=BatchResults)
def get_batch_results(batch_id: UUID) -> BatchResults:
    with pool.connection() as conn:
        if conn.execute("SELECT 1 FROM batches WHERE id = %s", (batch_id,)).fetchone() is None:
            raise HTTPException(404, "batch not found")
        jobs = conn.execute(
            "SELECT id, filename, result_key FROM jobs WHERE batch_id = %s AND status = 'done' ORDER BY filename",
            (batch_id,),
        ).fetchall()
    return BatchResults(
        batch_id=batch_id,
        expires_in=settings.presign_expiry_seconds,
        results=[
            ResultLink(job_id=j["id"], filename=j["filename"],
                       download_url=aws.presign_download(j["result_key"], _result_filename(j)))
            for j in jobs
        ],
    )


@app.get("/jobs/{job_id}/result", response_model=ResultLink)
def get_job_result(job_id: UUID) -> ResultLink:
    with pool.connection() as conn:
        job = conn.execute(
            "SELECT id, filename, status, result_key FROM jobs WHERE id = %s", (job_id,)
        ).fetchone()
    if job is None:
        raise HTTPException(404, "job not found")
    if job["status"] != "done":
        raise HTTPException(409, f"job is not done (status: {job['status']})")
    return ResultLink(job_id=job["id"], filename=job["filename"],
                      download_url=aws.presign_download(job["result_key"], _result_filename(job)))


def _result_filename(job: dict) -> str:
    stem, _ = os.path.splitext(job["filename"])
    _, ext = os.path.splitext(job["result_key"])
    return f"{stem}-processed{ext}".replace('"', "")


def _load_status(batch_id: UUID) -> BatchStatus:
    with pool.connection() as conn:
        batch = conn.execute(
            "SELECT id, operation, status, created_at, queued_at FROM batches WHERE id = %s", (batch_id,)
        ).fetchone()
        if batch is None:
            raise HTTPException(404, "batch not found")
        jobs = conn.execute(
            "SELECT id, filename, status, attempts, error, updated_at FROM jobs"
            " WHERE batch_id = %s ORDER BY filename, id",
            (batch_id,),
        ).fetchall()

    counts: dict[str, int] = {}
    for j in jobs:
        counts[j["status"]] = counts.get(j["status"], 0) + 1

    failed = counts.get("failed", 0) + counts.get("upload_missing", 0)
    finished = counts.get("done", 0) + failed
    if batch["status"] == "awaiting_upload":
        overall = "awaiting_upload"
    elif finished < len(jobs):
        overall = "processing"
    elif failed == 0:
        overall = "done"
    elif failed == len(jobs):
        overall = "failed"
    else:
        overall = "partial_failure"

    return BatchStatus(
        batch_id=batch["id"],
        status=overall,
        operation=batch["operation"],
        total=len(jobs),
        counts=counts,
        created_at=batch["created_at"],
        queued_at=batch["queued_at"],
        jobs=jobs,
    )
