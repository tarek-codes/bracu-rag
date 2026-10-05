import uuid
from datetime import UTC, datetime

import jwt
import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import RefreshToken, User, UserRole

logger = structlog.get_logger("services.auth")


class AuthService:
    @staticmethod
    async def register_user(
        db: AsyncSession,
        email: str,
        password: str,
        full_name: str | None = None,
        role: UserRole = UserRole.USER,
    ) -> User:
        normalized_email = email.lower().strip()
        existing = await db.execute(select(User).where(User.email == normalized_email))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email address already exists",
            )

        hashed = hash_password(password)
        user = User(
            email=normalized_email,
            hashed_password=hashed,
            full_name=full_name,
            role=role.value,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        logger.info("user_registered", user_id=str(user.id), email=user.email, role=user.role)
        return user

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        email: str,
        password: str,
    ) -> User:
        normalized_email = email.lower().strip()
        result = await db.execute(select(User).where(User.email == normalized_email))
        user = result.scalar_one_or_none()

        if not user or not verify_password(password, user.hashed_password):
            logger.warning("authentication_failed", email=normalized_email)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user account",
            )

        logger.info("user_authenticated", user_id=str(user.id), email=user.email)
        return user

    @staticmethod
    async def create_tokens_for_user(
        db: AsyncSession,
        user: User,
    ) -> tuple[str, str]:
        user_id_str = str(user.id)
        access_token = create_access_token(subject=user_id_str, role=user.role)
        refresh_token = create_refresh_token(subject=user_id_str)

        decoded = decode_token(refresh_token)
        exp_timestamp = decoded["exp"]
        expires_at = datetime.fromtimestamp(exp_timestamp, tz=UTC)

        db_refresh_token = RefreshToken(
            user_id=user.id,
            token=refresh_token,
            expires_at=expires_at,
        )
        db.add(db_refresh_token)
        await db.commit()

        return access_token, refresh_token

    @staticmethod
    async def refresh_tokens(
        db: AsyncSession,
        refresh_token_str: str,
    ) -> tuple[str, str, User]:
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

        try:
            payload = decode_token(refresh_token_str)
            if payload.get("type") != "refresh":
                raise credentials_exception
            user_id = uuid.UUID(payload.get("sub", ""))
        except (jwt.PyJWTError, ValueError) as exc:
            raise credentials_exception from exc

        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.token == refresh_token_str,
                RefreshToken.revoked.is_(False),
            )
        )
        stored_token = result.scalar_one_or_none()

        if not stored_token or stored_token.expires_at < datetime.now(UTC):
            if stored_token:
                stored_token.revoked = True
                await db.commit()
            raise credentials_exception

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user or not user.is_active:
            raise credentials_exception

        # Rotate refresh token: revoke current and issue a new pair
        stored_token.revoked = True
        new_access_token, new_refresh_token = await AuthService.create_tokens_for_user(db, user)

        return new_access_token, new_refresh_token, user

    @staticmethod
    async def revoke_token(
        db: AsyncSession,
        refresh_token_str: str,
    ) -> None:
        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token == refresh_token_str)
        )
        stored_token = result.scalar_one_or_none()
        if stored_token:
            stored_token.revoked = True
            await db.commit()
            logger.info("refresh_token_revoked", token_id=str(stored_token.id))
