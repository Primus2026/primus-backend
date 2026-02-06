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
    access_token: str = Field(..., description="Token dostępu JWT")
    token_type: str = Field(..., description="Typ tokena, np. 'bearer'")
    is_2fa_required: bool = Field(False, description="Czy wymagana jest weryfikacja 2FA")


class TokenPayload(BaseModel):
    sub: str | None = None


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(..., description="Obecne aktywne hasło")
    new_password: str = Field(..., description="Nowe hasło (min 8 znaków)")
    confirm_password: str = Field(..., description="Powtórz nowe hasło dla potwierdzenia")

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
            raise ValueError("Hasło musi mieć co najmniej 8 znaków")
        return v

    @field_validator("confirm_password")
    @classmethod
    def validate_passwords_match(cls, v: str, info: ValidationInfo) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Hasła nie są identyczne")
        return v
