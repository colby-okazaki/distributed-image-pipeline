"""Redis cache for batch-status reads.

Cache only: every error is swallowed and the caller falls back to PostgreSQL,
so the API stays correct if Redis is down or cleared.
"""
import json
import logging

import redis

from .config import settings

log = logging.getLogger(__name__)
_client = redis.Redis.from_url(settings.redis_url, socket_timeout=0.2, socket_connect_timeout=0.2)


def _key(batch_id: str) -> str:
    return f"batch-status:{batch_id}"


def get_status(batch_id: str) -> dict | None:
    try:
        raw = _client.get(_key(batch_id))
        return json.loads(raw) if raw else None
    except redis.RedisError as e:
        log.warning("redis get failed, falling back to postgres: %s", e)
        return None


def set_status(batch_id: str, value: dict) -> None:
    try:
        _client.set(_key(batch_id), json.dumps(value, default=str), ex=settings.status_cache_ttl_seconds)
    except redis.RedisError as e:
        log.warning("redis set failed: %s", e)


def invalidate(batch_id: str) -> None:
    try:
        _client.delete(_key(batch_id))
    except redis.RedisError as e:
        log.warning("redis delete failed: %s", e)
