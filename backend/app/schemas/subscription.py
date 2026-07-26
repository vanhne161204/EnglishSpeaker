"""Subscription (plan + limits) schemas (PRD §8.11)."""

from pydantic import BaseModel

from app.models.enums import PlanTier


class PlanLimits(BaseModel):
    # ``None`` means unlimited.
    ai_suggestions_per_day: int | None
    max_saved_notes: int | None
    max_topics: int | None


class SubscriptionRead(BaseModel):
    plan: PlanTier
    limits: PlanLimits


class SubscriptionUpdate(BaseModel):
    plan: PlanTier
