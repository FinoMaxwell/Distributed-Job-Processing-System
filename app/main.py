import json
import logging
from datetime import timedelta

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import CurrentUser, authenticate_user, create_access_token, get_password_hash
from .config import get_settings
from .database import get_db, init_db
from .models import Job, JobStatus, User
from .notifications import JOB_UPDATES_CHANNEL, decode_job_update, get_redis_pubsub
from .rate_limiter import is_rate_limited
from .schemas import JobCreate, JobOut, Token, UserCreate, UserOut
from .tasks import heavy_job
from .idempotency import get_existing_job_id, set_job_id, try_lock


settings = get_settings()
app = FastAPI(title=settings.app_name)
logger = logging.getLogger("api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()


@app.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    existing = await db.execute(select(User).where(User.username == user_in.username))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    user = User(
        username=user_in.username,
        hashed_password=get_password_hash(user_in.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@app.post("/auth/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.id},
        expires_delta=access_token_expires,
    )
    return Token(access_token=access_token)


@app.post("/jobs", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    job_in: JobCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JobOut:
    if await is_rate_limited(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
        )

    if idempotency_key:
        existing_job_id = await get_existing_job_id(current_user.id, idempotency_key)
        if existing_job_id is not None:
            result = await db.execute(
                select(Job).where(
                    Job.id == existing_job_id, Job.user_id == current_user.id
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing
        await try_lock(current_user.id, idempotency_key)

    job = Job(
        user_id=current_user.id,
        name=job_in.name,
        payload=json.dumps(job_in.payload),
        status=JobStatus.PENDING,
        task_id="",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    countdown = job_in.delay_seconds or 0
    task = heavy_job.apply_async(
        args=[job.id, job_in.job_type, job_in.payload],
        countdown=countdown,
    )

    job.task_id = task.id
    await db.commit()
    await db.refresh(job)
    if idempotency_key:
        await set_job_id(current_user.id, idempotency_key, job.id)
    logger.info("job_created user_id=%s job_id=%s task_id=%s", current_user.id, job.id, job.task_id)
    return job


@app.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(
    job_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> JobOut:
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@app.get("/me", response_model=UserOut)
async def read_users_me(current_user: CurrentUser) -> UserOut:
    return current_user


@app.websocket("/ws/jobs/{job_id}")
async def job_status_ws(
    websocket: WebSocket,
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    await websocket.accept()
    pubsub = get_redis_pubsub()
    await pubsub.subscribe(JOB_UPDATES_CHANNEL)
    try:
        # Send current state immediately.
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            await websocket.send_json({"error": "Job not found"})
            await websocket.close(code=1008)
            return
        await websocket.send_json({"job_id": job.id, "status": job.status, "result": job.result})
        if job.status in {JobStatus.SUCCESS, JobStatus.FAILED}:
            await websocket.close()
            return

        # Stream updates pushed by workers via Redis pubsub.
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
            update = decode_job_update(message)
            if not update:
                continue
            if int(update.get("job_id", -1)) != job_id:
                continue
            await websocket.send_json(update)
            if update.get("status") in {JobStatus.SUCCESS, JobStatus.FAILED}:
                await websocket.close()
                break
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await pubsub.unsubscribe(JOB_UPDATES_CHANNEL)
            await pubsub.close()
        except Exception:  # noqa: BLE001
            pass

