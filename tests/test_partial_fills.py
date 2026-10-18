from app.database import SessionLocal
from app.models import AccountHoldingDB, OrderRequest, OrderSide
from app.service import create_order, get_account, get_holdings, get_order, get_trades


def test_order_filled_across_multiple_trades():
    with SessionLocal() as session:
        session.add(
            AccountHoldingDB(
                account_id=2, symbol="AAPL", quantity=100, reserved_quantity=0
            )
        )
        session.commit()

    # Resting sell order 1: 10 shares @ 140
    sell1 = create_order(
        OrderRequest(
            account_id=2, symbol="AAPL", side=OrderSide.SELL, price=140, quantity=10
        )
    )
    # Resting sell order 2: 15 shares @ 145
    sell2 = create_order(
        OrderRequest(
            account_id=2, symbol="AAPL", side=OrderSide.SELL, price=145, quantity=15
        )
    )

    # Incoming buy: 25 shares @ 150
    # Should match sell1 (10 @ 140) and then sell2 (15 @ 145)
    buy = create_order(
        OrderRequest(
            account_id=1, symbol="AAPL", side=OrderSide.BUY, price=150, quantity=25
        )
    )

    trades = get_trades(symbol="AAPL")
    assert len(trades) == 2
    assert trades[0]["price"] == 140
    assert trades[0]["quantity"] == 10
    assert trades[1]["price"] == 145
    assert trades[1]["quantity"] == 15

    # Buy order should be fully filled
    updated_buy = get_order(buy.id)
    assert updated_buy.status == "filled"
    assert updated_buy.filled_quantity == 25

    # Both sell orders should be fully filled
    assert get_order(sell1.id).status == "filled"
    assert get_order(sell2.id).status == "filled"

    # Buyer has 25 shares now
    holdings1 = get_holdings(1)
    aapl_h1 = next(h for h in holdings1 if h["symbol"] == "AAPL")
    assert aapl_h1["quantity"] == 25
    assert aapl_h1["reserved_quantity"] == 0

    # Total cost = 10*140 + 15*145 = 1400 + 2175 = 3575
    acc1 = get_account(1)
    assert acc1["balance"] == 10000000 - 3575
    assert acc1["reserved_balance"] == 0


def test_partially_filled_order_remaining():
    with SessionLocal() as session:
        session.add(
            AccountHoldingDB(
                account_id=2, symbol="AAPL", quantity=100, reserved_quantity=0
            )
        )
        session.commit()

    # Resting sell: 10 shares @ 140
    sell = create_order(
        OrderRequest(
            account_id=2, symbol="AAPL", side=OrderSide.SELL, price=140, quantity=10
        )
    )

    # Incoming buy: 30 shares @ 140
    # Matches 10 shares, 20 shares remain open
    buy = create_order(
        OrderRequest(
            account_id=1, symbol="AAPL", side=OrderSide.BUY, price=140, quantity=30
        )
    )

    updated_buy = get_order(buy.id)
    assert updated_buy.status == "partially_filled"
    assert updated_buy.filled_quantity == 10

    assert get_order(sell.id).status == "filled"

    # 10 shares filled at 140 -> cost 1400 deducted
    # 20 shares still open at 140 -> reserved_balance = 20 * 140 = 2800
    acc1 = get_account(1)
    assert acc1["balance"] == 10000000 - 1400
    assert acc1["reserved_balance"] == 2800
    assert acc1["available_balance"] == 10000000 - 1400 - 2800
