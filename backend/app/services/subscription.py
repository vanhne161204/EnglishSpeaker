"""Business logic for subscriptions (PRD §8.11).

Each user is on a plan (free / premium) with a set of limits. This service exposes
the plan and its limits, and lets a user upgrade or cancel. Enforcement of the
limits (counting daily usage) is a follow-up that needs per-user usage tracking.
"""

import uuid

from app.core.exceptions import NotFoundError
from app.models.enums import PlanTier
from app.repositories.user import UserRepository
from app.schemas.subscription import PlanLimits, SubscriptionRead

# Limits per plan. ``None`` means unlimited.
PLAN_LIMITS: dict[PlanTier, PlanLimits] = {
    PlanTier.free: PlanLimits(
        ai_suggestions_per_day=10, max_saved_notes=50, max_topics=5
    ),
    PlanTier.premium: PlanLimits(
        ai_suggestions_per_day=None, max_saved_notes=None, max_topics=None
    ),
}


class SubscriptionService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    async def get_subscription(self, user_id: uuid.UUID) -> SubscriptionRead:
        plan = await self._user_plan(user_id)
        return SubscriptionRead(plan=plan, limits=PLAN_LIMITS[plan])

    async def set_plan(self, user_id: uuid.UUID, plan: PlanTier) -> SubscriptionRead:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        user.plan = plan.value
        return SubscriptionRead(plan=plan, limits=PLAN_LIMITS[plan])

    async def _user_plan(self, user_id: uuid.UUID) -> PlanTier:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return PlanTier(user.plan)
