#!/bin/sh
# Runs inside LocalStack on startup: creates buckets and queues for local dev.
awslocal s3 mb s3://pipeline-uploads
awslocal s3 mb s3://pipeline-results
awslocal sqs create-queue --queue-name pipeline-jobs-dlq
DLQ_ARN=$(awslocal sqs get-queue-attributes --queue-url http://localhost:4566/000000000000/pipeline-jobs-dlq \
  --attribute-names QueueArn --query 'Attributes.QueueArn' --output text)
awslocal sqs create-queue --queue-name pipeline-jobs --attributes "{\"VisibilityTimeout\":\"60\",\"RedrivePolicy\":\"{\\\"deadLetterTargetArn\\\":\\\"$DLQ_ARN\\\",\\\"maxReceiveCount\\\":\\\"3\\\"}\"}"
