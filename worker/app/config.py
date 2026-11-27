import os


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://pipeline:pipeline@localhost:5434/pipeline")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL") or None
UPLOAD_BUCKET = os.environ.get("UPLOAD_BUCKET", "pipeline-uploads")
RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET", "pipeline-results")
JOBS_QUEUE_URL = os.environ.get("JOBS_QUEUE_URL", "")

# Must match the queue's VisibilityTimeout. While a job runs, a heartbeat keeps
# extending visibility so a slow job is not redelivered to another worker.
VISIBILITY_TIMEOUT = _int("VISIBILITY_TIMEOUT", 60)
HEARTBEAT_INTERVAL = _int("HEARTBEAT_INTERVAL", 20)
# Must match the queue's RedrivePolicy maxReceiveCount. On the last attempt a
# failing job is marked failed in Postgres before SQS moves it to the DLQ.
MAX_RECEIVES = _int("MAX_RECEIVES", 3)
RETRY_BASE_DELAY = _int("RETRY_BASE_DELAY", 5)  # seconds; doubled on each attempt
