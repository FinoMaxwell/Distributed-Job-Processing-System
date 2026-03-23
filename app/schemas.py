from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    is_active: bool

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: int | None = None


class JobCreate(BaseModel):
    job_type: str = Field(default="heavy", max_length=50)
    name: str = Field(..., max_length=100)
    payload: dict[str, Any]
    delay_seconds: int | None = Field(
        default=None, description="Optional delay before execution"
    )


class JobOut(BaseModel):
    id: int
    task_id: str
    name: str
    payload: str
    status: str
    result: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class JobStatusUpdate(BaseModel):
    status: str
    result: str | None = None

