from app.database import SessionLocal
from app.models import OrderDB, OrderSide, OrderType

session = SessionLocal()


def test_create_order():
    new_order = OrderDB(
        symbol="AAPL",
        side=OrderSide.BUY.value,
        type=OrderType.LIMIT.value,
        price=150,
        quantity=10,
        status="open",
        filled_quantity=0
    )
    session.add(new_order)
    session.commit()
    session.refresh(new_order)
    assert new_order.id is not None
