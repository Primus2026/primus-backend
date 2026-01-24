from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any


class RecognitionResult(BaseModel):
    product_id: int = Field(
        ..., description="The unique identifier of the recognized product"
    )
    confidence: float = Field(
        ..., description="The confidence score of the recognition (0.0 to 1.0)"
    )
    name: str = Field(..., description="The name of the recognized product")
    barcode: str = Field(..., description="The barcode of the recognized product")

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
    success: bool = Field(..., description="Indicates if the operation was successful")
    message: str = Field(
        ..., description="A message describing the result of the operation"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"success": True, "message": "Feedback saved successfully"}
        }
    )


class TaskStatusResponse(BaseModel):
    task_id: str = Field(
        ..., description="The unique identifier of the background task"
    )
    status: str = Field(
        ...,
        description="The current status of the task (PENDING, STARTED, SUCCESS, FAILURE)",
    )
    result: RecognitionResult | Dict[str, Any] | None = Field(
        None, description="The result of the task if completed"
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
        ..., description="The unique identifier of the background task"
    )
