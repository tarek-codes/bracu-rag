import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import UserResponse
from app.schemas.user import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    UserListResponse,
    UserRoleUpdateRequest,
)

logger = structlog.get_logger("api.users")

router = APIRouter(prefix="/users", tags=["User Management"])


@router.get(
    "",
    response_model=UserListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Users (Admin Only)",
    description="Retrieves a paginated list of all users. Requires admin privileges.",
)
async def list_users(
    skip: int = Query(default=0, ge=0, description="Offset"),
    limit: int = Query(default=50, ge=1, le=100, description="Page size"),
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    total_query = await db.execute(select(func.count(User.id)))
    total = total_query.scalar_one()

    users_query = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    )
    users = users_query.scalars().all()

    return UserListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=total,
    )


@router.delete(
    "/bulk",
    response_model=BulkDeleteResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk Delete Users (Admin Only)",
    description="Permanently deletes selected user accounts and their related data. The current admin account cannot be deleted.",
)
async def bulk_delete_users(
    payload: BulkDeleteRequest,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> BulkDeleteResponse:
    if admin_user.id in payload.ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The currently signed-in admin account cannot be deleted",
        )

    result = await db.execute(select(User).where(User.id.in_(set(payload.ids))))
    users = result.scalars().all()
    for user in users:
        await db.delete(user)
    await db.commit()

    logger.info(
        "users_bulk_deleted",
        deleted_count=len(users),
        deleted_by=str(admin_user.id),
    )
    return BulkDeleteResponse(deleted_count=len(users))


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get User Details (Admin Only)",
    description="Fetches details for a specific user ID. Requires admin privileges.",
)
async def get_user_by_id(
    user_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserResponse.model_validate(user)


@router.patch(
    "/{user_id}/role",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Update User Role (Admin Only)",
    description="Modifies a user's role (user or admin). Requires admin privileges.",
)
async def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdateRequest,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent admin from demoting themselves
    if user.id == admin_user.id and payload.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admins cannot revoke their own admin privileges",
        )

    user.role = payload.role
    await db.commit()
    await db.refresh(user)

    logger.info(
        "user_role_updated",
        target_user_id=str(user.id),
        new_role=user.role,
        updated_by=str(admin_user.id),
    )
    return UserResponse.model_validate(user)
