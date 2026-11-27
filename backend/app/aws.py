import json
from collections.abc import Iterable

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import settings

_s3_config = Config(signature_version="s3v4", s3={"addressing_style": "path"})

s3 = boto3.client("s3", region_name=settings.aws_region,
                  endpoint_url=settings.aws_endpoint_url, config=_s3_config)
# Separate client for presigning so URLs point at an endpoint the browser can reach.
s3_presign = boto3.client("s3", region_name=settings.aws_region,
                          endpoint_url=settings.aws_public_endpoint_url or settings.aws_endpoint_url,
                          config=_s3_config)
sqs = boto3.client("sqs", region_name=settings.aws_region, endpoint_url=settings.aws_endpoint_url)


def presign_upload(key: str, content_type: str) -> str:
    return s3_presign.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.upload_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=settings.presign_expiry_seconds,
    )


def presign_download(key: str, filename: str) -> str:
    return s3_presign.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.results_bucket,
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
        },
        ExpiresIn=settings.presign_expiry_seconds,
    )


def upload_exists(key: str) -> bool:
    try:
        s3.head_object(Bucket=settings.upload_bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def publish_jobs(messages: Iterable[dict]) -> None:
    """Send one SQS message per job, in batches of 10 (the SQS maximum)."""
    messages = list(messages)
    for i in range(0, len(messages), 10):
        chunk = messages[i:i + 10]
        resp = sqs.send_message_batch(
            QueueUrl=settings.jobs_queue_url,
            Entries=[{"Id": str(n), "MessageBody": json.dumps(m)} for n, m in enumerate(chunk)],
        )
        if resp.get("Failed"):
            raise RuntimeError(f"SQS rejected {len(resp['Failed'])} messages: {resp['Failed']}")
