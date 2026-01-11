from pydantic import BaseModel
from typing import Optional

# 1. Base class for common fields
class RackBase(BaseModel):
    designation: str
    rows_m: int
    cols_n: int
    temp_min: float
    temp_max: float
    max_weight_kg: float
    max_dims_x_mm: int
    max_dims_y_mm: int
    max_dims_z_mm: int
    comment: Optional[str] = None
    distance_from_exit_m: Optional[float] = None

class RackCreate(RackBase):
    pass

class RackUpdate(BaseModel):
    id: int 
    designation: Optional[str] = None
    rows_m: Optional[int] = None
    cols_n: Optional[int] = None
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None
    max_weight_kg: Optional[float] = None
    max_dims_x_mm: Optional[int] = None
    max_dims_y_mm: Optional[int] = None
    max_dims_z_mm: Optional[int] = None
    comment: Optional[str] = None
    distance_from_exit_m: Optional[float] = None

class RackOut(BaseModel):
    id: int
    designation: str
    rows_m: int
    cols_n: int
    temp_min: float
    temp_max: float
    max_weight_kg: float
    max_dims_x_mm: int
    max_dims_y_mm: int
    max_dims_z_mm: int
    comment: Optional[str] = None
    distance_from_exit_m: Optional[float] = None