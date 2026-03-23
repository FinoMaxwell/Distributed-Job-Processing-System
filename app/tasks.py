import json
import logging
import time

from celery import states
from celery.exceptions import Ignore
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .celery_app import celery_app
from .config import get_settings
from .database import Base
from .models import Job, JobStatus
from .notifications import JOB_UPDATES_CHANNEL, encode_job_update


settings = get_settings()
logger = logging.getLogger("worker")


def _publish_job_update(job_id: int, status: str, result: str | None) -> None:
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url)
        client.publish(JOB_UPDATES_CHANNEL, encode_job_update(job_id, status, result))
    except Exception:  # noqa: BLE001
        # Best effort only; DB remains source of truth.
        return


def _get_sync_session() -> Session:
    """
    Celery workers run in a separate process; use a sync engine/session here.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(settings.database_url, echo=False, future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SessionLocal()


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 10},
)
def heavy_job(self, job_id: int, job_type: str, payload: dict) -> dict:
    """
    Demo heavy job with retry support + multiple job types.
    """
    session = _get_sync_session()
    try:
        job: Job | None = session.execute(
            select(Job).where(Job.id == job_id)
        ).scalar_one_or_none()
        if not job:
            self.update_state(
                state=states.FAILURE, meta={"reason": "Job not found", "job_id": job_id}
            )
            raise Ignore()

        session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status=JobStatus.RUNNING)
        )
        session.commit()
        _publish_job_update(job_id, JobStatus.RUNNING, None)

        # Simulate heavy computation and provide a few demo behaviors.
        if job_type == "sleep":
            seconds = int(payload.get("seconds", 5))
            time.sleep(max(0, min(seconds, 30)))
        elif job_type == "fail":
            raise RuntimeError("Intentional failure (job_type=fail)")
        else:
            time.sleep(5)

        # Simple "processing" - count keys and return payload back
        result = {
            "job_id": job_id,
            "job_type": job_type,
            "input_keys": list(payload.keys()),
            "summary": f"Processed payload with {len(payload)} keys.",
        }

        session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status=JobStatus.SUCCESS, result=json.dumps(result))
        )
        session.commit()
        _publish_job_update(job_id, JobStatus.SUCCESS, json.dumps(result))

        return result
    except Exception as exc:  # noqa: BLE001
        # Mark as failed if max retries exceeded
        if self.request.retries >= self.max_retries:
            session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(status=JobStatus.FAILED, result=str(exc))
            )
            session.commit()
            _publish_job_update(job_id, JobStatus.FAILED, str(exc))
        raise
    finally:
        session.close()

