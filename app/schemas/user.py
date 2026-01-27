from pydantic import BaseModel, ConfigDict, Field
from app.database.models.user import UserRole

class UserIn(BaseModel):
    login: str = Field(..., description="Unique username")
    email: str = Field(..., description="Unique email address")
    password: str = Field(..., description="Strong password")

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