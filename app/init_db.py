from app.database import SessionLocal, create_tables
from app.models import AccountDB


def initialise_database():
    create_tables()
    with SessionLocal() as session:
        account_count = session.query(AccountDB).count()
        if account_count == 0:
            default_account = AccountDB(balance=10000000, reserved_balance=0)
            session.add(default_account)
            session.commit()


initialise_database()