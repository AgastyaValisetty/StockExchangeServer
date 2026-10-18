from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session


@dataclass
class BookOrder:
    id: int
    account_id: int
    symbol: str
    side: str
    price: int
    quantity: int
    filled_quantity: int
    status: str
    created_at: Optional[datetime] = None


class SymbolOrderBook:
    def __init__(self, symbol: str):
        self.symbol = symbol.upper()
        # price -> list of BookOrder (FIFO order per price level)
        self.bids: Dict[int, List[BookOrder]] = defaultdict(list)
        self.asks: Dict[int, List[BookOrder]] = defaultdict(list)
        self.orders: Dict[int, BookOrder] = {}

    def add(self, order: BookOrder) -> None:
        if order.status not in ("open", "partially_filled"):
            return
        if order.filled_quantity >= order.quantity:
            return

        # Avoid duplicates
        if order.id in self.orders:
            self.remove(order.id)

        self.orders[order.id] = order
        if order.side == "buy":
            self.bids[order.price].append(order)
        else:
            self.asks[order.price].append(order)

    def remove(self, order_id: int) -> Optional[BookOrder]:
        order = self.orders.pop(order_id, None)
        if not order:
            return None
        book = self.bids if order.side == "buy" else self.asks
        if order.price in book:
            book[order.price] = [o for o in book[order.price] if o.id != order_id]
            if not book[order.price]:
                del book[order.price]
        return order

    def update_fill(self, order_id: int, fill_qty: int) -> None:
        order = self.orders.get(order_id)
        if not order:
            return
        order.filled_quantity += fill_qty
        if order.filled_quantity >= order.quantity:
            order.status = "filled"
            self.remove(order_id)
        else:
            order.status = "partially_filled"

    def get_matching_orders(
        self,
        side: str,
        price: int,
        incoming_account_id: Optional[int] = None,
    ) -> List[BookOrder]:
        matches: List[BookOrder] = []
        if side == "buy":
            # Match sells (asks) <= price, sorted price ascending (cheapest first)
            for ask_price in sorted(self.asks.keys()):
                if ask_price > price:
                    break
                for o in self.asks[ask_price]:
                    if incoming_account_id is not None and o.account_id == incoming_account_id:
                        continue
                    if o.quantity > o.filled_quantity:
                        matches.append(o)
        else:
            # Match buys (bids) >= price, sorted price descending (highest first)
            for bid_price in sorted(self.bids.keys(), reverse=True):
                if bid_price < price:
                    break
                for o in self.bids[bid_price]:
                    if incoming_account_id is not None and o.account_id == incoming_account_id:
                        continue
                    if o.quantity > o.filled_quantity:
                        matches.append(o)
        return matches

    def to_dict(self) -> dict:
        sorted_bid_prices = sorted(self.bids.keys(), reverse=True)
        sorted_ask_prices = sorted(self.asks.keys())

        bids_list = []
        for p in sorted_bid_prices:
            for o in self.bids[p]:
                rem = o.quantity - o.filled_quantity
                if rem > 0:
                    bids_list.append({"id": o.id, "price": o.price, "quantity": rem})

        asks_list = []
        for p in sorted_ask_prices:
            for o in self.asks[p]:
                rem = o.quantity - o.filled_quantity
                if rem > 0:
                    asks_list.append({"id": o.id, "price": o.price, "quantity": rem})

        return {
            "symbol": self.symbol,
            "bids": bids_list,
            "asks": asks_list,
        }


class OrderBookManager:
    def __init__(self):
        self.books: Dict[str, SymbolOrderBook] = {}
        self.last_synced_id: int = 0
        self.last_sync_time: float = 0.0
        self._initialized: bool = False

    def get_book_for_symbol(self, symbol: str) -> SymbolOrderBook:
        s = symbol.strip().upper()
        if s not in self.books:
            self.books[s] = SymbolOrderBook(s)
        return self.books[s]

    def recover_from_db(self, session: Session) -> None:
        import time
        from app.models import OrderDB

        self.books.clear()
        active_orders = (
            session.query(OrderDB)
            .filter(OrderDB.status.in_(["open", "partially_filled"]))
            .filter(OrderDB.quantity > OrderDB.filled_quantity)
            .order_by(OrderDB.id.asc())
            .all()
        )
        max_id = 0
        for o in active_orders:
            book = self.get_book_for_symbol(o.symbol)
            book.add(
                BookOrder(
                    id=o.id,
                    account_id=o.account_id,
                    symbol=o.symbol,
                    side=o.side,
                    price=o.price,
                    quantity=o.quantity,
                    filled_quantity=o.filled_quantity,
                    status=o.status,
                    created_at=o.created_at,
                )
            )
            if o.id > max_id:
                max_id = o.id
        self.last_synced_id = max_id
        self.last_sync_time = time.monotonic()
        self._initialized = True

    def sync_recent(self, session: Session, min_interval_seconds: float = 0.1) -> None:
        import time
        from app.models import OrderDB

        now = time.monotonic()
        if not self._initialized:
            self.recover_from_db(session)
            return

        # Throttle DB sync so high-frequency queries read purely from memory
        if (now - self.last_sync_time) < min_interval_seconds:
            return
        self.last_sync_time = now

        new_orders = (
            session.query(OrderDB)
            .filter(OrderDB.id > self.last_synced_id)
            .order_by(OrderDB.id.asc())
            .all()
        )
        for o in new_orders:
            if o.id > self.last_synced_id:
                self.last_synced_id = o.id
            book = self.get_book_for_symbol(o.symbol)
            if o.status in ("open", "partially_filled") and o.quantity > o.filled_quantity:
                book.add(
                    BookOrder(
                        id=o.id,
                        account_id=o.account_id,
                        symbol=o.symbol,
                        side=o.side,
                        price=o.price,
                        quantity=o.quantity,
                        filled_quantity=o.filled_quantity,
                        status=o.status,
                        created_at=o.created_at,
                    )
                )
            elif o.status in ("filled", "cancelled"):
                book.remove(o.id)


# Global singleton instance
global_order_book_manager = OrderBookManager()
