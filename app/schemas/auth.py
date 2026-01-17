from pydantic import BaseModel, field_validator, ValidationInfo, ConfigDict, Field


class TwoFactorSetupResponse(BaseModel):
    secret: str
    qr_code_url: str
    qr_code_image: str


class TwoFactorVerifyRequest(BaseModel):
    code: str


class TwoFactorLoginRequest(BaseModel):
    token: str
    code: str


class Token(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(..., description="Token type, e.g., 'bearer'")
    is_2fa_required: bool = Field(False, description="Whether 2FA verification is pending")


class TokenPayload(BaseModel):
    sub: str | None = None


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(..., description="Current active password")
    new_password: str = Field(..., description="New password (min 8 chars)")
    confirm_password: str = Field(..., description="Repeat new password for confirmation")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "old_password": "oldSecretPassword123",
                "new_password": "newSecretPassword456",
                "confirm_password": "newSecretPassword456"
            }
        }
    )

    @field_validator("new_password")
    @classmethod
    def validate_password_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

    @field_validator("confirm_password")
    @classmethod
    def validate_passwords_match(cls, v: str, info: ValidationInfo) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match")
        return v
