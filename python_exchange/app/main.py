import gc
from contextlib import asynccontextmanager
from typing import Optional
from anyio.to_thread import current_default_thread_limiter
from fastapi import FastAPI, HTTPException, Query, Request, Response
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
    warmup_account_cache,
)

from app.database import SessionLocal, create_tables
from app.orderbook import global_order_book_manager

create_tables()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Increase AnyIO worker thread limit from default 40 to 500
    limiter = current_default_thread_limiter()
    limiter.total_tokens = 500

    # Recover in-memory order book from persistent SQLite database
    with SessionLocal() as session:
        global_order_book_manager.recover_from_db(session)

    # Pre-warm account cache for all existing accounts (zero DB latency on initial reads)
    warmup_account_cache()

    # Freeze GC memory to prevent cyclic collection pauses on long-lived startup objects
    gc.collect()
    gc.freeze()
    gc.set_threshold(50_000, 20, 20)

    yield


app = FastAPI(
    title="Paper Exchange",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
    redirect_slashes=False,
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
async def get_account_endpoint(request: Request):
    qs = request.scope.get("query_string", b"")
    if not qs or qs == b"account_id=1":
        aid = 1
    else:
        aid_str = request.query_params.get("account_id", "1")
        try:
            aid = int(aid_str)
        except ValueError:
            aid = 1
    return Response(content=get_account_json_bytes(aid), media_type="application/json")


@app.get("/holdings")
async def get_holdings_endpoint(request: Request):
    qs = request.scope.get("query_string", b"")
    if not qs or qs == b"account_id=1":
        aid = 1
    else:
        aid_str = request.query_params.get("account_id", "1")
        try:
            aid = int(aid_str)
        except ValueError:
            aid = 1
    return Response(content=get_holdings_json_bytes(aid), media_type="application/json")


@app.get("/trades")
def get_trades_endpoint(
    symbol: Optional[str] = Query(None, description="Filter trades by stock symbol"),
    order_id: Optional[int] = Query(None, description="Filter trades by order ID"),
):
    return get_trades(symbol=symbol, order_id=order_id)


@app.get("/orderbook/{symbol}")
async def get_orderbook_endpoint(symbol: str):
    return Response(content=get_orderbook_bytes(symbol.upper()), media_type="application/json")


@app.get("/portfolio")
def get_portfolio_endpoint(account_id: int = Query(1, description="Account ID")):
    return get_portfolio(account_id)