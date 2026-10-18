from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
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
from app.orderbook import (
    OrderNode,
    global_order_book_manager,
)


def submit_orders_batch(
    session: Session, order_requests: List[OrderRequest]
) -> List[OrderDB]:
    if not order_requests:
        return []

    orders: List[OrderDB] = []
    accounts_cache: Dict[int, AccountDB] = {}
    holdings_cache: Dict[Tuple[int, str], Optional[AccountHoldingDB]] = {}

    for req in order_requests:
        if req.account_id not in accounts_cache:
            acc = session.get(AccountDB, req.account_id)
            if acc is None:
                raise HTTPException(
                    status_code=404, detail=f"Account {req.account_id} not found"
                )
            accounts_cache[req.account_id] = acc
        account = accounts_cache[req.account_id]

        if req.side.value == "buy":
            required_cash = req.price * req.quantity
            available_cash = account.balance - account.reserved_balance

            if available_cash < required_cash:
                raise HTTPException(
                    status_code=400, detail="Insufficient available cash"
                )

            account.reserved_balance += required_cash

        elif req.side.value == "sell":
            h_key = (account.id, req.symbol)
            if h_key not in holdings_cache:
                h = (
                    session.query(AccountHoldingDB)
                    .filter_by(account_id=account.id, symbol=req.symbol)
                    .first()
                )
                holdings_cache[h_key] = h
            holding = holdings_cache[h_key]

            if holding is None:
                raise HTTPException(
                    status_code=400, detail="No holding found for symbol"
                )

            available_shares = holding.quantity - holding.reserved_quantity

            if available_shares < req.quantity:
                raise HTTPException(
                    status_code=400, detail="Insufficient available shares"
                )

            holding.reserved_quantity += req.quantity

        new_order = OrderDB(
            account_id=account.id,
            symbol=req.symbol,
            side=req.side.value,
            type=req.type.value,
            price=req.price,
            quantity=req.quantity,
            status=OrderStatus.OPEN.value,
            filled_quantity=0,
            created_at=datetime.now(timezone.utc),
        )
        session.add(new_order)
        orders.append(new_order)

    # Batch flush all orders to get IDs in a single DB operation
    session.flush()

    # Add to in-memory order book & match each order against resting book
    for order in orders:
        book = global_order_book_manager.get_book_for_symbol(order.symbol)
        book.add(
            OrderNode(
                id=order.id,
                account_id=order.account_id,
                symbol=order.symbol,
                side=order.side,
                price=order.price,
                quantity=order.quantity,
                filled_quantity=order.filled_quantity,
                status=order.status,
                created_at=order.created_at,
            )
        )
        match_orders(session, order)

    return orders


def submit_order(session: Session, order_request: OrderRequest) -> OrderDB:
    return submit_orders_batch(session, [order_request])[0]


def get_matching_orders(
    session: Session,
    symbol: str,
    side: str,
    price: int,
    incoming_account_id: Optional[int] = None,
) -> List[OrderDB]:
    global_order_book_manager.sync_recent(session)
    book = global_order_book_manager.get_book_for_symbol(symbol)
    in_memory_matches = book.get_matching_orders(side, price, incoming_account_id)

    matching_orders: List[OrderDB] = []
    for m in in_memory_matches:
        o = session.get(OrderDB, m.id)
        if (
            o is not None
            and o.status in (OrderStatus.OPEN.value, OrderStatus.PARTIALLY_FILLED.value)
            and o.quantity > o.filled_quantity
        ):
            matching_orders.append(o)

    return matching_orders


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

    # Update filled quantities and order statuses in DB
    update_order_fill(buy_order, quantity)
    update_order_fill(sell_order, quantity)

    # Update in-memory order books
    buy_book = global_order_book_manager.get_book_for_symbol(buy_order.symbol)
    buy_book.update_fill(buy_order.id, quantity)
    sell_book = global_order_book_manager.get_book_for_symbol(sell_order.symbol)
    sell_book.update_fill(sell_order.id, quantity)

    # Buyer accounting
    buyer_account = session.get(AccountDB, buy_order.account_id)
    if buyer_account is not None:
        actual_cost = price * quantity
        buyer_account.balance -= actual_cost
        # Release the reservation for the filled quantity at order's limit price
        buyer_account.reserved_balance -= buy_order.price * quantity

    buyer_holding = (
        session.query(AccountHoldingDB)
        .filter_by(
            account_id=buy_order.account_id,
            symbol=buy_order.symbol,
        )
        .first()
    )

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

    seller_holding = (
        session.query(AccountHoldingDB)
        .filter_by(
            account_id=sell_order.account_id,
            symbol=sell_order.symbol,
        )
        .first()
    )

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
            detail=f"Cannot cancel order with status '{order.status}'",
        )

    remaining_qty = order.quantity - order.filled_quantity
    if remaining_qty > 0:
        if order.side == "buy":
            account = session.get(AccountDB, order.account_id)
            if account is not None:
                release_buy_reservation(session, account, order, remaining_qty)
        elif order.side == "sell":
            holding = (
                session.query(AccountHoldingDB)
                .filter_by(
                    account_id=order.account_id,
                    symbol=order.symbol,
                )
                .first()
            )
            if holding is not None:
                release_sell_reservation(session, holding, order, remaining_qty)

    order.status = OrderStatus.CANCELLED.value
    # Remove from in-memory book
    book = global_order_book_manager.get_book_for_symbol(order.symbol)
    book.remove(order.id)

    return order


def get_orderbook(session: Session, symbol: str) -> dict:
    global_order_book_manager.sync_recent(session)
    book = global_order_book_manager.get_book_for_symbol(symbol)
    return book.to_dict()
