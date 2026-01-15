from pydantic import BaseModel, field_validator, ValidationInfo


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
    access_token: str
    token_type: str
    is_2fa_required: bool = False


class TokenPayload(BaseModel):
    sub: str | None = None


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str

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
