from pydantic import BaseModel, field_validator, model_validator, Field
from typing import Optional

class RackValidatorMixin(BaseModel):
    @field_validator("max_weight_kg", "max_dims_x_mm", "max_dims_y_mm", "max_dims_z_mm", "rows_m", "cols_n", "distance_from_exit_m", check_fields=False)
    @classmethod
    def check_positive_values(cls, v):
        if v is not None and v <= 0:
             raise ValueError("Value must be greater than 0")
        return v

    @model_validator(mode='after')
    def check_temp_min_max(self):
        temp_min = self.temp_min
        temp_max = self.temp_max
        
        # Check if both are present in the model (for RackBase/Create) or set (updated)
        if temp_min is not None and temp_max is not None:
             if temp_min > temp_max:
                raise ValueError("temp_min cannot be greater than temp_max")
        return self

# 1. Base class for common fields
class RackBase(RackValidatorMixin):
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

class RackUpdate(RackValidatorMixin):
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