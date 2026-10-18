from fastapi import FastAPI
from app.database import create_tables, SessionLocal
from app.models import OrderDB, OrderRequest
from app.service import create_order

create_tables()

app = FastAPI(title="Paper Exchange")

@app.post("/orders")
def create_order_endpoint(order_request: OrderRequest):
    new_order = create_order(order_request)
    return {
        "id": new_order.id,
        "symbol": new_order.symbol,
        "side": new_order.side,
        "type": new_order.type,
        "price": new_order.price,
        "quantity": new_order.quantity,
        "status": new_order.status,
        "filled_quantity": new_order.filled_quantity
    }

@app.get("/orders")
def list_orders():
    with SessionLocal() as session:
        orders = session.query(OrderDB).order_by(OrderDB.id).all()
        return [
            {
                "id": order.id,
                "symbol": order.symbol,
                "side": order.side,
                "type": order.type,
                "price": order.price,
                "quantity": order.quantity,
                "status": order.status,
                "filled_quantity": order.filled_quantity
            }
            for order in orders
        ]