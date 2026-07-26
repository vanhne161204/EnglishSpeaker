"""Reusable FastAPI dependencies (wiring services to requests)."""

import uuid

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models.user import User
from app.repositories.document import DocumentRepository
from app.repositories.message import MessageRepository
from app.repositories.note import NoteRepository
from app.repositories.participant import ParticipantRepository
from app.repositories.room import RoomRepository
from app.repositories.topic import TopicRepository
from app.repositories.user import UserRepository
from app.services.assistant import AssistantService
from app.services.auth import AuthService
from app.services.conversation import ConversationService
from app.services.document import DocumentService
from app.services.match import MatchService
from app.services.note import NoteService
from app.services.room import RoomService
from app.services.subscription import SubscriptionService
from app.services.topic import TopicService
from app.services.transcription import TranscriptionService
from app.services.translation import TranslationService
from app.services.user import UserService


def get_topic_service(session: AsyncSession = Depends(get_session)) -> TopicService:
    return TopicService(TopicRepository(session))


def get_document_service(session: AsyncSession = Depends(get_session)) -> DocumentService:
    return DocumentService(DocumentRepository(session), TopicRepository(session))


def get_room_service(session: AsyncSession = Depends(get_session)) -> RoomService:
    return RoomService(
        RoomRepository(session),
        ParticipantRepository(session),
        UserRepository(session),
    )


def get_note_service(session: AsyncSession = Depends(get_session)) -> NoteService:
    return NoteService(NoteRepository(session))


def get_translation_service() -> TranslationService:
    return TranslationService()


def get_assistant_service(session: AsyncSession = Depends(get_session)) -> AssistantService:
    # Document repo lets the coach ground suggestions in a topic's trusted content.
    return AssistantService(DocumentRepository(session))


def get_transcription_service() -> TranscriptionService:
    return TranscriptionService()


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
    except ValueError:
        raise NotAuthenticatedError("Invalid session — sign in again.")
    user = await UserRepository(session).get(user_id)
    if user is None:
        raise NotAuthenticatedError("Session no longer valid — sign in again.")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Allow only admin users through; raise 403 otherwise."""
    if not user.is_admin:
        raise NotAdminError("Admins only.")
    return user
