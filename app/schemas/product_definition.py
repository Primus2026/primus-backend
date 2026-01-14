from pydantic import BaseModel
class ProductDefinitionIn(BaseModel):
    name: str
    barcode: str
    req_temp_min: float
    req_temp_max: float
    weight_kg: float
    dims_x_mm: int
    dims_y_mm: int
    dims_z_mm: int
    is_dangerous: bool
    expiry_days: int

class ProductDefinitionOut(BaseModel):
    id: int
    name: str
    barcode: str
    photo_path: str
    req_temp_min: float
    req_temp_max: float
    weight_kg: float
    dims_x_mm: int
    dims_y_mm: int
    dims_z_mm: int
    is_dangerous: bool
    expiry_days: int


