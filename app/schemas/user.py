from pydantic import BaseModel

class UserIn(BaseModel):
    login: str 
    email: str 
    password: str 
    

class UserOut(BaseModel):
    id: int 
    login: str 
    email: str 
    role: str 
    is_2fa_enabled: bool 