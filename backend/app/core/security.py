import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Response

from app.core.config import get_settings

settings = get_settings()

pwd_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return pwd_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_hasher.verify(hashed_password, plain_password)
    except VerifyMismatchError:
        return False


def create_access_token(subject: str, role: str, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES)

    to_encode: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_DAYS)

    to_encode: dict[str, Any] = {
        "sub": subject,
        "type": "refresh",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
) -> None:
    is_production = settings.ENVIRONMENT == "production"

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_MINUTES * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    is_production = settings.ENVIRONMENT == "production"

    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=is_production,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=is_production,
        samesite="lax",
        path="/",
    )
