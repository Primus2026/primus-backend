import uuid
from datetime import date, datetime
from sqlalchemy import Integer, ForeignKey, DateTime, UniqueConstraint, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .base import Base

class StockItem(Base):
    __tablename__ = 'stock_items'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_definitions.id"))
    rack_id: Mapped[int] = mapped_column(Integer, ForeignKey("racks.id"))
    position_row: Mapped[int] = mapped_column(Integer)
    position_col: Mapped[int] = mapped_column(Integer)
    y_position: Mapped[int] = mapped_column(Integer, default=0)
    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expiry_date: Mapped[date] = mapped_column(DateTime(timezone=True))
    received_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))

    product = relationship("ProductDefinition")
    rack = relationship("Rack", back_populates="items")
    receiver = relationship("User")

    __table_args__ = (
        UniqueConstraint('rack_id', 'position_row', 'position_col', 'y_position', name='unique_rack_position'),
    )
