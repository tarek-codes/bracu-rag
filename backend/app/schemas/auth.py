import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address", examples=["student@example.com"])
    password: str = Field(
        ...,
        min_length=8,
        description="Password with minimum 8 characters",
        examples=["correct-horse-battery-staple"],
    )
    full_name: str | None = Field(
        default=None,
        max_length=255,
        description="Full name",
        examples=["Ayesha Rahman"],
    )


class UserLoginRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address", examples=["student@example.com"])
    password: str = Field(
        ..., description="User password", examples=["correct-horse-battery-staple"]
    )


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="User ID")
    email: EmailStr = Field(..., description="User email address")
    full_name: str | None = Field(default=None, description="Full name")
    role: str = Field(..., description="User role ('user' or 'admin')")
    is_active: bool = Field(..., description="Account active status")
    created_at: datetime = Field(..., description="Account creation timestamp")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="Short-lived JWT access token")
    token_type: str = Field(default="bearer", description="Token type", examples=["bearer"])
    user: UserResponse = Field(..., description="User profile")


class MessageResponse(BaseModel):
    message: str = Field(..., description="Status message")
