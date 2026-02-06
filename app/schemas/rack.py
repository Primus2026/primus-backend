from pydantic import BaseModel, field_validator, model_validator, Field, ConfigDict, ValidationInfo
from typing import Optional, List

class RackValidatorMixin(BaseModel):
    @field_validator("max_weight_kg", "max_dims_x_mm", "max_dims_y_mm", "max_dims_z_mm", "rows_m", "cols_n", "distance_from_exit_m", check_fields=False)
    @classmethod
    def check_positive_values(cls, v):
        if v is not None and v <= 0:
             raise ValueError("Wartość musi być większa od 0")
        return v

    @model_validator(mode='after')
    def check_temp_min_max(self):
        temp_min = self.temp_min
        temp_max = self.temp_max
        
        # Check if both are present in the model (for RackBase/Create) or set (updated)
        if temp_min is not None and temp_max is not None:
             if temp_min > temp_max:
                raise ValueError("temp_min nie może być większe niż temp_max")
        return self

# 1. Base class for common fields
class RackBase(RackValidatorMixin):
    designation: str = Field(..., description="Unikalny kod/oznaczenie regału (np. R-01)")
    rows_m: int = Field(..., description="Liczba rzędów (poziomów wysokości)")
    cols_n: int = Field(..., description="Liczba kolumn (slotów na poziom)")
    temp_min: float = Field(..., description="Minimalna dopuszczalna temperatura (°C)")
    temp_max: float = Field(..., description="Maksymalna dopuszczalna temperatura (°C)")
    max_weight_kg: float = Field(..., description="Maksymalna nośność (kg)")
    max_dims_x_mm: int = Field(..., description="Maksymalna szerokość przedmiotu (mm)")
    max_dims_y_mm: int = Field(..., description="Maksymalna wysokość przedmiotu (mm)")
    max_dims_z_mm: int = Field(..., description="Maksymalna głębokość przedmiotu (mm)")
    comment: Optional[str] = Field(None, description="Opcjonalny opis lub uwagi")
    distance_from_exit_m: Optional[float] = Field(None, description="Odległość od głównego wyjścia (metry)")


class RackCreate(RackBase):
    pass

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "designation": "R-101",
                "rows_m": 5,
                "cols_n": 10,
                "temp_min": 18.0,
                "temp_max": 25.0,
                "max_weight_kg": 500.0,
                "max_dims_x_mm": 1000,
                "max_dims_y_mm": 500,
                "max_dims_z_mm": 500,
                "comment": "Main storage rack",
                "distance_from_exit_m": 15.5
            }
        }
    )

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


class RackSlotWeight(BaseModel):
    row: int
    col: int
    current_weight: float

class RackWithInventory(RackOut):
    active_slots: List[RackSlotWeight] = []


# CSV Import Schemas
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

    @field_validator("temp_max")
    @classmethod
    def validate_temp_range_csv(cls, v, info: ValidationInfo):
        # NOTE: field_validator context 'info' usage differs from v1 'values'
        # 'info.data' contains previously validated fields. 
        # But 'temp_min' might not be in 'info.data' if it failed validation or order differs?
        # Pydantic v2: "check_fields=False" isn't needed here if we rely on standard behavior?
        # Standard behavior: validated fields are in info.data
        if "temp_min" in info.data and v < info.data["temp_min"]:
            raise ValueError("TempMax musi być większe niż TempMin")
        return v

    @field_validator("rows", "cols", "max_width", "max_height", "max_depth")
    @classmethod
    def validate_positive_int(cls, v):
        if v <= 0:
            raise ValueError("Musi być dodatnią liczbą całkowitą")
        return v
    
    @field_validator("max_weight")
    @classmethod
    def validate_positive_float(cls, v):
        if v <= 0:
            raise ValueError("Musi być dodatnią liczbą zmiennoprzecinkową")
        return v

class RackImportSummary(BaseModel):
    created_count: int = Field(0, description="Liczba nowo utworzonych regałów")
    updated_count: int = Field(0, description="Liczba zaktualizowanych istniejących regałów")
    skipped_count: int = Field(0, description="Liczba pominiętych wierszy")
    skipped_details: List[str] = Field([], description="Szczegóły pominiętych wierszy")

class RackImportResult(BaseModel):
    message: Optional[str] = Field(None, description="Komunikat wyniku")
    summary: Optional[RackImportSummary] = Field(None, description="Statystyki importu")
    status: Optional[str] = Field(None, description="Status zadania")
    error: Optional[str] = Field(None, description="Komunikat błędu jeśli wystąpił")
    task_id: Optional[str] = Field(None, description="ID zadania Celery")