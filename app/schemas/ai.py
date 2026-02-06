from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any


class RecognitionResult(BaseModel):
    product_id: int = Field(
        ..., description="Unikalny identyfikator rozpoznanego produktu"
    )
    confidence: float = Field(
        ..., description="Poziom pewności rozpoznania (0.0 do 1.0)"
    )
    name: str = Field(..., description="Nazwa rozpoznanego produktu")
    barcode: str = Field(..., description="Kod kreskowy rozpoznanego produktu")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "product_id": 101,
                "confidence": 0.98,
                "name": "Milk 3.2%",
                "barcode": "1234567890123",
            }
        }
    )


class FeedbackResponse(BaseModel):
    success: bool = Field(..., description="Czy operacja zakończyła się sukcesem")
    message: str = Field(
        ..., description="Komunikat opisujący wynik operacji"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"success": True, "message": "Feedback saved successfully"}
        }
    )


class TaskStatusResponse(BaseModel):
    task_id: str = Field(
        ..., description="Unikalny identyfikator zadania w tle"
    )
    status: str = Field(
        ...,
        description="Obecny status zadania (PENDING, STARTED, SUCCESS, FAILURE)",
    )
    result: RecognitionResult | Dict[str, Any] | None = Field(
        None, description="Wynik zadania jeśli zakończone"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "task_id": "c2013-1234-5678",
                "status": "SUCCESS",
                "result": {"product_id": 101, "confidence": 0.98, "name": "Milk 3.2%"},
            }
        }
    )


class TaskRequestResponse(BaseModel):
    task_id: str = Field(
        ..., description="Unikalny identyfikator zadania w tle"
    )
