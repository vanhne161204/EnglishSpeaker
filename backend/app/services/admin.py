"""Admin panel operations, and the rails that stop an admin locking themselves out.

Everything here is behind ``require_admin``. The rules enforced below are not UI
polish — each one is a state this system can otherwise be put into and not get
out of:

* **You cannot change your own role.** One click and there is no admin left who
  can undo it.
* **You cannot remove the last admin.** Demote or delete, same rule. There is
  no allowlist to fall back on any more — recovery means SSH and
  ``scripts/grant_admin.py``, so it is much better not to need it.
* **You cannot suspend or delete yourself.** Same reasoning, less dramatic.

Every write is recorded in ``admin_audit_log`` (docs/11_Security.md §11.9).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.abuse_report import AbuseReport
from app.models.admin_audit import AdminAuditLog
from app.models.doc import Doc, DocSection, Question
from app.models.enums import UserRole
from app.models.topic import Topic
from app.models.user import User
from app.repositories.abuse_report import AbuseReportRepository
from app.repositories.ai_usage import AiUsageRepository
from app.repositories.audit import AuditRepository
from app.repositories.room_ban import RoomBanRepository
from app.repositories.user import UserRepository
from app.schemas.admin import (
    AdminOverview,
    AdminUserPage,
    AdminUserRead,
    AdminUserUpdate,
    AiSpendSummary,
    BanRead,
    ModelHealth,
    ReportCreate,
    ReportReview,
    SpendByTask,
    SpendByUser,
)

# Money is stored at 8 decimal places, because a single rescue call costs about
# $0.000011. Raw, that serialises as "0E-8" — technically correct and unreadable.
# Six places is the precision the pricing table actually carries.
_CENTS = Decimal("0.000001")


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_CENTS)


class AdminService:
    def __init__(
        self,
        session: AsyncSession,
        users: UserRepository,
        usage: AiUsageRepository,
        reports: AbuseReportRepository,
        bans: RoomBanRepository,
        audit: AuditRepository,
    ) -> None:
        self.session = session
        self.users = users
        self.usage = usage
        self.reports = reports
        self.bans = bans
        self.audit = audit

    # --- users -------------------------------------------------------------

    async def list_users(
        self,
        query: str | None = None,
        *,
        role: str | None = None,
        plan: str | None = None,
        suspended: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AdminUserPage:
        rows = await self.users.search(
            query, role=role, plan=plan, suspended=suspended, limit=limit, offset=offset
        )
        total = await self.users.count(query, role=role, plan=plan, suspended=suspended)

        # Two aggregate queries for the whole page. Per-row lookups would be 100
        # round trips to render a list of 50.
        ids = [u.id for u in rows]
        activity = await self.users.activity(ids)
        reports_by_user = await self._reports_against(ids)

        items = [self._to_read(u, activity, reports_by_user) for u in rows]
        return AdminUserPage(items=items, total=total, limit=limit, offset=offset)

    async def get_user(self, user_id: uuid.UUID) -> AdminUserRead:
        user = await self.users.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        activity = await self.users.activity([user.id])
        reports = await self._reports_against([user.id])
        return self._to_read(user, activity, reports)

    async def update_user(
        self, actor: User, user_id: uuid.UUID, payload: AdminUserUpdate
    ) -> AdminUserRead:
        """Apply a partial update, refusing anything that would strand the system."""
        target = await self.users.get(user_id)
        if target is None:
            raise NotFoundError("User not found")

        changes: list[str] = []

        if payload.role is not None and payload.role.value != target.role:
            if target.id == actor.id:
                raise ForbiddenError("You cannot change your own role.", code="self_role_change")
            if target.role == UserRole.admin and await self.users.count_admins() <= 1:
                raise ConflictError(
                    "This is the last admin — promote someone else first.",
                    code="last_admin",
                )
            changes.append(f"role {target.role} -> {payload.role.value}")
            target.role = payload.role.value

        if payload.plan is not None and payload.plan.value != target.plan:
            changes.append(f"plan {target.plan} -> {payload.plan.value}")
            target.plan = payload.plan.value

        if payload.display_name is not None and payload.display_name != target.display_name:
            changes.append(f"name {target.display_name} -> {payload.display_name}")
            target.display_name = payload.display_name.strip()

        if payload.suspended is not None:
            if payload.suspended and target.id == actor.id:
                raise ForbiddenError("You cannot suspend your own account.", code="self_suspend")
            if payload.suspended and target.suspended_at is None:
                target.suspended_at = datetime.now(UTC)
                target.suspended_reason = payload.suspended_reason
                why = payload.suspended_reason or "no reason given"
                changes.append(f"suspended ({why})")
            elif not payload.suspended and target.suspended_at is not None:
                target.suspended_at = None
                target.suspended_reason = None
                changes.append("suspension lifted")

        if changes:
            await self._record(actor, "user.update", "user", target, "; ".join(changes))

        await self.session.flush()
        return await self.get_user(target.id)

    async def delete_user(self, actor: User, user_id: uuid.UUID) -> None:
        """Permanent. Cascades to that person's notes, transcripts and reports.

        Suspension is almost always the right action instead. This exists for
        deletion requests, which are an obligation rather than a moderation tool.
        """
        target = await self.users.get(user_id)
        if target is None:
            raise NotFoundError("User not found")
        if target.id == actor.id:
            raise ForbiddenError("You cannot delete your own account here.", code="self_delete")
        if target.role == UserRole.admin and await self.users.count_admins() <= 1:
            raise ConflictError(
                "This is the last admin — promote someone else first.", code="last_admin"
            )

        # Recorded BEFORE the delete: afterwards there is no name left to record.
        await self._record(
            actor, "user.delete", "user", target, f"deleted account {target.username}"
        )
        await self.users.delete(target)

    # --- AI spend ----------------------------------------------------------

    async def ai_spend(self, days: int = 30, top: int = 10) -> AiSpendSummary:
        """What the AI cost, and where it went (docs §18.8).

        A vendor dashboard gives one total. It cannot say which feature ate the
        budget or what a single user costs, and those two answers are what set
        the price of the product.
        """
        now = datetime.now(UTC)
        today = await self.usage.spend_since(now - timedelta(days=1))
        week = await self.usage.spend_since(now - timedelta(days=7))
        month = await self.usage.spend_since(now - timedelta(days=30))

        by_task = [
            SpendByTask(task=task, cost_usd=_money(cost), calls=calls)
            for task, cost, calls in await self.usage.cost_by_task(days)
        ]

        by_user: list[SpendByUser] = []
        for user_id, cost in await self.usage.cost_per_user(days, limit=top):
            user = await self.users.get(user_id)
            by_user.append(
                SpendByUser(
                    user_id=user_id,
                    username=user.username if user else None,
                    display_name=user.display_name if user else "(deleted account)",
                    cost_usd=_money(cost),
                    calls=0,
                )
            )

        health = [
            ModelHealth(model=model, calls=calls, degraded=degraded, failed=failed)
            for model, calls, degraded, failed in await self.usage.health(24)
        ]

        return AiSpendSummary(
            today_usd=_money(today),
            week_usd=_money(week),
            month_usd=_money(month),
            failed_24h=sum(h.failed for h in health),
            by_task=by_task,
            by_user=by_user,
            health=health,
        )

    # --- abuse reports -----------------------------------------------------

    async def file_report(self, reporter: User, payload: ReportCreate) -> AbuseReport:
        """Filed by an ordinary user, so this is not an audited admin action."""
        if payload.target_user_id == reporter.id:
            raise ForbiddenError("You cannot report yourself.", code="self_report")

        target = await self.users.get(payload.target_user_id)
        if target is None:
            raise NotFoundError("That user no longer exists")

        report = AbuseReport(
            reporter_id=reporter.id,
            reporter_name=reporter.display_name,
            target_user_id=target.id,
            target_name=target.display_name,
            room_id=payload.room_id,
            reason=payload.reason.value,
            detail=payload.detail,
            quoted_text=payload.quoted_text,
        )
        return await self.reports.add(report)

    async def list_reports(
        self, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[AbuseReport]:
        return await self.reports.list(status, limit, offset)

    async def review_report(
        self, actor: User, report_id: uuid.UUID, payload: ReportReview
    ) -> AbuseReport:
        """Close a report, optionally suspending the account it names.

        Deciding and acting are one motion for a moderator, so they are one
        request here — otherwise the common case is two calls that can half-fail.
        """
        report = await self.reports.get(report_id)
        if report is None:
            raise NotFoundError("Report not found")

        report.status = payload.status.value
        report.reviewed_by = actor.id
        report.reviewed_at = datetime.now(UTC)
        report.review_note = payload.note

        detail = f"{payload.status.value}: {payload.note or 'no note'}"

        if payload.suspend_target and report.target_user_id is not None:
            target = await self.users.get(report.target_user_id)
            if target is None:
                raise NotFoundError("That user no longer exists")
            if target.id == actor.id:
                raise ForbiddenError("You cannot suspend your own account.", code="self_suspend")
            if target.suspended_at is None:
                target.suspended_at = datetime.now(UTC)
                target.suspended_reason = payload.suspend_reason or "Reported for abuse"
                detail += f"; suspended {target.username}"

        await self._record(actor, "report.review", "report", None, detail)
        await self.session.flush()
        return report

    # --- bans --------------------------------------------------------------

    async def list_bans(self, limit: int = 100, offset: int = 0) -> list[BanRead]:
        return [
            BanRead(
                id=ban.id,
                room_id=ban.room_id,
                room_title=room_title,
                user_id=ban.user_id,
                user_name=user_name,
                reason=ban.reason,
                expires_at=ban.expires_at,
                created_at=ban.created_at,
            )
            for ban, room_title, user_name in await self.bans.list_active(limit, offset)
        ]

    async def lift_ban(self, actor: User, ban_id: uuid.UUID) -> None:
        ban = await self.bans.lift(ban_id)
        if ban is None:
            raise NotFoundError("Ban not found")
        await self._record(
            actor,
            "ban.lift",
            "ban",
            None,
            f"lifted ban on user {ban.user_id} in room {ban.room_id}",
        )

    # --- audit -------------------------------------------------------------

    async def list_audit(self, limit: int = 100, offset: int = 0) -> list[AdminAuditLog]:
        return await self.audit.list(limit, offset)

    # --- overview ----------------------------------------------------------

    async def overview(self) -> AdminOverview:
        now = datetime.now(UTC)
        return AdminOverview(
            total_users=await self.users.count(),
            admins=await self.users.count_admins(),
            suspended=await self.users.count(suspended=True),
            new_users_7d=await self.users.count_since(now - timedelta(days=7)),
            open_reports=await self.reports.count_open(),
            active_bans=len(await self.bans.list_active(limit=1000)),
            spend_today_usd=_money(await self.usage.spend_since(now - timedelta(days=1))),
            spend_month_usd=_money(await self.usage.spend_since(now - timedelta(days=30))),
            topics_without_questions=await self._topics_without_questions(),
        )

    # --- internals ---------------------------------------------------------

    async def _reports_against(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        """How many reports name each user. One is noise; six is a pattern."""
        if not user_ids:
            return {}
        stmt = (
            select(AbuseReport.target_user_id, func.count())
            .where(AbuseReport.target_user_id.in_(user_ids))
            .group_by(AbuseReport.target_user_id)
        )
        rows = (await self.session.execute(stmt)).all()
        return {uid: int(n) for uid, n in rows if uid is not None}

    async def _topics_without_questions(self) -> int:
        """A topic with no questions looks fine in the topic list and is empty in
        the room. This number turns a hunt into a to-do list."""
        with_questions = (
            select(Doc.topic_id)
            .join(DocSection, DocSection.doc_id == Doc.id)
            .join(Question, Question.section_id == DocSection.id)
            .distinct()
        )
        stmt = select(func.count()).select_from(Topic).where(Topic.id.not_in(with_questions))
        return int((await self.session.execute(stmt)).scalar_one())

    async def _record(
        self, actor: User, action: str, target_type: str, target: User | None, detail: str
    ) -> None:
        await self.audit.record(
            actor_id=actor.id,
            actor_name=actor.display_name,
            action=action,
            target_type=target_type,
            target_id=target.id if target else None,
            target_name=(target.username or target.display_name) if target else "",
            detail=detail,
        )

    @staticmethod
    def _to_read(
        user: User,
        activity: dict[uuid.UUID, tuple[int, int]],
        reports: dict[uuid.UUID, int],
    ) -> AdminUserRead:
        messages, lines = activity.get(user.id, (0, 0))
        return AdminUserRead(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            role=UserRole(user.role),
            plan=user.plan,
            level=user.level,
            created_at=user.created_at,
            suspended_at=user.suspended_at,
            suspended_reason=user.suspended_reason,
            messages_sent=messages,
            lines_spoken=lines,
            reports_against=reports.get(user.id, 0),
        )
