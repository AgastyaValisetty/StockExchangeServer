import pytest
from app.database import SessionLocal, create_tables
from app.models import AccountDB, AccountHoldingDB, OrderDB, TradeDB
from app.orderbook import global_order_book_manager


@pytest.fixture(autouse=True)
def setup_and_clean_database():
    create_tables()
    with SessionLocal() as session:
        session.query(TradeDB).delete()
        session.query(OrderDB).delete()
        session.query(AccountHoldingDB).delete()
        session.query(AccountDB).delete()

        # Seed standard test accounts:
        # Account 1: 10,000,000 paise cash
        # Account 2: 10,000,000 paise cash
        acc1 = AccountDB(id=1, balance=10000000, reserved_balance=0)
        acc2 = AccountDB(id=2, balance=10000000, reserved_balance=0)
        session.add_all([acc1, acc2])
        session.commit()

    # Reset in-memory order book state for test isolation
    global_order_book_manager.books.clear()
    global_order_book_manager.last_synced_id = 0
    global_order_book_manager._initialized = True
    yield

