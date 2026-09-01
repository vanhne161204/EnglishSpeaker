"""Admin panel endpoints (docs/11_Security.md §11.9).

Every route here depends on ``require_admin``, so a non-admin gets 403 before any
handler runs. The acting admin is always taken from the session token — no route
accepts an actor id, for the same reason the rest of the API stopped accepting
`user_id` bodies (§11.4).

The one route that is NOT admin-only lives in `moderation.py`: filing an abuse
report is something an ordinary learner does.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import get_admin_service, require_admin
from app.models.user import User
from app.schemas.admin import (
    AdminOverview,
    AdminUserPage,
    AdminUserRead,
    AdminUserUpdate,
    AiCallPage,
    AiSpendSummary,
    AuditRead,
    BanRead,
    ReportRead,
    ReportReview,
)
from app.services.admin import AdminService

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# --- overview ---------------------------------------------------------------


@router.get("/overview", response_model=AdminOverview, summary="Headline numbers")
async def overview(service: AdminService = Depends(get_admin_service)) -> AdminOverview:
    return await service.overview()


# --- users ------------------------------------------------------------------


@router.get("/users", response_model=AdminUserPage, summary="List and search accounts")
async def list_users(
    q: str | None = Query(default=None, description="Matches username or display name"),
    role: str | None = Query(default=None, pattern="^(user|admin)$"),
    plan: str | None = Query(default=None, pattern="^(free|premium)$"),
    suspended: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: AdminService = Depends(get_admin_service),
) -> AdminUserPage:
    return await service.list_users(
        q, role=role, plan=plan, suspended=suspended, limit=limit, offset=offset
    )


@router.get("/users/{user_id}", response_model=AdminUserRead, summary="One account")
async def get_user(
    user_id: uuid.UUID, service: AdminService = Depends(get_admin_service)
) -> AdminUserRead:
    return await service.get_user(user_id)


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserRead,
    summary="Change role, plan, name or suspension",
)
async def update_user(
    user_id: uuid.UUID,
    payload: AdminUserUpdate,
    actor: User = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> AdminUserRead:
    return await service.update_user(actor, user_id, payload)


@router.delete(
    "/users/{user_id}",
    status_code=204,
    summary="Delete an account permanently",
)
async def delete_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> Response:
    await service.delete_user(actor, user_id)
    return Response(status_code=204)


# --- AI spend ---------------------------------------------------------------


@router.get("/ai-spend", response_model=AiSpendSummary, summary="What the AI cost")
async def ai_spend(
    days: int = Query(default=30, ge=1, le=365),
    top: int = Query(default=10, ge=1, le=50),
    service: AdminService = Depends(get_admin_service),
) -> AiSpendSummary:
    return await service.ai_spend(days, top)


@router.get(
    "/ai-calls",
    response_model=AiCallPage,
    summary="Every AI call, newest first",
)
async def ai_calls(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    task: str | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    failed_only: bool = Query(default=False),
    service: AdminService = Depends(get_admin_service),
) -> AiCallPage:
    """The raw ledger behind the summary.

    Aggregates say how much was spent; this says which call spent it. When a
    figure looks wrong, reading the rows that produced it is the only way to
    find out why.
    """
    return await service.ai_calls(
        limit, offset, task=task, user_id=user_id, failed_only=failed_only
    )


# --- safety queue -----------------------------------------------------------


@router.get("/reports", response_model=list[ReportRead], summary="Abuse report queue")
async def list_reports(
    status: str | None = Query(default="open", pattern="^(open|resolved|dismissed)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: AdminService = Depends(get_admin_service),
) -> list:
    return await service.list_reports(status, limit, offset)


@router.patch(
    "/reports/{report_id}",
    response_model=ReportRead,
    summary="Resolve or dismiss a report",
)
async def review_report(
    report_id: uuid.UUID,
    payload: ReportReview,
    actor: User = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
):
    return await service.review_report(actor, report_id, payload)


@router.get("/bans", response_model=list[BanRead], summary="Active room bans")
async def list_bans(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: AdminService = Depends(get_admin_service),
) -> list[BanRead]:
    return await service.list_bans(limit, offset)


@router.delete("/bans/{ban_id}", status_code=204, summary="Lift a ban")
async def lift_ban(
    ban_id: uuid.UUID,
    actor: User = Depends(require_admin),
    service: AdminService = Depends(get_admin_service),
) -> Response:
    await service.lift_ban(actor, ban_id)
    return Response(status_code=204)


# --- audit ------------------------------------------------------------------


@router.get("/audit", response_model=list[AuditRead], summary="Admin action log")
async def list_audit(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: AdminService = Depends(get_admin_service),
) -> list:
    return await service.list_audit(limit, offset)
