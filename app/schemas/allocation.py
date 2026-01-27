from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID

class AllocationRequest(BaseModel):
    barcode: str = Field(..., description="Barcode of the product to allocate")

class AllocationResponse(BaseModel):
    rack_id: int
    rack_designation: str
    row: int
    col: int

    model_config = ConfigDict(from_attributes=True)
