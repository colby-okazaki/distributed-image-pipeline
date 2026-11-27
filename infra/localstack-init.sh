#!/bin/sh
# Runs inside LocalStack once it is ready: creates the buckets and queues for local dev.
set -e
awslocal s3 mb s3://pipeline-uploads
awslocal s3 mb s3://pipeline-results

# Browsers upload and download directly with presigned URLs, so the buckets need CORS.
CORS='{"CORSRules":[{"AllowedOrigins":["http://localhost:5173"],"AllowedMethods":["GET","PUT"],"AllowedHeaders":["*"],"ExposeHeaders":["ETag"],"MaxAgeSeconds":3000}]}'
awslocal s3api put-bucket-cors --bucket pipeline-uploads --cors-configuration "$CORS"
awslocal s3api put-bucket-cors --bucket pipeline-results --cors-configuration "$CORS"

awslocal sqs create-queue --queue-name pipeline-jobs-dlq
DLQ_ARN=$(awslocal sqs get-queue-attributes \
  --queue-url http://localhost:4566/000000000000/pipeline-jobs-dlq \
  --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)
# Main queue created last: the compose health check waits for it.
awslocal sqs create-queue --queue-name pipeline-jobs --attributes \
  "{\"VisibilityTimeout\":\"60\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"$DLQ_ARN\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}"
