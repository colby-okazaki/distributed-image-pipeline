from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://pipeline:pipeline@localhost:5432/pipeline"
    redis_url: str = "redis://localhost:6379/0"

    aws_region: str = "us-east-1"
    # Endpoint the API uses to talk to S3/SQS. LocalStack in dev, unset on real AWS.
    aws_endpoint_url: str | None = None
    # Endpoint baked into presigned URLs, which the browser must be able to reach.
    # In Docker the API reaches LocalStack at http://localstack:4566 but the browser needs localhost.
    aws_public_endpoint_url: str | None = None

    upload_bucket: str = "pipeline-uploads"
    results_bucket: str = "pipeline-results"
    jobs_queue_url: str = ""

    presign_expiry_seconds: int = 900
    max_files_per_batch: int = 500
    status_cache_ttl_seconds: int = 2
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
