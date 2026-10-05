from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(
        ...,
        description="Overall service health status",
        examples=["ok", "degraded"],
    )
    version: str = Field(
        ...,
        description="API version",
        examples=["0.1.0"],
    )
    environment: str = Field(
        ...,
        description="Running environment",
        examples=["development", "production"],
    )
    database: str = Field(
        ...,
        description="Database connectivity status",
        examples=["connected", "disconnected", "unreachable"],
    )
    details: dict[str, str] | None = Field(
        default=None,
        description="Detailed component statuses",
    )
