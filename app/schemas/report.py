from datetime import datetime
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

class ReportType(Enum):
    EXPIRY = "expiry"
    AUDIT = "audit"
    TEMP = "temp"
    

class ReportResponse(BaseModel):
    """Response model for a single report file."""
    filename: str
    created_at: datetime
    size_bytes: int

class ReportStatusResponse(BaseModel):
    """Response model for the status of a report generation task."""
    task_id: str
    status: str
    result: Optional[dict] = None
    download_url: Optional[str] = None
    error: Optional[str] = None

class ReportGenerateResponse(BaseModel):
    """Response model for triggering a report generation."""
    task_id: str
    message: str

class ReportFilter(BaseModel):
    """Optional filters for report generation."""
    rack_id: Optional[int] = Field(None, description="Filtruj przedmioty po konkretnym ID regału (opcjonalne)")
    barcode: Optional[str] = Field(None, description="Filtruj przedmioty po kodzie kreskowym produktu (opcjonalne)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "rack_id": 1,
                "barcode": "5901234567890"
            }
        }
    )
