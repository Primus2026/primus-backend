from pydantic import BaseModel, validator, Field, ConfigDict
from typing import List, Optional 

class ProductDefinitionIn(BaseModel):
    name: str = Field(..., description="Name of the product/assortment")
    barcode: str = Field(..., description="Unique barcode or QR code identifier")
    req_temp_min: float = Field(..., description="Minimum required storage temperature (°C)")
    req_temp_max: float = Field(..., description="Maximum required storage temperature (°C)")
    weight_kg: float = Field(..., description="Weight per unit (kg)")
    dims_x_mm: int = Field(..., description="Width (mm)")
    dims_y_mm: int = Field(..., description="Height (mm)")
    dims_z_mm: int = Field(..., description="Depth (mm)")
    is_dangerous: bool = Field(..., description="Whether the item is hazardous/dangerous")
    comment: str = Field(..., description="Additional notes or handling instructions")
    expiry_days: int = Field(..., description="Shelf life in days from reception")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Standard Widget",
                "barcode": "1234567890123",
                "req_temp_min": 5.0,
                "req_temp_max": 25.0,
                "weight_kg": 1.5,
                "dims_x_mm": 100,
                "dims_y_mm": 50,
                "dims_z_mm": 50,
                "is_dangerous": False,
                "comment": "Fragile item",
                "expiry_days": 365
            }
        }
    )

class ProductDefinitionOut(BaseModel):
    id: int
    name: str
    barcode: str
    photo_path: Optional[str] = None
    req_temp_min: float
    req_temp_max: float
    weight_kg: float
    dims_x_mm: int
    dims_y_mm: int
    dims_z_mm: int
    is_dangerous: bool
    comment: Optional[str] = None
    expiry_days: int

    model_config = ConfigDict(from_attributes=True)


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


class ProductImportSummary(BaseModel):
    total_processed: int = Field(0, description="Total rows processed")
    success_count: int = Field(0, description="Rows successfully imported")
    error_count: int = Field(0, description="Rows failed")
    errors: List[str] = Field([], description="List of error messages")
    successes: List[dict] = Field([], description="Details of successful imports")


class ProductImportResult(BaseModel):
    message: Optional[str] = Field(None, description="Result message")
    summary: Optional[ProductImportSummary] = Field(None, description="Import statistics")
    status: Optional[str] = Field(None, description="Task status (e.g. SUCCESS, FAILURE)")
    error: Optional[str] = Field(None, description="Generic error message")
    task_id: Optional[str] = Field(None, description="Celery task ID")