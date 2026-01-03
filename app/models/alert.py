from enum import Enum
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, Text, DateTime, ForeignKey, Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base

class AlertType(str, Enum):
    TEMP = 'TEMP'
    WEIGHT = 'WEIGHT'
    EXPIRY = 'EXPIRY'
    THEFT = 'THEFT'

class Alert(Base):
    __tablename__ = 'alerts'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    alert_type: Mapped[AlertType] = mapped_column(SQLAlchemyEnum(AlertType))
    rack_id: Mapped[int] = mapped_column(Integer, ForeignKey("racks.id"), nullable=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_definitions.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    rack = relationship("Rack")
    product = relationship("ProductDefinition")
