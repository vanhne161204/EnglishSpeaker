"""Shared schemas."""

from pydantic import BaseModel


class HealthStatus(BaseModel):
    status: str
    service: str
    environment: str
