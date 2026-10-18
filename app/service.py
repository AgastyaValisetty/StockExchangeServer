from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.engine import (
    cancel_order as engine_cancel_order,
    get_orderbook as engine_get_orderbook,
    submit_order as engine_submit_order,
)
from app.models import (
    AccountDB,
    AccountHoldingDB,
    OrderDB,
    OrderRequest,
    TradeDB,
)

SIMULATED_PRICES = {
    "AAPL": 15000,
    "GOOGL": 28000,
    "MSFT": 30000,
    "TSLA": 20000,
}


def create_order(order_request: OrderRequest) -> OrderDB:
    with SessionLocal() as session:
        order = engine_submit_order(session, order_request)
        session.commit()
        session.refresh(order)
        session.expunge(order)
        return order


def cancel_order(order_id: int) -> OrderDB:
    with SessionLocal() as session:
        order = engine_cancel_order(session, order_id)
        session.commit()
        session.refresh(order)
        session.expunge(order)
        return order


def get_order(order_id: int) -> OrderDB:
    with SessionLocal() as session:
        order = session.get(OrderDB, order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        session.expunge(order)
        return order


def list_orders(
    symbol: Optional[str] = None, status: Optional[str] = None
) -> List[dict]:
    with SessionLocal() as session:
        query = session.query(OrderDB)
        if symbol:
            query = query.filter(OrderDB.symbol == symbol.strip().upper())
        if status:
            query = query.filter(OrderDB.status == status.strip().lower())
        orders = query.order_by(OrderDB.id).all()
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
            for o in orders
        ]


def get_account(account_id: int = 1) -> dict:
    with SessionLocal() as session:
        account = session.get(AccountDB, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        return {
            "account_id": account.id,
            "balance": account.balance,
            "reserved_balance": account.reserved_balance,
            "available_balance": account.balance - account.reserved_balance,
        }


def get_holdings(account_id: int = 1) -> List[dict]:
    with SessionLocal() as session:
        holdings = (
            session.query(AccountHoldingDB)
            .filter_by(account_id=account_id)
            .order_by(AccountHoldingDB.symbol)
            .all()
        )
        return [
            {
                "symbol": h.symbol,
                "quantity": h.quantity,
                "reserved_quantity": h.reserved_quantity,
                "available_quantity": h.quantity - h.reserved_quantity,
            }
            for h in holdings
        ]


def get_trades(
    symbol: Optional[str] = None, order_id: Optional[int] = None
) -> List[dict]:
    with SessionLocal() as session:
        query = session.query(TradeDB)
        if order_id is not None:
            query = query.filter(
                (TradeDB.buy_order_id == order_id) | (TradeDB.sell_order_id == order_id)
            )
        if symbol:
            symbol_upper = symbol.strip().upper()
            query = query.join(
                OrderDB, TradeDB.buy_order_id == OrderDB.id
            ).filter(OrderDB.symbol == symbol_upper)

        trades = query.order_by(TradeDB.id).all()
        return [
            {
                "id": t.id,
                "buy_order_id": t.buy_order_id,
                "sell_order_id": t.sell_order_id,
                "price": t.price,
                "quantity": t.quantity,
                "executed_at": t.executed_at.isoformat() if t.executed_at else None,
            }
            for t in trades
        ]


def get_orderbook(symbol: str) -> dict:
    with SessionLocal() as session:
        return engine_get_orderbook(session, symbol.strip().upper())


def get_market_price(session: Session, symbol: str) -> int:
    # 1. Check last trade price
    last_trade = (
        session.query(TradeDB)
        .join(OrderDB, TradeDB.buy_order_id == OrderDB.id)
        .filter(OrderDB.symbol == symbol)
        .order_by(TradeDB.id.desc())
        .first()
    )
    if last_trade:
        return last_trade.price

    # 2. Check last order price
    last_order = (
        session.query(OrderDB)
        .filter(OrderDB.symbol == symbol)
        .order_by(OrderDB.id.desc())
        .first()
    )
    if last_order:
        return last_order.price

    # 3. Fallback to default simulated price
    return SIMULATED_PRICES.get(symbol, 10000)


def get_portfolio(account_id: int = 1) -> dict:
    with SessionLocal() as session:
        account = session.get(AccountDB, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")

        holdings = (
            session.query(AccountHoldingDB)
            .filter_by(account_id=account_id)
            .all()
        )

        holdings_summary = []
        total_holding_value = 0
        total_cost_basis = 0

        for h in holdings:
            if h.quantity == 0:
                continue

            market_price = get_market_price(session, h.symbol)
            current_value = h.quantity * market_price

            # Compute cost basis from executed buy trades for this account & symbol
            buy_trades = (
                session.query(TradeDB)
                .join(OrderDB, TradeDB.buy_order_id == OrderDB.id)
                .filter(OrderDB.account_id == account_id, OrderDB.symbol == h.symbol)
                .all()
            )
            total_bought_qty = sum(t.quantity for t in buy_trades)
            total_bought_cost = sum(t.price * t.quantity for t in buy_trades)

            if total_bought_qty > 0:
                avg_cost_per_share = total_bought_cost // total_bought_qty
            else:
                avg_cost_per_share = market_price

            cost_basis = avg_cost_per_share * h.quantity
            unrealized_pnl = current_value - cost_basis

            total_holding_value += current_value
            total_cost_basis += cost_basis

            holdings_summary.append({
                "symbol": h.symbol,
                "quantity": h.quantity,
                "market_price": market_price,
                "current_value": current_value,
                "cost_basis": cost_basis,
                "unrealized_pnl": unrealized_pnl,
            })

        total_unrealized_pnl = total_holding_value - total_cost_basis
        portfolio_value = account.balance + total_holding_value

        return {
            "account_id": account.id,
            "cash_balance": account.balance,
            "reserved_cash": account.reserved_balance,
            "available_cash": account.balance - account.reserved_balance,
            "holdings_value": total_holding_value,
            "total_portfolio_value": portfolio_value,
            "total_unrealized_pnl": total_unrealized_pnl,
            "holdings": holdings_summary,
        }
