import pytest
from fastapi import HTTPException
from app.database import SessionLocal
from app.models import AccountHoldingDB, OrderRequest, OrderSide
from app.service import cancel_order, create_order, get_account, get_holdings, get_order


def test_cancel_open_buy_order():
    # Submit buy order
    buy = create_order(
        OrderRequest(
            account_id=1, symbol="AAPL", side=OrderSide.BUY, price=150, quantity=10
        )
    )
    acc_before = get_account(1)
    assert acc_before["reserved_balance"] == 1500

    # Cancel order
    cancelled = cancel_order(buy.id)
    assert cancelled.status == "cancelled"

    acc_after = get_account(1)
    assert acc_after["reserved_balance"] == 0
    assert acc_after["available_balance"] == 10000000


def test_cancel_open_sell_order():
    with SessionLocal() as session:
        session.add(
            AccountHoldingDB(
                account_id=1, symbol="AAPL", quantity=50, reserved_quantity=0
            )
        )
        session.commit()

    sell = create_order(
        OrderRequest(
            account_id=1, symbol="AAPL", side=OrderSide.SELL, price=200, quantity=20
        )
    )
    h_before = next(h for h in get_holdings(1) if h["symbol"] == "AAPL")
    assert h_before["reserved_quantity"] == 20

    cancelled = cancel_order(sell.id)
    assert cancelled.status == "cancelled"

    h_after = next(h for h in get_holdings(1) if h["symbol"] == "AAPL")
    assert h_after["reserved_quantity"] == 0
    assert h_after["available_quantity"] == 50


def test_cancel_partially_filled_order():
    with SessionLocal() as session:
        session.add(
            AccountHoldingDB(
                account_id=2, symbol="AAPL", quantity=100, reserved_quantity=0
            )
        )
        session.commit()

    # Seller rests with 10 shares
    create_order(
        OrderRequest(
            account_id=2, symbol="AAPL", side=OrderSide.SELL, price=140, quantity=10
        )
    )

    # Buyer orders 30 shares -> 10 filled, 20 remaining
    buy = create_order(
        OrderRequest(
            account_id=1, symbol="AAPL", side=OrderSide.BUY, price=140, quantity=30
        )
    )
    assert get_order(buy.id).status == "partially_filled"

    acc_before = get_account(1)
    # Remaining 20 shares reserved at 140 = 2800
    assert acc_before["reserved_balance"] == 2800

    # Cancel partially filled order
    cancelled = cancel_order(buy.id)
    assert cancelled.status == "cancelled"

    acc_after = get_account(1)
    # The 2800 reserved cash should be released
    assert acc_after["reserved_balance"] == 0


def test_cancel_filled_order_rejected():
    with SessionLocal() as session:
        session.add(
            AccountHoldingDB(
                account_id=2, symbol="AAPL", quantity=100, reserved_quantity=0
            )
        )
        session.commit()

    create_order(
        OrderRequest(
            account_id=2, symbol="AAPL", side=OrderSide.SELL, price=100, quantity=10
        )
    )
    buy = create_order(
        OrderRequest(
            account_id=1, symbol="AAPL", side=OrderSide.BUY, price=100, quantity=10
        )
    )
    assert get_order(buy.id).status == "filled"

    with pytest.raises(HTTPException) as exc_info:
        cancel_order(buy.id)
    assert exc_info.value.status_code == 400
    assert "Cannot cancel order with status 'filled'" in exc_info.value.detail


def test_cancel_already_cancelled_order_rejected():
    buy = create_order(
        OrderRequest(
            account_id=1, symbol="AAPL", side=OrderSide.BUY, price=150, quantity=5
        )
    )
    cancel_order(buy.id)

    with pytest.raises(HTTPException) as exc_info:
        cancel_order(buy.id)
    assert exc_info.value.status_code == 400
    assert "Cannot cancel order with status 'cancelled'" in exc_info.value.detail


def test_cancel_nonexistent_order():
    with pytest.raises(HTTPException) as exc_info:
        cancel_order(999999)
    assert exc_info.value.status_code == 404
