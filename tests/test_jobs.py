import json

import pytest
from httpx import AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_register_and_login_and_create_job(monkeypatch):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Register
        resp = await ac.post(
            "/auth/register",
            json={"username": "alice", "password": "secret123"},
        )
        assert resp.status_code in (200, 201)

        # Login
        resp = await ac.post(
            "/auth/token",
            data={"username": "alice", "password": "secret123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 200
        token = resp.json()["access_token"]

        # Monkeypatch rate limiter to always allow in tests
        from app import rate_limiter

        async def not_limited(user_id: int) -> bool:
            return False

        monkeypatch.setattr(rate_limiter, "is_rate_limited", not_limited)

        # Monkeypatch idempotency storage to in-memory dict for test stability
        from app import idempotency

        store: dict[str, int] = {}

        async def get_existing(user_id: int, key: str) -> int | None:
            return store.get(f"{user_id}:{key}")

        async def lock(user_id: int, key: str) -> bool:
            return True

        async def set_existing(user_id: int, key: str, job_id: int) -> None:
            store[f"{user_id}:{key}"] = job_id

        monkeypatch.setattr(idempotency, "get_existing_job_id", get_existing)
        monkeypatch.setattr(idempotency, "try_lock", lock)
        monkeypatch.setattr(idempotency, "set_job_id", set_existing)

        # Create job
        job_payload = {"numbers": [1, 2, 3]}
        resp = await ac.post(
            "/jobs",
            json={"name": "sum-job", "payload": job_payload},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["name"] == "sum-job"
        assert json.loads(body["payload"]) == job_payload


@pytest.mark.asyncio
async def test_idempotency_key_returns_same_job(monkeypatch):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        await ac.post(
            "/auth/register",
            json={"username": "bob", "password": "secret123"},
        )
        resp = await ac.post(
            "/auth/token",
            data={"username": "bob", "password": "secret123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        token = resp.json()["access_token"]

        from app import rate_limiter

        async def not_limited(user_id: int) -> bool:
            return False

        monkeypatch.setattr(rate_limiter, "is_rate_limited", not_limited)

        from app import idempotency

        store: dict[str, int] = {}

        async def get_existing(user_id: int, key: str) -> int | None:
            return store.get(f"{user_id}:{key}")

        async def lock(user_id: int, key: str) -> bool:
            return True

        async def set_existing(user_id: int, key: str, job_id: int) -> None:
            store[f"{user_id}:{key}"] = job_id

        monkeypatch.setattr(idempotency, "get_existing_job_id", get_existing)
        monkeypatch.setattr(idempotency, "try_lock", lock)
        monkeypatch.setattr(idempotency, "set_job_id", set_existing)

        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "abc-123",
        }
        payload = {"report_id": 1}

        r1 = await ac.post(
            "/jobs",
            json={"name": "job", "payload": payload, "delay_seconds": 0},
            headers=headers,
        )
        r2 = await ac.post(
            "/jobs",
            json={"name": "job", "payload": payload, "delay_seconds": 0},
            headers=headers,
        )

        assert r1.status_code == 202
        assert r2.status_code == 202
        assert r1.json()["id"] == r2.json()["id"]

