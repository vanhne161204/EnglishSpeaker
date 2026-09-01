"""Admin panel request/response schemas (docs/11_Security.md §11.9).

Every route that uses these is behind ``require_admin``. None of them takes an
actor id from the caller — the acting admin always comes from the session token,
for the same reason the rest of the API stopped accepting `user_id` bodies
(§11.4).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.enums import PlanTier, UserRole

# --- users -----------------------------------------------------------------


class AdminUserRead(BaseModel):
    """One row of the users table, with the numbers that make a row actionable."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str | None
    display_name: str
    role: UserRole
    plan: str
    level: str | None
    created_at: datetime
    suspended_at: datetime | None
    suspended_reason: str | None
    # Activity, so an admin can tell a real learner from a drive-by signup before
    # deciding what to do about a report.
    messages_sent: int = 0
    lines_spoken: int = 0
    # Reports naming this person. One is noise; several is a pattern.
    reports_against: int = 0


class AdminUserPage(BaseModel):
    items: list[AdminUserRead]
    total: int
    limit: int
    offset: int


class AdminUserUpdate(BaseModel):
    """A partial update. Every field is optional; only what is sent changes."""

    role: UserRole | None = None
    plan: PlanTier | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    # True suspends, False lifts. Separate from `suspended_reason` so lifting a
    # suspension does not require restating why it was applied.
    suspended: bool | None = None
    suspended_reason: str | None = Field(default=None, max_length=200)


# --- AI spend ---------------------------------------------------------------


class SpendByTask(BaseModel):
    task: str
    cost_usd: Decimal
    calls: int


class SpendByUser(BaseModel):
    user_id: uuid.UUID
    username: str | None
    display_name: str
    cost_usd: Decimal
    calls: int


class SpendByDay(BaseModel):
    """One point on the trend line. Quiet days are present with zeros, so the
    axis stays evenly spaced instead of compressing time."""

    day: str
    cost_usd: Decimal
    calls: int


class AiCallRead(BaseModel):
    """One row of the raw ledger — a single AI call and what it cost.

    Aggregates answer "how much". This answers "which call", which is the only
    way to find out why a figure looks wrong.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    task: str
    provider: str
    model: str
    user_id: uuid.UUID | None
    room_id: uuid.UUID | None
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    cost_usd: Decimal
    latency_ms: int
    #: True when a fallback answered instead of the first choice in the chain.
    degraded: bool
    #: False when every provider failed. Recorded so outages show in the data.
    ok: bool

    @field_serializer("cost_usd")
    def _fixed_places(self, value: Decimal) -> Decimal:
        """Money is stored at 8 decimal places, so a zero serialises as "0E-8"
        — correct and unreadable. Six places matches the pricing table and the
        summary, so the ledger and the totals above it look like one number."""
        return value.quantize(Decimal("0.000001"))


class AiCallPage(BaseModel):
    items: list[AiCallRead]
    limit: int
    offset: int


class ModelHealth(BaseModel):
    """A rising degraded or failed count is an outage, visible before the bill."""

    model: str
    calls: int
    degraded: int
    failed: int


class AiSpendSummary(BaseModel):
    """What the AI cost, and where it went.

    Vendor dashboards give one total. They cannot answer "which feature ate the
    budget" or "what does one user cost", which are the two questions that set
    the price of the product (docs §18.8).
    """

    today_usd: Decimal
    week_usd: Decimal
    month_usd: Decimal
    # Calls that failed outright in the last 24h. Nonzero means users saw errors.
    failed_24h: int
    #: Total calls in the window — cost alone cannot tell a busy day from an
    #: expensive one.
    calls: int
    by_day: list[SpendByDay]
    by_task: list[SpendByTask]
    by_user: list[SpendByUser]
    health: list[ModelHealth]


# --- abuse reports ----------------------------------------------------------


class ReportReason(StrEnum):
    harassment = "harassment"
    inappropriate = "inappropriate"
    spam = "spam"
    hate = "hate"
    other = "other"


class ReportStatusValue(StrEnum):
    open = "open"
    resolved = "resolved"
    dismissed = "dismissed"


class ReportCreate(BaseModel):
    """Filed by an ordinary signed-in user, not an admin.

    There is no `reporter_id`: it comes from the session token. Letting the
    client name the reporter would allow filing reports as somebody else.
    """

    target_user_id: uuid.UUID
    room_id: uuid.UUID | None = None
    reason: ReportReason
    detail: str | None = Field(default=None, max_length=2000)
    # Optional line the reporter is pointing at, copied at report time so it
    # survives deletion of the original message.
    quoted_text: str | None = Field(default=None, max_length=2000)


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reporter_id: uuid.UUID | None
    reporter_name: str
    target_user_id: uuid.UUID | None
    target_name: str
    room_id: uuid.UUID | None
    reason: str
    detail: str | None
    quoted_text: str | None
    status: str
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime


class ReportReview(BaseModel):
    """An admin's decision on a report."""

    status: ReportStatusValue
    note: str | None = Field(default=None, max_length=1000)
    # Optionally suspend the reported account in the same action, because
    # "resolve" and "actually do something about it" are usually one decision.
    suspend_target: bool = False
    suspend_reason: str | None = Field(default=None, max_length=200)


# --- bans -------------------------------------------------------------------


class BanRead(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    room_title: str | None
    user_id: uuid.UUID
    user_name: str | None
    reason: str | None
    expires_at: datetime | None
    created_at: datetime


# --- audit ------------------------------------------------------------------


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_name: str
    action: str
    target_type: str
    target_id: uuid.UUID | None
    target_name: str
    detail: str | None
    created_at: datetime


# --- overview ---------------------------------------------------------------


class AdminOverview(BaseModel):
    """The numbers worth putting above the tabs."""

    total_users: int
    admins: int
    suspended: int
    new_users_7d: int
    open_reports: int
    active_bans: int
    spend_today_usd: Decimal
    spend_month_usd: Decimal
    # Content gaps, because a topic with no questions is invisible to learners
    # but looks fine in the topic list.
    topics_without_questions: int
