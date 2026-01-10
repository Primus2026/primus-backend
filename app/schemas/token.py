from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    token_type: str
    is_2fa_required: bool = False

class TokenPayload(BaseModel):
    sub: str | None = None
