import pytest
from app.database import SessionLocal, create_tables
from app.models import AccountDB, AccountHoldingDB, OrderDB, TradeDB


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
    yield
