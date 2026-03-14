from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator


class UserActivityEvent(BaseModel):
    user_id: int = Field(gt=0)
    event_type: str = Field(min_length=1, max_length=50)
    timestamp: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include timezone information")
        return value


class TrackEventResponse(BaseModel):
    message: str
