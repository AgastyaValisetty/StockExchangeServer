from typing import Optional
from fastapi import FastAPI, HTTPException, Query

from app.database import create_tables
from app.models import OrderRequest
from app.service import (
    cancel_order,
    create_order,
    get_account,
    get_holdings,
    get_order,
    get_orderbook,
    get_portfolio,
    get_trades,
    list_orders,
)

create_tables()

app = FastAPI(title="Paper Exchange")


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
    return get_account(account_id)


@app.get("/holdings")
def get_holdings_endpoint(account_id: int = Query(1, description="Account ID")):
    return get_holdings(account_id)


@app.get("/trades")
def get_trades_endpoint(
    symbol: Optional[str] = Query(None, description="Filter trades by stock symbol"),
    order_id: Optional[int] = Query(None, description="Filter trades by order ID"),
):
    return get_trades(symbol=symbol, order_id=order_id)


@app.get("/orderbook/{symbol}")
def get_orderbook_endpoint(symbol: str):
    return get_orderbook(symbol)


@app.get("/portfolio")
def get_portfolio_endpoint(account_id: int = Query(1, description="Account ID")):
    return get_portfolio(account_id)