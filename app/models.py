from enum import Enum
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, engine

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(str, Enum):
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

class OrderType(str, Enum):
    LIMIT = "limit"

class OrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    type: OrderType
    price: int = Field(gt=0)
    quantity: int = Field(gt=0)
    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value.isalnum():
            raise ValueError("Symbol must be alphanumeric")
        return value

class OrderDB(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    type: Mapped[str] = mapped_column(String(5), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OrderStatus.OPEN.value
        )
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


def create_tables():
    Base.metadata.create_all(bind=engine)