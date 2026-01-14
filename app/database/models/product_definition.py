from sqlalchemy import Integer, String, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

class ProductDefinition(Base):
    __tablename__ = 'product_definitions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    barcode: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    photo_path: Mapped[str] = mapped_column(String(255), nullable=True)
    req_temp_min: Mapped[float] = mapped_column(Float)
    req_temp_max: Mapped[float] = mapped_column(Float)
    weight_kg: Mapped[float] = mapped_column(Float)
    dims_x_mm: Mapped[int] = mapped_column(Integer)
    dims_y_mm: Mapped[int] = mapped_column(Integer)
    dims_z_mm: Mapped[int] = mapped_column(Integer)
    is_dangerous: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str] = mapped_column(String(255), nullable=True)
    expiry_days: Mapped[int] = mapped_column(Integer)
