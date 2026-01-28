from sqlalchemy import Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column 
from .base import Base

class ProductStats(Base):
    __tablename__ = "product_stats"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("product_definitions.id"))
    pick_count: Mapped[int] = mapped_column(Integer, default=0)
    # Global counter 
    total_since_last_update: Mapped[int] = mapped_column(Integer, default=0)
    