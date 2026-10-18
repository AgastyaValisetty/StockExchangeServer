from app.database import SessionLocal
from app.models import OrderRequest, OrderDB

def create_order(order_request: OrderRequest) -> OrderDB:
    with SessionLocal() as session:
        new_order = OrderDB(
            symbol=order_request.symbol,
            side=order_request.side.value,
            type=order_request.type.value,
            price=order_request.price,
            quantity=order_request.quantity,
            status="open",
            filled_quantity=0
        )
        session.add(new_order)
        session.commit()
        session.refresh(new_order)
        session.close()
        return new_order