from app.database import SessionLocal
from app.models import AccountHoldingDB, OrderRequest, OrderSide
from app.service import create_order, get_order, get_orderbook, get_trades


def test_matching_buy_gte_sell():
    with SessionLocal() as session:
        session.add(
            AccountHoldingDB(
                account_id=2, symbol="AAPL", quantity=100, reserved_quantity=0
            )
        )
        session.commit()

    # Seller rests at 150
    sell_order = create_order(
        OrderRequest(
            account_id=2, symbol="AAPL", side=OrderSide.SELL, price=150, quantity=10
        )
    )
    # Buyer bids 150
    buy_order = create_order(
        OrderRequest(
            account_id=1, symbol="AAPL", side=OrderSide.BUY, price=150, quantity=10
        )
    )

    trades = get_trades(symbol="AAPL")
    assert len(trades) == 1
    assert trades[0]["price"] == 150
    assert trades[0]["quantity"] == 10

    o_buy = get_order(buy_order.id)
    o_sell = get_order(sell_order.id)
    assert o_buy.status == "filled"
    assert o_sell.status == "filled"


def test_no_match_when_buy_less_than_sell():
    with SessionLocal() as session:
        session.add(
            AccountHoldingDB(
                account_id=2, symbol="AAPL", quantity=100, reserved_quantity=0
            )
        )
        session.commit()

    # Seller at 160
    sell_order = create_order(
        OrderRequest(
            account_id=2, symbol="AAPL", side=OrderSide.SELL, price=160, quantity=10
        )
    )
    # Buyer bids 150 (lower than sell)
    buy_order = create_order(
        OrderRequest(
            account_id=1, symbol="AAPL", side=OrderSide.BUY, price=150, quantity=10
        )
    )

    trades = get_trades(symbol="AAPL")
    assert len(trades) == 0

    assert get_order(buy_order.id).status == "open"
    assert get_order(sell_order.id).status == "open"

    book = get_orderbook("AAPL")
    assert len(book["bids"]) == 1
    assert len(book["asks"]) == 1


def test_price_priority_for_sells():
    # Account 2 has shares to sell
    with SessionLocal() as session:
        session.add(
            AccountHoldingDB(
                account_id=2, symbol="AAPL", quantity=100, reserved_quantity=0
            )
        )
        session.commit()

    # Two resting sells: one at 155, one at 150 (cheaper)
    sell1 = create_order(
        OrderRequest(
            account_id=2, symbol="AAPL", side=OrderSide.SELL, price=155, quantity=10
        )
    )
    sell2 = create_order(
        OrderRequest(
            account_id=2, symbol="AAPL", side=OrderSide.SELL, price=150, quantity=10
        )
    )

    # Incoming buy for 10 shares at 160 -> should match sell2 (cheaper, price 150)
    buy = create_order(
        OrderRequest(
            account_id=1, symbol="AAPL", side=OrderSide.BUY, price=160, quantity=10
        )
    )

    trades = get_trades(symbol="AAPL")
    assert len(trades) == 1
    assert trades[0]["sell_order_id"] == sell2.id
    assert trades[0]["price"] == 150

    assert get_order(sell2.id).status == "filled"
    assert get_order(sell1.id).status == "open"


def test_time_priority_same_price():
    with SessionLocal() as session:
        session.add(
            AccountHoldingDB(
                account_id=2, symbol="AAPL", quantity=100, reserved_quantity=0
            )
        )
        session.commit()

    # Two resting sells at identical price 150
    first_sell = create_order(
        OrderRequest(
            account_id=2, symbol="AAPL", side=OrderSide.SELL, price=150, quantity=5
        )
    )
    second_sell = create_order(
        OrderRequest(
            account_id=2, symbol="AAPL", side=OrderSide.SELL, price=150, quantity=5
        )
    )

    # Incoming buy for 5 shares
    create_order(
        OrderRequest(
            account_id=1, symbol="AAPL", side=OrderSide.BUY, price=150, quantity=5
        )
    )

    trades = get_trades(symbol="AAPL")
    assert len(trades) == 1
    assert trades[0]["sell_order_id"] == first_sell.id
    assert get_order(first_sell.id).status == "filled"
    assert get_order(second_sell.id).status == "open"


def test_self_matching_prevention():
    # Account 1 has 50 shares of AAPL
    with SessionLocal() as session:
        session.add(
            AccountHoldingDB(
                account_id=1, symbol="AAPL", quantity=50, reserved_quantity=0
            )
        )
        session.commit()

    # Account 1 places a sell order at 150
    sell_order = create_order(
        OrderRequest(
            account_id=1, symbol="AAPL", side=OrderSide.SELL, price=150, quantity=10
        )
    )

    # Account 1 places a buy order at 150
    buy_order = create_order(
        OrderRequest(
            account_id=1, symbol="AAPL", side=OrderSide.BUY, price=150, quantity=10
        )
    )

    # They should NOT match each other because account_id is the same
    trades = get_trades(symbol="AAPL")
    assert len(trades) == 0

    assert get_order(sell_order.id).status == "open"
    assert get_order(buy_order.id).status == "open"
