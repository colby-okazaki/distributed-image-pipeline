#!/usr/bin/env bash
# Runs the test suite against a fresh Docker stack. Used by GitHub Actions and runnable locally:
#   COMPOSE_PROJECT_NAME=pipeline-ci scripts/ci.sh
# A separate project name keeps the CI stack and its volumes apart from your dev stack
# (stop the dev stack first if it is using the same host ports).
set -euo pipefail
cd "$(dirname "$0")/.."

cleanup() {
  status=$?
  if [ $status -ne 0 ]; then
    echo "::group::docker compose logs"
    docker compose logs --no-color --tail 200 || true
    echo "::endgroup::"
  fi
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  exit $status
}
trap cleanup EXIT

echo "== build images"
docker compose build --quiet

if compgen -G "worker/tests/test_*.py" >/dev/null; then
  echo "== worker unit tests"
  docker compose run --rm --no-deps -v "$PWD/worker/tests:/app/tests" worker \
    sh -c "pip install -q pytest==8.3.4 && python -m pytest -q tests"
fi

echo "== start stack without the worker"
# The API smoke test checks job states straight after confirm, so no worker may be consuming yet.
docker compose up -d --wait postgres redis localstack api

echo "== API smoke test"
python3 scripts/smoke_test_api.py

if [ -f scripts/smoke_test_pipeline.py ]; then
  echo "== start worker"
  docker compose up -d --wait worker
  echo "== pipeline smoke test"
  python3 scripts/smoke_test_pipeline.py 25
fi
