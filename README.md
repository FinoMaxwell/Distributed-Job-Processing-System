# Distributed Job Processing System (Async Task Queue Platform)

Backend platform where users submit heavy jobs via an API and workers process them asynchronously.

## Tech Stack

- **API**: FastAPI (async), Pydantic
- **Workers**: Celery
- **Queue/Cache**: Redis
- **Database**: PostgreSQL + SQLAlchemy
- **Monitoring**: Flower (Celery dashboard)
- **DevOps**: Docker, Docker Compose
- **Testing**: Pytest

## Features

- **Async job submission**: API returns immediately (HTTP 202) with a job id.
- **Retries**: worker retries failed jobs automatically (configurable).
- **Delayed jobs**: schedule execution using `delay_seconds`.
- **Idempotency**: prevent duplicate job creation using `Idempotency-Key` header.
- **JWT auth**: register/login and use Bearer token for protected endpoints.
- **Rate limiting**: limit job submissions per user (Redis-based).
- **Job status**: query status and result from PostgreSQL.
- **Monitoring**: Flower dashboard for workers/tasks.

## Quickstart (Docker Compose)

### Prerequisites

- Docker Desktop installed
- Ports free: **8000** (API), **5555** (Flower), **5432** (Postgres), **6379** (Redis)

### Run

From the project root:

```bash
docker compose up --build
```

### URLs

- **Swagger UI**: `http://localhost:8000/docs`
- **Flower**: `http://localhost:5555`

### Stop

```bash
docker compose down
```

Reset everything (including DB data):

```bash
docker compose down -v
```

## Using Swagger UI (recommended)

1. Open Swagger: `http://localhost:8000/docs`
2. Register a user:
   - `POST /auth/register`
   - Body:

```json
{
  "username": "fino",
  "password": "MyStrongPassword123!"
}
```

3. Login to get a token:
   - `POST /auth/token`
   - Enter `username` and `password`
4. Click **Authorize** (top-right) and enter:
   - `username`: your username
   - `password`: your password
   - Then click **Authorize**
5. Submit a job:
   - `POST /jobs`
   - Body:

```json
{
  "job_type": "heavy",
  "name": "create report",
  "payload": { "report_id": 1234, "format": "pdf" },
  "delay_seconds": 0
}
```

Expected: **202 Accepted** with `id`, `task_id`, and `status: "PENDING"`.

6. Check status/result:
   - `GET /jobs/{job_id}`
   - You should see `PENDING → RUNNING → SUCCESS` (or `FAILED`).

## WebSocket job updates

Endpoint:

- `ws://localhost:8000/ws/jobs/{job_id}`

Behavior:

- The server **pushes updates automatically** (no client polling required).
- Messages look like: `{ "job_id": 3, "status": "RUNNING", "result": null }`
- On completion (`SUCCESS`/`FAILED`) the server closes the socket.

## Idempotency (avoid duplicate submissions)

Send an `Idempotency-Key` header on `POST /jobs`. If you retry the same request with the
same key, the API returns the **same job** (instead of creating a duplicate).

Example header:

- `Idempotency-Key: 6d2e7f1d-0b2b-4e2a-8d8d-2f7b5d7f3f14`

Tip: use a UUID per “user action” (button click).

## Monitoring (Flower)

Open Flower at `http://localhost:5555` to view:

- active workers
- task history
- task failures/retries

## Configuration

Default settings live in `docker-compose.yml` (env vars). Common ones:

- `JWT_SECRET_KEY`: keep stable across runs (changing it invalidates old tokens)
- `RATE_LIMIT_JOBS_PER_MINUTE`: per-user submission limit
- Postgres/Redis connection variables

## Tests

Install deps and run tests (requires Postgres/Redis available):

```bash
pip install -r requirements.txt
pytest
```

## Resume bullets (copy/paste)

- Built a distributed async job processing platform using **FastAPI**, **Celery**, **Redis**, and **PostgreSQL**, containerized via **Docker Compose**.
- Implemented **JWT authentication**, **per-user rate limiting**, **delayed job scheduling**, and **automatic retries** for failed tasks to improve reliability.
- Added **Flower** monitoring for worker/task observability and created **Pytest** coverage for core auth + job submission workflows.

