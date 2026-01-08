from enum import Enum
from sqlalchemy import Integer, String, Boolean, Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

class UserRole(str, Enum):
    ADMIN = 'ADMIN'
    WAREHOUSEMAN = 'WAREHOUSEMAN'

class User(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    login: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(SQLAlchemyEnum(UserRole))
    totp_secret: Mapped[str] = mapped_column(String(32), nullable=True)
    is_2fa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
