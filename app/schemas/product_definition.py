from pydantic import BaseModel, validator, Field
from typing import List, Optional 

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
    comment: str
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
    comment: str
    expiry_days: int


class ProductDefinitionCSVRow(BaseModel):
    name: str = Field(..., alias="Nazwa")
    barcode: str = Field(..., alias="Id")
    photo_path: str = Field(..., alias="Zdjecie")
    req_temp_min: float = Field(..., alias="TempMin")
    req_temp_max: float = Field(..., alias="TempMax")
    weight_kg: float = Field(..., alias="Waga")
    dims_x_mm: int = Field(..., alias="SzerokoscMm")
    dims_y_mm: int = Field(..., alias="WysokoscMm")
    dims_z_mm: int = Field(..., alias="GlebokoscMm")
    comment: str = Field(..., alias="Komentarz")
    expiry_days: int = Field(..., alias="TerminWaznosciDni")
    is_dangerous: bool = Field(..., alias="CzyNiebezpieczny")

    @validator("req_temp_max")
    def validate_temp_range(cls, v, values):
        if "req_temp_min" in values and v < values["req_temp_min"]:
            raise ValueError("TempMax must be greater than TempMin")
        return v

    @validator("dims_x_mm", "dims_y_mm", "dims_z_mm")
    def validate_positive_int(cls, v):
        if v <= 0:
            raise ValueError("Must be a positive integer")
        return v

    @validator("weight_kg")
    def validate_positive_float(cls, v):
        if v <= 0:
            raise ValueError("Must be a positive float")
        return v
    
    @validator("expiry_days")
    def validate_expiry_days(cls, v):
        if v <= 0:
            raise ValueError("Must be a positive integer")
        return v


class ImportSummary(BaseModel):
    total_processed: int = 0
    success_count: int = 0
    error_count: int = 0
    errors: List[str] = []


class ImportResult(BaseModel):
    message: Optional[str] = None
    summary: Optional[ImportSummary] = None
    status: Optional[str] = None
    error: Optional[str] = None
    task_id: Optional[str] = None