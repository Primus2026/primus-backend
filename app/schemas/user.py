from pydantic import BaseModel
from app.database.models.user import UserRole

class UserIn(BaseModel):
    login: str 
    email: str 
    password: str 
    

class UserOut(BaseModel):
    id: int 
    login: str 
    email: str 
    role: UserRole 
    is_2fa_enabled: bool 
    is_active: bool 