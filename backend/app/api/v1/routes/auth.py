"""Username/password auth endpoints (optional login on top of the device profile)."""

from fastapi import APIRouter, Depends

from app.api.deps import get_auth_service
from app.core.rate_limit import rate_limiter
from app.core.security import create_access_token
from app.schemas.auth import AuthResult, LoginRequest, RegisterRequest
from app.schemas.user import UserRead
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=AuthResult,
    summary="Create an account",
    # Throttle signups per IP to curb bot/spam account creation.
    dependencies=[Depends(rate_limiter(max_requests=5, window_seconds=600))],
)
async def register(
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthResult:
    user = await service.register(payload.username, payload.password, payload.display_name)
    token = create_access_token(user.id, user.is_admin)
    return AuthResult(user=UserRead.model_validate(user), token=token)


@router.post(
    "/login",
    response_model=AuthResult,
    summary="Log in with username and password",
    # Throttle login attempts per IP to slow password guessing.
    dependencies=[Depends(rate_limiter(max_requests=10, window_seconds=60))],
)
async def login(
    payload: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthResult:
    user = await service.login(payload.username, payload.password)
    token = create_access_token(user.id, user.is_admin)
    return AuthResult(user=UserRead.model_validate(user), token=token)


@router.post("/logout", summary="Log out")
async def logout() -> dict[str, bool]:
    # The token is stateless (just the user id), so there is nothing to revoke
    # server-side — the client clears its stored identity. This endpoint exists
    # so the flow is complete and stays stable if real sessions are added later.
    return {"ok": True}
