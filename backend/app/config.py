from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://pipeline:pipeline@localhost:5432/pipeline"
    redis_url: str = "redis://localhost:6379/0"
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None  # set to LocalStack in dev, unset on real AWS
    upload_bucket: str = "pipeline-uploads"
    results_bucket: str = "pipeline-results"
    jobs_queue_url: str = ""


settings = Settings()
