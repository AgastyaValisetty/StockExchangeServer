from app.database import SessionLocal
from app.models import AccountDB

def initialise_database():
    with SessionLocal() as session:
        # Check if the accounts table is empty
        account_count = session.query(AccountDB).count()
        if account_count == 0:
            # Create a default account with a balance of 10000000 paise not INR 
            default_account = AccountDB(balance=10000000, reserved_balance=0)
            session.add(default_account)
            session.commit()

initialise_database()