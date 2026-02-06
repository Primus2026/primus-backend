from app.schemas.user import UserReceiverOut
from app.schemas.rack import RackOut
from datetime import datetime, date 
from app.schemas.product_definition import ProductDefinitionOut
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional

class RackLocation(BaseModel):
    designation: str = Field(..., description="Oznaczenie regału")
    row: int = Field(..., description="Rząd pozycji (wysokość)")
    col: int = Field(..., description="Kolumna pozycji")

class RackLocationManual(BaseModel):
    rack_id: int = Field(..., description="ID regału")
    row: int = Field(..., description="Rząd pozycji")
    col: int = Field(..., description="Kolumna pozycji")

from uuid import UUID

class StockOut(BaseModel):
    id: UUID
    product: ProductDefinitionOut
    rack_id: int 
    position_row: int 
    position_col: int 
    entry_date: datetime
    expiry_date: date
    received_by: UserReceiverOut

    model_config = ConfigDict(from_attributes=True)

class StockItemSimpleOut(BaseModel):
    id: UUID
    rack_id: int
    position_row: int
    position_col: int
    entry_date: datetime
    expiry_date: date
    received_by: UserReceiverOut
    rack: RackOut

    model_config = ConfigDict(from_attributes=True)

class ProductStockGroup(BaseModel):
    product: ProductDefinitionOut
    stock_items: list[StockItemSimpleOut]

    model_config = ConfigDict(from_attributes=True)