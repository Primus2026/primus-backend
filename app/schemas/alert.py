from pydantic import BaseModel, ConfigDict
from datetime import datetime
from app.database.models.alert import AlertType
from typing import Optional

class AlertBase(BaseModel):
    alert_type: AlertType
    rack_id: Optional[int] = None
    product_id: Optional[int] = None
    message: str
    last_valid_weight: Optional[float] = None
    position_row: Optional[int] = None
    position_col: Optional[int] = None
    is_resolved: bool = False

class AlertCreate(AlertBase):
    pass

class AlertOut(AlertBase):
    id: int
    created_at: datetime
    is_sent: bool

    model_config = ConfigDict(from_attributes=True)
