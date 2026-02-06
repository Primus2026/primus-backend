from pydantic import BaseModel, validator, Field, ConfigDict
from typing import List, Optional 
from app.database.models.product_definition import FrequencyClass 

class ProductDefinitionIn(BaseModel):
    name: str = Field(..., description="Nazwa produktu/asortymentu")
    barcode: str = Field(..., description="Unikalny kod kreskowy lub identyfikator QR")
    req_temp_min: float = Field(..., description="Minimalna wymagana temperatura przechowywania (°C)")
    req_temp_max: float = Field(..., description="Maksymalna wymagana temperatura przechowywania (°C)")
    weight_kg: float = Field(..., description="Waga jednostkowa (kg)")
    dims_x_mm: int = Field(..., description="Szerokość (mm)")
    dims_y_mm: int = Field(..., description="Wysokość (mm)")
    dims_z_mm: int = Field(..., description="Głębokość (mm)")
    is_dangerous: bool = Field(..., description="Czy przedmiot jest niebezpieczny/szkodliwy")
    comment: str = Field(..., description="Dodatkowe uwagi lub instrukcje obsługi")
    expiry_days: int = Field(..., description="Okres przydatności w dniach od przyjęcia")

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

class ProductDefinitionUpdate(BaseModel):
    name: Optional[str] = None
    barcode: Optional[str] = None
    req_temp_min: Optional[float] = None
    req_temp_max: Optional[float] = None
    weight_kg: Optional[float] = None
    dims_x_mm: Optional[int] = None
    dims_y_mm: Optional[int] = None
    dims_z_mm: Optional[int] = None
    is_dangerous: Optional[bool] = None
    comment: Optional[str] = None
    expiry_days: Optional[int] = None
    frequency_class: Optional[FrequencyClass] = None

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
    frequency_class: FrequencyClass

    @validator("photo_path", pre=True, always=True)
    def resolve_photo_url(cls, v):
        if v:
            from app.core.storage import storage
            return storage.get_url(v)
        return v

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
            raise ValueError("TempMax musi być większe niż TempMin")
        return v

    @validator("dims_x_mm", "dims_y_mm", "dims_z_mm")
    def validate_positive_int(cls, v):
        if v <= 0:
            raise ValueError("Musi być dodatnią liczbą całkowitą")
        return v

    @validator("weight_kg")
    def validate_positive_float(cls, v):
        if v <= 0:
            raise ValueError("Musi być dodatnią liczbą zmiennoprzecinkową")
        return v
    
    @validator("expiry_days")
    def validate_expiry_days(cls, v):
        if v <= 0:
            raise ValueError("Musi być dodatnią liczbą całkowitą")
        return v


class ProductImportSummary(BaseModel):
    total_processed: int = Field(0, description="Całkowita liczba przetworzonych wierszy")
    created_count: int = Field(0, description="Liczba utworzonych wierszy")
    updated_count: int = Field(0, description="Liczba zaktualizowanych wierszy")
    skipped_count: int = Field(0, description="Liczba pominiętych wierszy")
    skipped_details: List[dict] = Field([], description="Szczegóły pominiętych wierszy")
    success_count: int = Field(0, description="Liczba pomyślnie zaimportowanych (Legacy)")
    error_count: int = Field(0, description="Liczba błędnych (Legacy)")
    errors: List[str] = Field([], description="Lista komunikatów błędów")
    successes: List[dict] = Field([], description="Szczegóły udanych importów")


class ProductImportResult(BaseModel):
    message: Optional[str] = Field(None, description="Komunikat wyniku")
    summary: Optional[ProductImportSummary] = Field(None, description="Statystyki importu")
    status: Optional[str] = Field(None, description="Status zadania (np. SUCCESS, FAILURE)")
    error: Optional[str] = Field(None, description="Ogólny komunikat błędu")
    task_id: Optional[str] = Field(None, description="ID zadania Celery")