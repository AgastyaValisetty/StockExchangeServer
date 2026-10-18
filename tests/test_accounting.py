import pytest
from fastapi import HTTPException
from app.database import SessionLocal
from app.models import AccountDB, AccountHoldingDB, OrderRequest, OrderSide
from app.service import create_order, get_account, get_holdings


def test_buy_order_cash_reservation():
    # Account 1 starts with 10,000,000 paise
    req = OrderRequest(
        symbol="AAPL",
        side=OrderSide.BUY,
        price=150,
        quantity=100,
        account_id=1,
    )
    order = create_order(req)
    assert order.id is not None

    acc = get_account(1)
    assert acc["balance"] == 10000000
    assert acc["reserved_balance"] == 15000  # 150 * 100
    assert acc["available_balance"] == 10000000 - 15000


def test_insufficient_cash_rejected():
    # Attempt to reserve more than 10,000,000 paise
    req = OrderRequest(
        symbol="AAPL",
        side=OrderSide.BUY,
        price=200000,
        quantity=100,  # 20,000,000 paise > 10,000,000
        account_id=1,
    )
    with pytest.raises(HTTPException) as exc_info:
        create_order(req)
    assert exc_info.value.status_code == 400
    assert "Insufficient available cash" in exc_info.value.detail


def test_sell_order_share_reservation():
    # Give Account 1 some shares first
    with SessionLocal() as session:
        holding = AccountHoldingDB(
            account_id=1,
            symbol="MSFT",
            quantity=50,
            reserved_quantity=0,
        )
        session.add(holding)
        session.commit()

    req = OrderRequest(
        symbol="MSFT",
        side=OrderSide.SELL,
        price=300,
        quantity=20,
        account_id=1,
    )
    order = create_order(req)
    assert order.id is not None

    holdings = get_holdings(1)
    msft_holding = next(h for h in holdings if h["symbol"] == "MSFT")
    assert msft_holding["quantity"] == 50
    assert msft_holding["reserved_quantity"] == 20
    assert msft_holding["available_quantity"] == 30


def test_sell_without_holding_rejected():
    req = OrderRequest(
        symbol="XYZ",
        side=OrderSide.SELL,
        price=100,
        quantity=10,
        account_id=1,
    )
    with pytest.raises(HTTPException) as exc_info:
        create_order(req)
    assert exc_info.value.status_code == 400
    assert "No holding found for symbol" in exc_info.value.detail


def test_insufficient_shares_rejected():
    with SessionLocal() as session:
        holding = AccountHoldingDB(
            account_id=1,
            symbol="TSLA",
            quantity=10,
            reserved_quantity=5,
        )
        session.add(holding)
        session.commit()

    req = OrderRequest(
        symbol="TSLA",
        side=OrderSide.SELL,
        price=200,
        quantity=6,  # available is 10 - 5 = 5
        account_id=1,
    )
    with pytest.raises(HTTPException) as exc_info:
        create_order(req)
    assert exc_info.value.status_code == 400
    assert "Insufficient available shares" in exc_info.value.detail


def test_trade_accounting_and_price_improvement():
    # Account 2 has 50 shares of AAPL
    with SessionLocal() as session:
        session.add(
            AccountHoldingDB(
                account_id=2,
                symbol="AAPL",
                quantity=50,
                reserved_quantity=0,
            )
        )
        session.commit()

    # Resting sell order from Account 2 at price 140 for 20 shares
    sell_req = OrderRequest(
        account_id=2,
        symbol="AAPL",
        side=OrderSide.SELL,
        price=140,
        quantity=20,
    )
    create_order(sell_req)

    # Incoming buy order from Account 1 with limit price 150 for 20 shares
    # Limit is 150, but resting sell is at 140 -> trade executes at 140!
    # Price improvement: buyer reserved 150*20 = 3000, paid 140*20 = 2800.
    # Excess 200 is freed.
    buy_req = OrderRequest(
        account_id=1,
        symbol="AAPL",
        side=OrderSide.BUY,
        price=150,
        quantity=20,
    )
    create_order(buy_req)

    # Check buyer (Account 1)
    acc1 = get_account(1)
    # Balance decreased by actual cost 2800 (from 10,000,000)
    assert acc1["balance"] == 10000000 - 2800
    # Reserved cash fully released
    assert acc1["reserved_balance"] == 0
    assert acc1["available_balance"] == 10000000 - 2800

    holdings1 = get_holdings(1)
    h1 = next(h for h in holdings1 if h["symbol"] == "AAPL")
    assert h1["quantity"] == 20
    assert h1["reserved_quantity"] == 0
    assert h1["available_quantity"] == 20

    # Check seller (Account 2)
    acc2 = get_account(2)
    # Balance increased by 2800 (from 10,000,000)
    assert acc2["balance"] == 10000000 + 2800
    assert acc2["reserved_balance"] == 0

    holdings2 = get_holdings(2)
    h2 = next(h for h in holdings2 if h["symbol"] == "AAPL")
    # 50 - 20 = 30 remaining
    assert h2["quantity"] == 30
    assert h2["reserved_quantity"] == 0
    assert h2["available_quantity"] == 30
