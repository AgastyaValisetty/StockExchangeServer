from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

# Color constants for Red-Black Tree
RED = 0
BLACK = 1


class OrderNode:
    """Intrusive doubly-linked list node representing an order in the book."""

    def __init__(
        self,
        id: int,
        account_id: int,
        symbol: str,
        side: str,
        price: int,
        quantity: int,
        filled_quantity: int = 0,
        status: str = "open",
        created_at: Optional[datetime] = None,
    ):
        self.id = id
        self.account_id = account_id
        self.symbol = symbol.strip().upper()
        self.side = side
        self.price = price
        self.quantity = quantity
        self.filled_quantity = filled_quantity
        self.status = status
        self.created_at = created_at

        # Pointers for doubly-linked FIFO list within price level
        self.prev: Optional["OrderNode"] = None
        self.next: Optional["OrderNode"] = None
        self.price_level: Optional["PriceLevel"] = None


class PriceLevel:
    """Maintains a doubly linked FIFO queue of orders at a specific price."""

    def __init__(self, price: int):
        self.price = price
        self.head: Optional[OrderNode] = None
        self.tail: Optional[OrderNode] = None
        self.count: int = 0
        self.total_volume: int = 0

    def append(self, node: OrderNode) -> None:
        """Append order to the tail of the FIFO queue (O(1))."""
        node.price_level = self
        node.prev = self.tail
        node.next = None
        if self.tail:
            self.tail.next = node
        else:
            self.head = node
        self.tail = node

        rem = node.quantity - node.filled_quantity
        self.total_volume += rem if rem > 0 else 0
        self.count += 1

    def remove(self, node: OrderNode) -> None:
        """Remove order node from linked list via direct pointers (O(1))."""
        if node.prev:
            node.prev.next = node.next
        else:
            self.head = node.next

        if node.next:
            node.next.prev = node.prev
        else:
            self.tail = node.prev

        rem = node.quantity - node.filled_quantity
        self.total_volume -= rem if rem > 0 else 0
        self.count -= 1

        node.prev = None
        node.next = None
        node.price_level = None

    def is_empty(self) -> bool:
        return self.head is None

    def nodes(self) -> List[OrderNode]:
        """Iterate in strict FIFO time-priority order."""
        curr = self.head
        res = []
        while curr:
            res.append(curr)
            curr = curr.next
        return res


class RBNode:
    """Node in the Red-Black Tree."""

    def __init__(self, key=None, val: Optional[PriceLevel] = None, color=BLACK):
        self.key = key
        self.val: Optional[PriceLevel] = val
        self.color = color
        self.left: "RBNode" = self
        self.right: "RBNode" = self
        self.parent: "RBNode" = self


class RedBlackTree:
    """Balanced Red-Black Search Tree for price levels."""

    def __init__(self):
        self.NIL = RBNode()
        self.NIL.left = self.NIL
        self.NIL.right = self.NIL
        self.root = self.NIL
        self.size = 0

    def _left_rotate(self, x: RBNode) -> None:
        y = x.right
        x.right = y.left
        if y.left != self.NIL:
            y.left.parent = x
        y.parent = x.parent
        if x.parent == self.NIL:
            self.root = y
        elif x == x.parent.left:
            x.parent.left = y
        else:
            x.parent.right = y
        y.left = x
        x.parent = y

    def _right_rotate(self, x: RBNode) -> None:
        y = x.left
        x.left = y.right
        if y.right != self.NIL:
            y.right.parent = x
        y.parent = x.parent
        if x.parent == self.NIL:
            self.root = y
        elif x == x.parent.right:
            x.parent.right = y
        else:
            x.parent.left = y
        y.right = x
        x.parent = y

    def insert(self, key: int, val: PriceLevel) -> RBNode:
        z = RBNode(key, val, color=RED)
        z.left = self.NIL
        z.right = self.NIL
        y = self.NIL
        x = self.root

        while x != self.NIL:
            y = x
            if z.key < x.key:
                x = x.left
            elif z.key > x.key:
                x = x.right
            else:
                x.val = val
                return x

        z.parent = y
        if y == self.NIL:
            self.root = z
        elif z.key < y.key:
            y.left = z
        else:
            y.right = z

        self.size += 1
        self._insert_fixup(z)
        return z

    def _insert_fixup(self, z: RBNode) -> None:
        while z.parent.color == RED:
            if z.parent == z.parent.parent.left:
                y = z.parent.parent.right
                if y.color == RED:
                    z.parent.color = BLACK
                    y.color = BLACK
                    z.parent.parent.color = RED
                    z = z.parent.parent
                else:
                    if z == z.parent.right:
                        z = z.parent
                        self._left_rotate(z)
                    z.parent.color = BLACK
                    z.parent.parent.color = RED
                    self._right_rotate(z.parent.parent)
            else:
                y = z.parent.parent.left
                if y.color == RED:
                    z.parent.color = BLACK
                    y.color = BLACK
                    z.parent.parent.color = RED
                    z = z.parent.parent
                else:
                    if z == z.parent.left:
                        z = z.parent
                        self._right_rotate(z)
                    z.parent.color = BLACK
                    z.parent.parent.color = RED
                    self._left_rotate(z.parent.parent)
        self.root.color = BLACK

    def find(self, key: int) -> Optional[RBNode]:
        x = self.root
        while x != self.NIL:
            if key == x.key:
                return x
            elif key < x.key:
                x = x.left
            else:
                x = x.right
        return None

    def min_node(self, node: Optional[RBNode] = None) -> Optional[RBNode]:
        if node is None:
            node = self.root
        if node == self.NIL:
            return None
        while node.left != self.NIL:
            node = node.left
        return node

    def max_node(self, node: Optional[RBNode] = None) -> Optional[RBNode]:
        if node is None:
            node = self.root
        if node == self.NIL:
            return None
        while node.right != self.NIL:
            node = node.right
        return node

    def _transplant(self, u: RBNode, v: RBNode) -> None:
        if u.parent == self.NIL:
            self.root = v
        elif u == u.parent.left:
            u.parent.left = v
        else:
            u.parent.right = v
        v.parent = u.parent

    def delete(self, key: int) -> bool:
        z = self.find(key)
        if z is None or z == self.NIL:
            return False

        y = z
        y_original_color = y.color
        if z.left == self.NIL:
            x = z.right
            self._transplant(z, z.right)
        elif z.right == self.NIL:
            x = z.left
            self._transplant(z, z.left)
        else:
            y = self.min_node(z.right)
            y_original_color = y.color
            x = y.right
            if y.parent == z:
                x.parent = y
            else:
                self._transplant(y, y.right)
                y.right = z.right
                y.right.parent = y
            self._transplant(z, y)
            y.left = z.left
            y.left.parent = y
            y.color = z.color

        self.size -= 1
        if y_original_color == BLACK:
            self._delete_fixup(x)
        return True

    def _delete_fixup(self, x: RBNode) -> None:
        while x != self.root and x.color == BLACK:
            if x == x.parent.left:
                w = x.parent.right
                if w.color == RED:
                    w.color = BLACK
                    x.parent.color = RED
                    self._left_rotate(x.parent)
                    w = x.parent.right
                if w.left.color == BLACK and w.right.color == BLACK:
                    w.color = RED
                    x = x.parent
                else:
                    if w.right.color == BLACK:
                        w.left.color = BLACK
                        w.color = RED
                        self._right_rotate(w)
                        w = x.parent.right
                    w.color = x.parent.color
                    x.parent.color = BLACK
                    w.right.color = BLACK
                    self._left_rotate(x.parent)
                    x = self.root
            else:
                w = x.parent.left
                if w.color == RED:
                    w.color = BLACK
                    x.parent.color = RED
                    self._right_rotate(x.parent)
                    w = x.parent.left
                if w.right.color == BLACK and w.left.color == BLACK:
                    w.color = RED
                    x = x.parent
                else:
                    if w.left.color == BLACK:
                        w.right.color = BLACK
                        w.color = RED
                        self._left_rotate(w)
                        w = x.parent.left
                    w.color = x.parent.color
                    x.parent.color = BLACK
                    w.left.color = BLACK
                    self._right_rotate(x.parent)
                    x = self.root
        x.color = BLACK

    def inorder(self, node: Optional[RBNode] = None) -> List[PriceLevel]:
        """In-order traversal returning price levels in ascending order."""
        if node is None:
            node = self.root
        if node == self.NIL:
            return []
        res: List[PriceLevel] = []
        stack = []
        curr = node
        while stack or curr != self.NIL:
            while curr != self.NIL:
                stack.append(curr)
                curr = curr.left
            curr = stack.pop()
            if curr.val:
                res.append(curr.val)
            curr = curr.right
        return res

    def reverse_inorder(self, node: Optional[RBNode] = None) -> List[PriceLevel]:
        """Reverse in-order traversal returning price levels in descending order."""
        if node is None:
            node = self.root
        if node == self.NIL:
            return []
        res: List[PriceLevel] = []
        stack = []
        curr = node
        while stack or curr != self.NIL:
            while curr != self.NIL:
                stack.append(curr)
                curr = curr.right
            curr = stack.pop()
            if curr.val:
                res.append(curr.val)
            curr = curr.left
        return res


class SymbolOrderBook:
    """In-memory order book for a single symbol using Red-Black trees and linked lists."""

    def __init__(self, symbol: str):
        self.symbol = symbol.strip().upper()
        # Separate balanced Red-Black trees for Bids and Asks
        self.bids: RedBlackTree = RedBlackTree()
        self.asks: RedBlackTree = RedBlackTree()
        # Direct O(1) hash map lookup by order ID
        self.orders: Dict[int, OrderNode] = {}

    def add(self, node: OrderNode) -> None:
        if node.status not in ("open", "partially_filled"):
            return
        if node.filled_quantity >= node.quantity:
            return

        # If already present, remove prior entry
        if node.id in self.orders:
            self.remove(node.id)

        self.orders[node.id] = node
        tree = self.bids if node.side == "buy" else self.asks

        rb_node = tree.find(node.price)
        if rb_node is None:
            level = PriceLevel(node.price)
            tree.insert(node.price, level)
        else:
            level = rb_node.val

        level.append(node)

    def remove(self, order_id: int) -> Optional[OrderNode]:
        """O(1) cancellation via direct pointer and price-level removal."""
        node = self.orders.pop(order_id, None)
        if node is None:
            return None

        level = node.price_level
        if level is not None:
            level.remove(node)
            if level.is_empty():
                tree = self.bids if node.side == "buy" else self.asks
                tree.delete(node.price)

        return node

    def update_fill(self, order_id: int, fill_qty: int) -> None:
        node = self.orders.get(order_id)
        if node is None:
            return

        node.filled_quantity += fill_qty
        if node.filled_quantity >= node.quantity:
            node.status = "filled"
            self.remove(order_id)
        else:
            node.status = "partially_filled"
            if node.price_level is not None:
                node.price_level.total_volume -= fill_qty

    def get_matching_orders(
        self,
        side: str,
        price: int,
        incoming_account_id: Optional[int] = None,
    ) -> List[OrderNode]:
        matches: List[OrderNode] = []
        if side == "buy":
            # Match sells (asks) <= price, lowest price first (ascending)
            for level in self.asks.inorder():
                if level.price > price:
                    break
                for node in level.nodes():
                    if incoming_account_id is not None and node.account_id == incoming_account_id:
                        continue
                    if node.quantity > node.filled_quantity:
                        matches.append(node)
        else:
            # Match buys (bids) >= price, highest price first (descending)
            for level in self.bids.reverse_inorder():
                if level.price < price:
                    break
                for node in level.nodes():
                    if incoming_account_id is not None and node.account_id == incoming_account_id:
                        continue
                    if node.quantity > node.filled_quantity:
                        matches.append(node)

        return matches

    def to_dict(self) -> dict:
        bids_list = []
        for level in self.bids.reverse_inorder():
            for node in level.nodes():
                rem = node.quantity - node.filled_quantity
                if rem > 0:
                    bids_list.append({
                        "id": node.id,
                        "price": node.price,
                        "quantity": rem,
                    })

        asks_list = []
        for level in self.asks.inorder():
            for node in level.nodes():
                rem = node.quantity - node.filled_quantity
                if rem > 0:
                    asks_list.append({
                        "id": node.id,
                        "price": node.price,
                        "quantity": rem,
                    })

        return {
            "symbol": self.symbol,
            "bids": bids_list,
            "asks": asks_list,
        }


class OrderBookManager:
    """Manages all symbol order books, persistence hydration, and synchronization."""

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
                OrderNode(
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
                    OrderNode(
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
