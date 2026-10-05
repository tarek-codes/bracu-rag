import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.auth import UserResponse


class UserRoleUpdateRequest(BaseModel):
    role: Literal["user", "admin"] = Field(..., description="Target user role")


class UserListResponse(BaseModel):
    users: list[UserResponse] = Field(..., description="List of registered users")
    total: int = Field(..., description="Total count of users")


class BulkDeleteRequest(BaseModel):
    ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="User IDs to permanently delete",
    )


class BulkDeleteResponse(BaseModel):
    deleted_count: int = Field(..., description="Number of records permanently deleted")
