from sqlalchemy import Integer, String, Float, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

class Rack(Base):
    __tablename__ = 'racks'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    designation: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    rows_m: Mapped[int] = mapped_column(Integer)
    cols_n: Mapped[int] = mapped_column(Integer)
    temp_min: Mapped[float] = mapped_column(Float)
    temp_max: Mapped[float] = mapped_column(Float)
    max_weight_kg: Mapped[float] = mapped_column(Float)
    max_dims_x_mm: Mapped[int] = mapped_column(Integer)
    max_dims_y_mm: Mapped[int] = mapped_column(Integer)
    max_dims_z_mm: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text, nullable=True)

    items = relationship("StockItem", back_populates="rack")
