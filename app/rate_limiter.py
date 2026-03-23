from datetime import timedelta

import redis.asyncio as redis

from .config import get_settings


settings = get_settings()

_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url)
    return _redis_client


async def is_rate_limited(user_id: int) -> bool:
    """
    Simple sliding-window rate limit using Redis INCR with expiry.
    """
    client = get_redis_client()
    key = f"user:{user_id}:job_submissions"
    ttl = timedelta(minutes=1)
    current = await client.incr(key)
    if current == 1:
        await client.expire(key, int(ttl.total_seconds()))
    return current > settings.rate_limit_jobs_per_minute

