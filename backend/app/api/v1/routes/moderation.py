"""Reporting abuse — the one moderation route ordinary learners use.

Separate from `admin.py` because the audience is different: any signed-in user
can file a report, only an admin can read or close one. Keeping them in one
router behind `require_admin` would have made the whole feature unreachable to
the people it exists for.

Named `moderation` rather than `reports` because `reports.py` is already taken by
the IELTS session report — a different thing with an unfortunately similar name.
"""

from fastapi import APIRouter, Depends

from app.api.deps import get_admin_service, get_current_user
from app.models.user import User
from app.schemas.admin import ReportCreate, ReportRead
from app.services.admin import AdminService

router = APIRouter(prefix="/moderation", tags=["moderation"])


@router.post(
    "/reports",
    response_model=ReportRead,
    status_code=201,
    summary="Report another learner",
)
async def file_report(
    payload: ReportCreate,
    reporter: User = Depends(get_current_user),
    service: AdminService = Depends(get_admin_service),
):
    """File a report about someone met in a room.

    The reporter is the token holder. There is no `reporter_id` in the body: a
    client-supplied one would let anybody file reports under someone else's name,
    which turns a safety tool into a harassment tool.
    """
    return await service.file_report(reporter, payload)
