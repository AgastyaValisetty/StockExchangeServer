import pytest
from pydantic import ValidationError
from app.models import OrderRequest, OrderSide, OrderType


def test_valid_order():
    order = OrderRequest(
        symbol=" aapl  ",
        side=OrderSide.BUY,
        type=OrderType.LIMIT,
        price=150,
        quantity=10,
    )
    assert order.symbol == "AAPL"
    assert order.side == OrderSide.BUY
    assert order.type == OrderType.LIMIT
    assert order.price == 150
    assert order.quantity == 10
    assert order.account_id == 1


def test_invalid_symbol():
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="AAPL$$",
            side=OrderSide.BUY,
            price=150,
            quantity=10,
        )

    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="",
            side=OrderSide.BUY,
            price=150,
            quantity=10,
        )


def test_invalid_price():
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            price=0,
            quantity=10,
        )

    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            price=-50,
            quantity=10,
        )


def test_invalid_quantity():
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            price=100,
            quantity=0,
        )

    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            price=100,
            quantity=-5,
        )


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            typee="limit",
            price=100,
            quantity=10,
        )