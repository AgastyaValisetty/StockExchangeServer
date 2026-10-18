from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint, CheckConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


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
    model_config = ConfigDict(extra="forbid")

    symbol: str
    side: OrderSide
    type: OrderType = OrderType.LIMIT
    price: int = Field(gt=0)
    quantity: int = Field(gt=0)
    account_id: int = 1

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if not value or not value.isalnum():
            raise ValueError("Symbol must be alphanumeric")
        return value


class OrderDB(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_order_price_positive"),
        CheckConstraint("quantity > 0", name="ck_order_quantity_positive"),
        CheckConstraint(
            "filled_quantity >= 0 AND filled_quantity <= quantity",
            name="ck_order_filled_quantity_valid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(5), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=OrderStatus.OPEN.value, index=True
    )
    filled_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class AccountDB(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_account_balance_nonnegative"),
        CheckConstraint(
            "reserved_balance >= 0 AND reserved_balance <= balance",
            name="ck_account_reserved_balance_valid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AccountHoldingDB(Base):
    __tablename__ = "account_holdings"
    __table_args__ = (
        UniqueConstraint("account_id", "symbol", name="uq_account_symbol"),
        CheckConstraint("quantity >= 0", name="ck_holding_quantity_nonnegative"),
        CheckConstraint(
            "reserved_quantity >= 0 AND reserved_quantity <= quantity",
            name="ck_holding_reserved_quantity_valid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TradeDB(Base):
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_trade_price_positive"),
        CheckConstraint("quantity > 0", name="ck_trade_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    buy_order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    sell_order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
