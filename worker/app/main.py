"""Worker: pulls image jobs from SQS, processes them with OpenCV, writes results to S3.

Ordering per message (not yet implemented):
  1. download source image from S3
  2. process (resize, ...)
  3. write result to S3 under a deterministic key (idempotent on retry)
  4. mark job complete in Postgres
  5. delete the SQS message, only after step 4 succeeds
"""
import os
import time

import boto3

QUEUE_URL = os.environ.get("JOBS_QUEUE_URL", "")
ENDPOINT = os.environ.get("AWS_ENDPOINT_URL") or None
REGION = os.environ.get("AWS_REGION", "us-east-1")


def main() -> None:
    sqs = boto3.client("sqs", region_name=REGION, endpoint_url=ENDPOINT)
    print(f"worker started, polling {QUEUE_URL}", flush=True)
    while True:
        resp = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=1, WaitTimeSeconds=20)
        for msg in resp.get("Messages", []):
            print(f"received message {msg['MessageId']} (processing not implemented yet)", flush=True)
        if not resp.get("Messages"):
            time.sleep(1)


if __name__ == "__main__":
    main()
