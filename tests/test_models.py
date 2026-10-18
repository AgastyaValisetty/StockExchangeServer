import pytest 
from pydantic import ValidationError
from app.models import OrderRequest

def test_valid_order():
    order = OrderRequest(
        symbol=" aapl  ",
        side="buy",
        type="limit",
        price=150,
        quantity=10
    )
    assert order.symbol == "AAPL"

def test_invalid_symbol():
    with pytest.raises(ValidationError):
        OrderRequest(
            symbol="AAPL",
            side="buy",
            typee="limit",
            price=0,
            quantity=10
        )