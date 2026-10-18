from contextlib import asynccontextmanager
from typing import Optional
from anyio.to_thread import current_default_thread_limiter
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import ORJSONResponse

from pydantic import BaseModel
from app.database import create_tables
from app.models import OrderRequest
from app.service import (
    cancel_order,
    create_order,
    create_orders_batch,
    get_account,
    get_account_json_bytes,
    get_holdings,
    get_holdings_json_bytes,
    get_order,
    get_orders_batch,
    get_orderbook,
    get_orderbook_bytes,
    get_portfolio,
    get_trades,
    list_orders,
)

from app.database import SessionLocal, create_tables
from app.orderbook import global_order_book_manager

create_tables()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Increase AnyIO worker thread limit from default 40 to 500 to prevent request queuing under high concurrency
    limiter = current_default_thread_limiter()
    limiter.total_tokens = 500

    # Recover in-memory order book from persistent SQLite database
    with SessionLocal() as session:
        global_order_book_manager.recover_from_db(session)

    yield


app = FastAPI(
    title="Paper Exchange",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)


@app.post("/orders", status_code=201)
def create_order_endpoint(order_request: OrderRequest):
    new_order = create_order(order_request)
    return {
        "id": new_order.id,
        "account_id": new_order.account_id,
        "symbol": new_order.symbol,
        "side": new_order.side,
        "type": new_order.type,
        "price": new_order.price,
        "quantity": new_order.quantity,
        "status": new_order.status,
        "filled_quantity": new_order.filled_quantity,
        "created_at": new_order.created_at.isoformat() if new_order.created_at else None,
    }


class BatchGetOrdersRequest(BaseModel):
    order_ids: list[int]


@app.post("/orders/batch", status_code=201)
def create_orders_batch_endpoint(orders: list[OrderRequest]):
    created_orders = create_orders_batch(orders)
    return [
        {
            "id": o.id,
            "account_id": o.account_id,
            "symbol": o.symbol,
            "side": o.side,
            "type": o.type,
            "price": o.price,
            "quantity": o.quantity,
            "status": o.status,
            "filled_quantity": o.filled_quantity,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in created_orders
    ]


@app.post("/orders/batch-get")
def get_orders_batch_endpoint(batch_req: BatchGetOrdersRequest):
    return get_orders_batch(batch_req.order_ids)


@app.get("/orders")
def list_orders_endpoint(
    symbol: Optional[str] = Query(None, description="Filter by stock symbol"),
    status: Optional[str] = Query(None, description="Filter by order status"),
):
    return list_orders(symbol=symbol, status=status)


@app.get("/orders/{id}")
def get_order_endpoint(id: int):
    order = get_order(id)
    return {
        "id": order.id,
        "account_id": order.account_id,
        "symbol": order.symbol,
        "side": order.side,
        "type": order.type,
        "price": order.price,
        "quantity": order.quantity,
        "status": order.status,
        "filled_quantity": order.filled_quantity,
        "created_at": order.created_at.isoformat() if order.created_at else None,
    }


@app.delete("/orders/{id}")
def cancel_order_endpoint(id: int):
    order = cancel_order(id)
    return {
        "id": order.id,
        "account_id": order.account_id,
        "symbol": order.symbol,
        "side": order.side,
        "type": order.type,
        "price": order.price,
        "quantity": order.quantity,
        "status": order.status,
        "filled_quantity": order.filled_quantity,
        "message": "Order cancelled successfully",
    }


@app.get("/account")
def get_account_endpoint(account_id: int = Query(1, description="Account ID")):
    return Response(content=get_account_json_bytes(account_id), media_type="application/json")


@app.get("/holdings")
def get_holdings_endpoint(account_id: int = Query(1, description="Account ID")):
    return Response(content=get_holdings_json_bytes(account_id), media_type="application/json")


@app.get("/trades")
def get_trades_endpoint(
    symbol: Optional[str] = Query(None, description="Filter trades by stock symbol"),
    order_id: Optional[int] = Query(None, description="Filter trades by order ID"),
):
    return get_trades(symbol=symbol, order_id=order_id)


@app.get("/orderbook/{symbol}")
def get_orderbook_endpoint(symbol: str):
    return Response(content=get_orderbook_bytes(symbol), media_type="application/json")


@app.get("/portfolio")
def get_portfolio_endpoint(account_id: int = Query(1, description="Account ID")):
    return get_portfolio(account_id)