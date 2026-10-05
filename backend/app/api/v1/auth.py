from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.security import clear_auth_cookies, set_auth_cookies
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.auth import (
    MessageResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register New User",
    description="Registers a new standard user account with email and password.",
)
async def register(
    payload: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await AuthService.register_user(
        db=db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=UserRole.USER,
    )
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="User Login",
    description="Authenticates user credentials and sets secure httpOnly session cookies.",
)
async def login(
    payload: UserLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    user = await AuthService.authenticate_user(
        db=db,
        email=payload.email,
        password=payload.password,
    )
    access_token, refresh_token = await AuthService.create_tokens_for_user(db, user)
    set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh Session Token",
    description="Rotates refresh token and issues a new access token via httpOnly cookie.",
)
async def refresh_token(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token cookie missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    new_access, new_refresh, user = await AuthService.refresh_tokens(db, refresh_token)
    set_auth_cookies(response, new_access, new_refresh)

    return TokenResponse(
        access_token=new_access,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="User Logout",
    description="Revokes current refresh token and clears session cookies.",
)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    if refresh_token:
        await AuthService.revoke_token(db, refresh_token)

    clear_auth_cookies(response)
    return MessageResponse(message="Successfully logged out")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Current User Profile",
    description="Retrieves the currently authenticated user's profile.",
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(current_user)
