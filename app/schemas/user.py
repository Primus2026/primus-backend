from pydantic import BaseModel, ConfigDict, Field
from app.database.models.user import UserRole

class UserIn(BaseModel):
    login: str = Field(..., description="Unikalna nazwa użytkownika")
    email: str = Field(..., description="Unikalny adres email")
    password: str = Field(..., description="Silne hasło")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "login": "newuser",
                "email": "newuser@example.com",
                "password": "strongpassword123"
            }
        }
    ) 
    

class UserOut(BaseModel):
    id: int 
    login: str 
    email: str 
    role: UserRole 
    is_2fa_enabled: bool 
 
    is_active: bool 

    model_config = ConfigDict(from_attributes=True) 

class UserReceiverOut(BaseModel):
    id: int 
    email: str 

    model_config = ConfigDict(from_attributes=True) 