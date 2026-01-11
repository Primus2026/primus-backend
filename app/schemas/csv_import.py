from pydantic import BaseModel, validator, Field
from typing import List, Optional

class RackCSVRow(BaseModel):
    designation: str = Field(..., alias="Oznaczenie")
    rows: int = Field(..., alias="M")
    cols: int = Field(..., alias="N")
    temp_min: float = Field(..., alias="TempMin")
    temp_max: float = Field(..., alias="TempMax")
    max_weight: float = Field(..., alias="MaxWagaKg")
    max_width: int = Field(..., alias="MaxSzerokoscMm")
    max_height: int = Field(..., alias="MaxWysokoscMm")
    max_depth: int = Field(..., alias="MaxGlebokoscMm")
    comment: Optional[str] = Field(None, alias="Komentarz")

    @validator("temp_max")
    def validate_temp_range(cls, v, values):
        if "temp_min" in values and v < values["temp_min"]:
            raise ValueError("TempMax must be greater than TempMin")
        return v

    @validator("rows", "cols", "max_width", "max_height", "max_depth")
    def validate_positive_int(cls, v):
        if v <= 0:
            raise ValueError("Must be a positive integer")
        return v
    
    @validator("max_weight")
    def validate_positive_float(cls, v):
        if v <= 0:
            raise ValueError("Must be a positive float")
        return v

class ImportSummary(BaseModel):
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    skipped_details: List[str] = []

class ImportResult(BaseModel):
    message: str
    summary: ImportSummary
