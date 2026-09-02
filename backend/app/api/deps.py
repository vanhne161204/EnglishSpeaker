"""Reusable FastAPI dependencies (wiring services to requests)."""

import uuid

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import build_llm, build_transcriber, build_translator
from app.ai.routing import AiTask
from app.core.exceptions import AppError
from app.core.security import decode_access_token
from app.db.session import AsyncSessionLocal, get_session
from app.models.enums import PlanTier, UserRole
from app.models.user import User
from app.repositories.abuse_report import AbuseReportRepository
from app.repositories.ai_usage import AiUsageRepository
from app.repositories.audit import AuditRepository
from app.repositories.category import CategoryRepository
from app.repositories.doc import DocRepository
from app.repositories.message import MessageRepository
from app.repositories.note import NoteRepository
from app.repositories.participant import ParticipantRepository
from app.repositories.room import RoomRepository
from app.repositories.room_ban import RoomBanRepository
from app.repositories.topic import TopicRepository
from app.repositories.user import UserRepository
from app.services.admin import AdminService
from app.services.assistant import AssistantService
from app.services.auth import AuthService
from app.services.category import CategoryService
from app.services.conversation import ConversationService
from app.services.doc import DocService
from app.services.match import MatchService
from app.services.note import NoteService
from app.services.room import RoomService
from app.services.subscription import SubscriptionService
from app.services.topic import TopicService
from app.services.transcription import TranscriptionService
from app.services.translation import TranslationService
from app.services.user import UserService


def get_category_service(session: AsyncSession = Depends(get_session)) -> CategoryService:
    return CategoryService(CategoryRepository(session))


def get_topic_service(session: AsyncSession = Depends(get_session)) -> TopicService:
    # The category repo lets the service reject an unknown category_id.
    return TopicService(TopicRepository(session), CategoryRepository(session))


def get_doc_service(session: AsyncSession = Depends(get_session)) -> DocService:
    return DocService(DocRepository(session), TopicRepository(session))


def get_room_service(session: AsyncSession = Depends(get_session)) -> RoomService:
    return RoomService(
        RoomRepository(session),
        ParticipantRepository(session),
        UserRepository(session),
        RoomBanRepository(session),
        AuditRepository(session),
    )


def get_note_service(session: AsyncSession = Depends(get_session)) -> NoteService:
    return NoteService(NoteRepository(session))


async def get_optional_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """The signed-in user, or None — never raises.

    AI help stays available to anonymous callers (the room demo does not force a
    login), but a signed-in user gets their own plan tier and their own spend
    cap instead of the anonymous defaults.
    """
    if not authorization:
        return None
    try:
        return await get_current_user(authorization, session)
    except NotAuthenticatedError:
        return None


def get_translation_service(
    user: User | None = Depends(get_optional_user),
) -> TranslationService:
    """Wire the translator to its configured engine chain (docs §18.10).

    The user is passed through only so an LLM-backed translation is metered and
    budget-capped against the right account; Google and Argos ignore it.
    """
    return TranslationService(build_translator(user.id if user else None))


def get_assistant_service(
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_optional_user),
) -> AssistantService:
    """Wire the in-room coach to its routed, metered, budget-capped provider.

    Which model actually answers is decided by app/ai/routing.py from the task
    and the caller's plan tier — not here (docs §18.5).
    """
    tier = PlanTier(user.plan) if user else PlanTier.free
    llm, route = build_llm(AiTask.rescue, tier, user_id=user.id if user else None)
    # The doc repo lets the coach ground suggestions in a topic's trusted content.
    return AssistantService(llm, route, DocRepository(session))


def get_transcription_service() -> TranscriptionService:
    """Wire speech-to-text to its configured engine chain (docs §18.10)."""
    return TranscriptionService(build_transcriber())


def get_user_service(session: AsyncSession = Depends(get_session)) -> UserService:
    return UserService(UserRepository(session))


def get_auth_service(session: AsyncSession = Depends(get_session)) -> AuthService:
    return AuthService(UserRepository(session))


def get_subscription_service(
    session: AsyncSession = Depends(get_session),
) -> SubscriptionService:
    return SubscriptionService(UserRepository(session))


def get_conversation_service(
    session: AsyncSession = Depends(get_session),
) -> ConversationService:
    return ConversationService(
        MessageRepository(session),
        RoomRepository(session),
        UserRepository(session),
        ParticipantRepository(session),
    )


def get_match_service(session: AsyncSession = Depends(get_session)) -> MatchService:
    return MatchService(RoomRepository(session))


# --- Authentication / authorization ---------------------------------------
#
# The demo's session token is simply the user's id (see AuthService/AuthResult).
# The client sends it as ``Authorization: Bearer <user-id>``. These dependencies
# resolve that header to a User and enforce the admin gate. Swap the token
# scheme for real JWTs later without changing the endpoints that depend on these.


class NotAuthenticatedError(AppError):
    status_code = 401
    code = "not_authenticated"


class NotAdminError(AppError):
    status_code = 403
    code = "forbidden"


class AccountSuspendedError(AppError):
    """A valid token for an account an admin has switched off."""

    status_code = 403
    code = "account_suspended"


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the bearer JWT to the current user, or raise 401.

    The token must be a valid, unexpired JWT signed with the server secret — a
    raw user id (or any guessed value) no longer authenticates. Admin status is
    re-read from the database, so revoking admin takes effect on the next request.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise NotAuthenticatedError("Sign in to continue.")
    token = authorization[7:].strip()
    claims = decode_access_token(token)
    if claims is None or "sub" not in claims:
        raise NotAuthenticatedError("Invalid or expired session — sign in again.")
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except ValueError as err:
        raise NotAuthenticatedError("Invalid session — sign in again.") from err
    user = await UserRepository(session).get(user_id)
    if user is not None and user.suspended_at is not None:
        # Suspension takes effect on the NEXT request, not at the next login.
        # Tokens are stateless and last 7 days, so checking only at login would
        # leave a suspended account fully working for a week.
        raise AccountSuspendedError(user.suspended_reason or "This account has been suspended.")
    if user is None:
        raise NotAuthenticatedError("Session no longer valid — sign in again.")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Allow only admin users through; raise 403 otherwise."""
    if user.role != UserRole.admin:
        raise NotAdminError("Admins only.")
    return user


# --- WebSocket authentication ---------------------------------------------


async def authenticate_socket(token: str | None) -> tuple[uuid.UUID, str] | None:
    """Resolve a WebSocket's session token to ``(user_id, display_name)``.

    Returns ``None`` when the token is missing, invalid, expired, or names a user
    who no longer exists — the caller then closes with 1008.

    The token arrives as a **query parameter** because a browser cannot set
    headers on a WebSocket handshake. That means it can land in server access
    logs, so keep the expiry short-ish and never log the raw query string.

    Identity comes from the token's ``sub`` claim, never from a `user_id`
    parameter. Accepting a claimed id let anyone connect as anyone and post chat
    and transcript lines under their name (docs/11_Security.md §11.4).
    """
    if not token:
        return None
    claims = decode_access_token(token)
    if claims is None or "sub" not in claims:
        return None
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except ValueError:
        return None
    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get(user_id)
    if user is None:
        return None
    return user.id, user.display_name


def get_admin_service(session: AsyncSession = Depends(get_session)) -> AdminService:
    """Wiring for the admin panel.

    Takes the session itself as well as the repositories: a few of the panel's
    queries are cross-table aggregates (reports per user, topics with no
    questions) that belong to no single repository.
    """
    return AdminService(
        session,
        UserRepository(session),
        AiUsageRepository(session),
        AbuseReportRepository(session),
        RoomBanRepository(session),
        AuditRepository(session),
    )
