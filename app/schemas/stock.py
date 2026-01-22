from pydantic import BaseModel, ConfigDict, Field
from typing import Optional

class RackLocation(BaseModel):
    designation: str = Field(..., description="Rack designation")
    row: int = Field(..., description="Item's position row")
    col: int = Field(..., description="Item's position column")


