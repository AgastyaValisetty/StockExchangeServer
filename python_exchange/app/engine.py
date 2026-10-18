from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    AccountDB,
    AccountHoldingDB,
    OrderDB,
    OrderRequest,
    OrderStatus,
    TradeDB,
)


def submit_order(session: Session, order_request: OrderRequest) -> OrderDB:
    account = session.get(AccountDB, order_request.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    if order_request.side.value == "buy":
        required_cash = order_request.price * order_request.quantity
        available_cash = account.balance - account.reserved_balance

        if available_cash < required_cash:
            raise HTTPException(
                status_code=400,
                detail="Insufficient available cash"
            )

        account.reserved_balance += required_cash

    elif order_request.side.value == "sell":
        holding = session.query(AccountHoldingDB).filter_by(
            account_id=account.id,
            symbol=order_request.symbol
        ).first()

        if holding is None:
            raise HTTPException(
                status_code=400,
                detail="No holding found for symbol"
            )

        available_shares = holding.quantity - holding.reserved_quantity

        if available_shares < order_request.quantity:
            raise HTTPException(
                status_code=400,
                detail="Insufficient available shares"
            )

        holding.reserved_quantity += order_request.quantity

    new_order = OrderDB(
        account_id=account.id,
        symbol=order_request.symbol,
        side=order_request.side.value,
        type=order_request.type.value,
        price=order_request.price,
        quantity=order_request.quantity,
        status=OrderStatus.OPEN.value,
        filled_quantity=0,
        created_at=datetime.now(timezone.utc),
    )

    session.add(new_order)
    session.flush()

    match_orders(session, new_order)
    return new_order


def get_matching_orders(
    session: Session,
    symbol: str,
    side: str,
    price: int,
    incoming_account_id: Optional[int] = None,
) -> List[OrderDB]:
    opposite_side = "sell" if side == "buy" else "buy"
    active_statuses = [OrderStatus.OPEN.value, OrderStatus.PARTIALLY_FILLED.value]

    query = session.query(OrderDB).filter(
        OrderDB.symbol == symbol,
        OrderDB.side == opposite_side,
        OrderDB.status.in_(active_statuses),
        OrderDB.quantity > OrderDB.filled_quantity,
    )

    # Self-matching prevention: do not match resting orders belonging to the same account
    if incoming_account_id is not None:
        query = query.filter(OrderDB.account_id != incoming_account_id)

    if side == "buy":
        # Buyer is willing to pay up to `price`; match sells at or below `price`
        query = query.filter(OrderDB.price <= price).order_by(
            OrderDB.price.asc(),
            OrderDB.created_at.asc(),
            OrderDB.id.asc(),
        )
    else:
        # Seller is willing to sell down to `price`; match buys at or above `price`
        query = query.filter(OrderDB.price >= price).order_by(
            OrderDB.price.desc(),
            OrderDB.created_at.asc(),
            OrderDB.id.asc(),
        )

    return query.all()


def update_order_fill(order: OrderDB, fill_qty: int) -> None:
    order.filled_quantity += fill_qty
    if order.filled_quantity >= order.quantity:
        order.status = OrderStatus.FILLED.value
    else:
        order.status = OrderStatus.PARTIALLY_FILLED.value


def release_buy_reservation(
    session: Session, account: AccountDB, order: OrderDB, released_qty: int
) -> None:
    account.reserved_balance -= order.price * released_qty


def release_sell_reservation(
    session: Session, holding: AccountHoldingDB, order: OrderDB, released_qty: int
) -> None:
    holding.reserved_quantity -= released_qty


def execute_trade(
    session: Session,
    buy_order: OrderDB,
    sell_order: OrderDB,
    price: int,
    quantity: int,
) -> TradeDB:
    trade = TradeDB(
        buy_order_id=buy_order.id,
        sell_order_id=sell_order.id,
        price=price,
        quantity=quantity,
        executed_at=datetime.now(timezone.utc),
    )
    session.add(trade)

    # Update filled quantities and order statuses
    update_order_fill(buy_order, quantity)
    update_order_fill(sell_order, quantity)

    # Buyer accounting
    buyer_account = session.get(AccountDB, buy_order.account_id)
    if buyer_account is not None:
        actual_cost = price * quantity
        buyer_account.balance -= actual_cost
        # Release the reservation for the filled quantity at order's limit price
        buyer_account.reserved_balance -= buy_order.price * quantity

    buyer_holding = session.query(AccountHoldingDB).filter_by(
        account_id=buy_order.account_id,
        symbol=buy_order.symbol,
    ).first()

    if buyer_holding is None:
        buyer_holding = AccountHoldingDB(
            account_id=buy_order.account_id,
            symbol=buy_order.symbol,
            quantity=quantity,
            reserved_quantity=0,
        )
        session.add(buyer_holding)
    else:
        buyer_holding.quantity += quantity

    # Seller accounting
    seller_account = session.get(AccountDB, sell_order.account_id)
    if seller_account is not None:
        proceeds = price * quantity
        seller_account.balance += proceeds

    seller_holding = session.query(AccountHoldingDB).filter_by(
        account_id=sell_order.account_id,
        symbol=sell_order.symbol,
    ).first()

    if seller_holding is not None:
        seller_holding.quantity -= quantity
        seller_holding.reserved_quantity -= quantity

    return trade


def match_orders(session: Session, incoming_order: OrderDB) -> List[TradeDB]:
    trades: List[TradeDB] = []

    matching_orders = get_matching_orders(
        session=session,
        symbol=incoming_order.symbol,
        side=incoming_order.side,
        price=incoming_order.price,
        incoming_account_id=incoming_order.account_id,
    )

    for resting_order in matching_orders:
        if incoming_order.filled_quantity >= incoming_order.quantity:
            break

        remaining_incoming = incoming_order.quantity - incoming_order.filled_quantity
        remaining_resting = resting_order.quantity - resting_order.filled_quantity
        match_qty = min(remaining_incoming, remaining_resting)

        # Resting order price sets execution price (price-time priority)
        match_price = resting_order.price

        if incoming_order.side == "buy":
            buy_order = incoming_order
            sell_order = resting_order
        else:
            buy_order = resting_order
            sell_order = incoming_order

        trade = execute_trade(
            session=session,
            buy_order=buy_order,
            sell_order=sell_order,
            price=match_price,
            quantity=match_qty,
        )
        trades.append(trade)

    return trades


def cancel_order(session: Session, order_id: int) -> OrderDB:
    order = session.get(OrderDB, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status not in (OrderStatus.OPEN.value, OrderStatus.PARTIALLY_FILLED.value):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel order with status '{order.status}'"
        )

    remaining_qty = order.quantity - order.filled_quantity
    if remaining_qty > 0:
        if order.side == "buy":
            account = session.get(AccountDB, order.account_id)
            if account is not None:
                release_buy_reservation(session, account, order, remaining_qty)
        elif order.side == "sell":
            holding = session.query(AccountHoldingDB).filter_by(
                account_id=order.account_id,
                symbol=order.symbol,
            ).first()
            if holding is not None:
                release_sell_reservation(session, holding, order, remaining_qty)

    order.status = OrderStatus.CANCELLED.value
    return order


def get_orderbook(session: Session, symbol: str) -> dict:
    active_statuses = [OrderStatus.OPEN.value, OrderStatus.PARTIALLY_FILLED.value]

    bids = (
        session.query(OrderDB)
        .filter(
            OrderDB.symbol == symbol,
            OrderDB.side == "buy",
            OrderDB.status.in_(active_statuses),
            OrderDB.quantity > OrderDB.filled_quantity,
        )
        .order_by(OrderDB.price.desc(), OrderDB.created_at.asc(), OrderDB.id.asc())
        .all()
    )

    asks = (
        session.query(OrderDB)
        .filter(
            OrderDB.symbol == symbol,
            OrderDB.side == "sell",
            OrderDB.status.in_(active_statuses),
            OrderDB.quantity > OrderDB.filled_quantity,
        )
        .order_by(OrderDB.price.asc(), OrderDB.created_at.asc(), OrderDB.id.asc())
        .all()
    )

    return {
        "symbol": symbol,
        "bids": [
            {
                "id": b.id,
                "price": b.price,
                "quantity": b.quantity - b.filled_quantity,
            }
            for b in bids
        ],
        "asks": [
            {
                "id": a.id,
                "price": a.price,
                "quantity": a.quantity - a.filled_quantity,
            }
            for a in asks
        ],
    }
