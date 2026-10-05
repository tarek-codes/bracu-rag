import uuid
from collections.abc import Callable

import jwt
import structlog
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User, UserRole

logger = structlog.get_logger("auth.deps")
settings = get_settings()


async def get_token_from_request(
    access_token_cookie: str | None = Cookie(default=None, alias="access_token"),
    authorization: str | None = Header(default=None),
) -> str:
    if access_token_cookie:
        return access_token_cookie
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1].strip()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    token: str = Depends(get_token_from_request),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id_str: str | None = payload.get("sub")
        if not user_id_str:
            raise credentials_exception
        user_id = uuid.UUID(user_id_str)
    except (jwt.PyJWTError, ValueError) as exc:
        logger.debug("token_validation_failed", error=str(exc))
        raise credentials_exception from exc

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )
    return user


async def get_optional_current_user(
    access_token_cookie: str | None = Cookie(default=None, alias="access_token"),
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Extract and return user if valid token exists, otherwise return None."""
    token = None
    if access_token_cookie:
        token = access_token_cookie
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()

    if not token:
        return None

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        user_id = uuid.UUID(user_id_str)
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user and user.is_active:
            return user
    except Exception:
        return None
    return None


def require_role(required_role: UserRole) -> Callable[[User], User]:
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role.value:
            logger.warning(
                "insufficient_permissions",
                user_id=str(current_user.id),
                user_role=current_user.role,
                required_role=required_role.value,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires {required_role.value} privileges",
            )
        return current_user

    return role_checker


# Convenient dependency aliases
require_admin = require_role(UserRole.ADMIN)
require_user = require_role(UserRole.USER)
