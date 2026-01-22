from pydantic import BaseModel

class RecognitionResult(BaseModel):
    product_id: int
    confidence: float
    name: str

class FeedbackResponse(BaseModel):
    message: str