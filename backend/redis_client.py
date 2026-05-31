"""
redis_client.py — Shared Redis connection singleton.

All modules that need Redis import get_redis() from here so the
connection pool is created once and reused across requests.
"""

import os
from pathlib import Path

import redis
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True,
        )
    return _client
