from app.database import SessionLocal
from app.models import AccountDB, AccountHoldingDB, OrderDB, OrderSide, OrderType, TradeDB


def test_account_creation_and_persistence():
    with SessionLocal() as session:
        acc = AccountDB(balance=500000, reserved_balance=50000)
        session.add(acc)
        session.commit()
        session.refresh(acc)

        assert acc.id is not None
        assert acc.balance == 500000
        assert acc.reserved_balance == 50000


def test_order_creation_and_persistence():
    with SessionLocal() as session:
        order = OrderDB(
            account_id=1,
            symbol="AAPL",
            side=OrderSide.BUY.value,
            type=OrderType.LIMIT.value,
            price=150,
            quantity=10,
            status="open",
            filled_quantity=0,
        )
        session.add(order)
        session.commit()
        session.refresh(order)

        assert order.id is not None
        assert order.symbol == "AAPL"
        assert order.account_id == 1
        assert order.created_at is not None


def test_holding_persistence():
    with SessionLocal() as session:
        holding = AccountHoldingDB(
            account_id=1,
            symbol="GOOGL",
            quantity=50,
            reserved_quantity=10,
        )
        session.add(holding)
        session.commit()
        session.refresh(holding)

        assert holding.id is not None
        assert holding.symbol == "GOOGL"
        assert holding.quantity == 50
        assert holding.reserved_quantity == 10


def test_trade_persistence():
    with SessionLocal() as session:
        buy_order = OrderDB(
            account_id=1,
            symbol="AAPL",
            side="buy",
            type="limit",
            price=100,
            quantity=5,
            status="filled",
            filled_quantity=5,
        )
        sell_order = OrderDB(
            account_id=2,
            symbol="AAPL",
            side="sell",
            type="limit",
            price=100,
            quantity=5,
            status="filled",
            filled_quantity=5,
        )
        session.add_all([buy_order, sell_order])
        session.commit()

        trade = TradeDB(
            buy_order_id=buy_order.id,
            sell_order_id=sell_order.id,
            price=100,
            quantity=5,
        )
        session.add(trade)
        session.commit()
        session.refresh(trade)

        assert trade.id is not None
        assert trade.price == 100
        assert trade.quantity == 5
        assert trade.executed_at is not None
