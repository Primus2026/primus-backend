from pydantic import BaseModel


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
