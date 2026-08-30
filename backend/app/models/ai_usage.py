"""AiUsage model — what every AI call cost (docs §18.8).

This table is what makes the product priceable. Vendor dashboards show a total;
they cannot tell you what one *user* costs, which feature ate the budget, or
whether the free tier is affordable. Those are the questions that set the price,
and they can only be answered from data you started collecting on day one —
spend you did not record cannot be recovered later.

One row per call, written by ``MeteredProvider``. Failed calls are recorded too
(``ok=False``): a provider that is timing out constantly is an outage you want
visible, and a rising ``degraded`` rate is an early warning.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AiUsage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_usage"

    # The budget guard runs "calls by this user, for this task, since <date>" on
    # every single AI call. On the fastest-growing table in the schema that has
    # to be an index, not a scan.
    __table_args__ = (
        Index("ix_ai_usage_user_task_created", "user_id", "task", "created_at"),
        Index("ix_ai_usage_created_at", "created_at"),
    )

    # Nullable so an unauthenticated or system call is still recorded rather than
    # silently dropped — unattributed spend is still spend.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, default=None
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), index=True, default=None
    )

    # rescue | translate | sentence_check | ielts_report (app/ai/routing.py AiTask)
    task: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    model: Mapped[str] = mapped_column(String(48), index=True, nullable=False)

    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Numeric, never Float: this is money. Six decimals because a single rescue
    # call costs about $0.000011 — three would round it to zero.
    cost_usd: Mapped[float] = mapped_column(
        Numeric(12, 8), default=0, server_default="0", nullable=False
    )
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # True when a fallback answered instead of the first choice in the chain.
    degraded: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    # False when every provider failed. Kept so outages are visible in the data.
    ok: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
