from datetime import timedelta

from .rate_limiter import get_redis_client


IDEMPOTENCY_TTL = timedelta(days=1)


async def get_existing_job_id(user_id: int, key: str) -> int | None:
    client = get_redis_client()
    value = await client.get(f"idem:{user_id}:{key}")
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def try_lock(user_id: int, key: str) -> bool:
    """
    Best-effort lock to prevent duplicate creation races.
    """
    client = get_redis_client()
    return bool(
        await client.set(
            f"idemlock:{user_id}:{key}",
            "1",
            ex=int(timedelta(seconds=30).total_seconds()),
            nx=True,
        )
    )


async def set_job_id(user_id: int, key: str, job_id: int) -> None:
    client = get_redis_client()
    await client.set(
        f"idem:{user_id}:{key}",
        str(job_id),
        ex=int(IDEMPOTENCY_TTL.total_seconds()),
    )

