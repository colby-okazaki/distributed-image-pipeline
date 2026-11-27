"""Worker: pulls image jobs from SQS, processes them with OpenCV and writes results to S3.

Per message, in this order:
  1. claim the job in Postgres (skip it if it is already finished)
  2. download the source image from S3
  3. process it
  4. write the result to S3 under the job's fixed result key
  5. mark the job done in Postgres
  6. delete the SQS message

The message is deleted only after step 5 succeeds. If the worker dies at any point
before that, SQS redelivers the message once its visibility timeout expires and
another worker repeats the job. That is safe because the result key is fixed and
processing is deterministic: a repeat overwrites the same object with the same bytes,
so a crash between steps 4 and 5 cannot lose or duplicate a result.
"""
import json
import logging
import os
import signal
import threading
import time
from dataclasses import dataclass

import boto3
import psycopg
from botocore.exceptions import BotoCoreError, ClientError
from psycopg.rows import dict_row

from . import config, processing
from .processing import PermanentError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker: %(message)s")
log = logging.getLogger("worker")

s3 = boto3.client("s3", region_name=config.AWS_REGION, endpoint_url=config.AWS_ENDPOINT_URL)
sqs = boto3.client("sqs", region_name=config.AWS_REGION, endpoint_url=config.AWS_ENDPOINT_URL)

CONTENT_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
FINISHED = ("done", "failed", "upload_missing")


@dataclass
class Job:
    job_id: str
    source_key: str
    result_key: str
    operation: str
    params: dict


class Database:
    """One autocommit connection, reopened if it breaks (e.g. Postgres restarted)."""

    def __init__(self, url: str):
        self.url = url
        self.conn: psycopg.Connection | None = None

    def execute(self, sql: str, args: tuple) -> dict | None:
        if self.conn is None or self.conn.closed:
            self.conn = psycopg.connect(self.url, autocommit=True, row_factory=dict_row, connect_timeout=5)
        try:
            return self.conn.execute(sql, args).fetchone()
        except psycopg.OperationalError:
            self.conn.close()
            self.conn = None
            raise


db = Database(config.DATABASE_URL)


class VisibilityHeartbeat:
    """Keeps a message invisible to other workers while a long job runs."""

    def __init__(self, receipt_handle: str):
        self.receipt_handle = receipt_handle
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(config.HEARTBEAT_INTERVAL):
            try:
                sqs.change_message_visibility(QueueUrl=config.JOBS_QUEUE_URL,
                                              ReceiptHandle=self.receipt_handle,
                                              VisibilityTimeout=config.VISIBILITY_TIMEOUT)
            except (BotoCoreError, ClientError) as e:
                log.warning("heartbeat failed: %s", e)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()


def parse(body: str) -> Job:
    try:
        m = json.loads(body)
        return Job(m["job_id"], m["source_key"], m["result_key"], m["operation"], m.get("params") or {})
    except (ValueError, KeyError, TypeError) as e:
        raise PermanentError(f"malformed message: {e}") from e


def claim(job: Job) -> bool:
    """Mark the job as processing. Returns False if it is finished or unknown (nothing to do)."""
    row = db.execute(
        "UPDATE jobs SET status = 'processing', attempts = attempts + 1, updated_at = now()"
        " WHERE id = %s AND status NOT IN ('done', 'failed', 'upload_missing') RETURNING id",
        (job.job_id,),
    )
    if row is not None:
        return True
    existing = db.execute("SELECT status FROM jobs WHERE id = %s", (job.job_id,))
    log.info("job %s skipped: %s", job.job_id, existing["status"] if existing else "not in database")
    return False


def process(job: Job) -> None:
    try:
        source = s3.get_object(Bucket=config.UPLOAD_BUCKET, Key=job.source_key)["Body"].read()
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            raise PermanentError("source image not found in S3") from e
        raise

    ext = os.path.splitext(job.result_key)[1].lower()
    result = processing.run(job.operation, job.params, source, ext)

    s3.put_object(Bucket=config.RESULTS_BUCKET, Key=job.result_key, Body=result,
                  ContentType=CONTENT_TYPES.get(ext, "application/octet-stream"))
    db.execute(
        "UPDATE jobs SET status = 'done', error = NULL, completed_at = now(), updated_at = now()"
        " WHERE id = %s RETURNING id",
        (job.job_id,),
    )


def mark_failed(job_id: str, error: str) -> None:
    db.execute(
        "UPDATE jobs SET status = 'failed', error = %s, updated_at = now() WHERE id = %s RETURNING id",
        (error[:1000], job_id),
    )


def delete(msg: dict) -> None:
    sqs.delete_message(QueueUrl=config.JOBS_QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])


def handle(msg: dict) -> None:
    receives = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
    job = None
    try:
        job = parse(msg["Body"])
        if claim(job):
            started = time.monotonic()
            with VisibilityHeartbeat(msg["ReceiptHandle"]):
                process(job)
            log.info("job %s done in %.0f ms (attempt %d)", job.job_id, (time.monotonic() - started) * 1000, receives)
        delete(msg)

    except PermanentError as e:
        # Retrying cannot help: record the failure and drop the message.
        log.warning("job %s failed permanently: %s", job.job_id if job else "?", e)
        if job:
            mark_failed(job.job_id, str(e))
            delete(msg)
        # A malformed message has no job to update; leave it so SQS moves it to the DLQ.

    except Exception as e:  # transient: S3, SQS or Postgres unavailable, etc.
        log.warning("job %s attempt %d/%d failed: %r", job.job_id if job else "?", receives, config.MAX_RECEIVES, e)
        if receives >= config.MAX_RECEIVES:
            # Last attempt: record it now, because the next receive moves the message to the DLQ.
            if job:
                try:
                    mark_failed(job.job_id, f"gave up after {receives} attempts: {e!r}")
                except Exception as db_err:
                    log.error("could not mark job %s failed: %r", job.job_id, db_err)
        else:
            # Retry sooner than the full visibility timeout, with exponential backoff.
            delay = min(config.RETRY_BASE_DELAY * 2 ** (receives - 1), config.VISIBILITY_TIMEOUT)
            try:
                sqs.change_message_visibility(QueueUrl=config.JOBS_QUEUE_URL,
                                              ReceiptHandle=msg["ReceiptHandle"], VisibilityTimeout=delay)
            except (BotoCoreError, ClientError):
                pass  # the normal visibility timeout still applies


def main() -> None:
    stopping = threading.Event()

    def on_signal(signum, _frame):
        log.info("received signal %d, finishing current job then exiting", signum)
        stopping.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    log.info("started, polling %s", config.JOBS_QUEUE_URL)
    while not stopping.is_set():
        try:
            resp = sqs.receive_message(QueueUrl=config.JOBS_QUEUE_URL, MaxNumberOfMessages=1,
                                       WaitTimeSeconds=10, AttributeNames=["ApproximateReceiveCount"])
        except (BotoCoreError, ClientError) as e:
            log.warning("receive failed: %s", e)
            time.sleep(2)
            continue
        for msg in resp.get("Messages", []):
            try:
                handle(msg)
            except Exception as e:
                # e.g. Postgres down while recording a failure. The message was not deleted,
                # so SQS will redeliver it; keep the worker alive.
                log.error("unhandled error for message %s: %r", msg.get("MessageId"), e)
    log.info("stopped")


if __name__ == "__main__":
    main()
