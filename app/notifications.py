import json
from typing import Any

import redis.asyncio as redis

from .config import get_settings


settings = get_settings()

JOB_UPDATES_CHANNEL = "job_updates"


def get_redis_pubsub() -> redis.client.PubSub:
    client = redis.from_url(settings.redis_url)
    return client.pubsub()


def encode_job_update(job_id: int, status: str, result: str | None) -> str:
    return json.dumps({"job_id": job_id, "status": status, "result": result})


def decode_job_update(message: Any) -> dict[str, Any] | None:
    if not message or message.get("type") != "message":
        return None
    data = message.get("data")
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8", errors="ignore")
    try:
        return json.loads(data)
    except Exception:  # noqa: BLE001
        return None

