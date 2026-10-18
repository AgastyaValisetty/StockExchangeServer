from app.orderbook import (
    OrderNode,
    PriceLevel,
    RedBlackTree,
    SymbolOrderBook,
)


def test_red_black_tree_invariants():
    tree = RedBlackTree()
    prices = [150, 140, 160, 130, 170, 145, 155]

    for p in prices:
        tree.insert(p, PriceLevel(p))

    # Inorder should be strictly ascending
    ascending_prices = [level.price for level in tree.inorder()]
    assert ascending_prices == [130, 140, 145, 150, 155, 160, 170]

    # Reverse inorder should be strictly descending
    descending_prices = [level.price for level in tree.reverse_inorder()]
    assert descending_prices == [170, 160, 155, 150, 145, 140, 130]

    # Min and Max
    assert tree.min_node().key == 130
    assert tree.max_node().key == 170

    # Delete node and verify balance
    tree.delete(150)
    assert tree.find(150) is None
    assert [level.price for level in tree.inorder()] == [130, 140, 145, 155, 160, 170]


def test_price_level_fifo_linked_list():
    level = PriceLevel(100)
    o1 = OrderNode(1, 1, "AAPL", "buy", 100, 10)
    o2 = OrderNode(2, 1, "AAPL", "buy", 100, 20)
    o3 = OrderNode(3, 1, "AAPL", "buy", 100, 30)

    level.append(o1)
    level.append(o2)
    level.append(o3)

    assert level.count == 3
    assert level.total_volume == 60
    assert [n.id for n in level.nodes()] == [1, 2, 3]

    # Remove middle node in O(1)
    level.remove(o2)
    assert level.count == 2
    assert level.total_volume == 40
    assert [n.id for n in level.nodes()] == [1, 3]

    # Remove head
    level.remove(o1)
    assert [n.id for n in level.nodes()] == [3]

    # Remove tail
    level.remove(o3)
    assert level.is_empty()
    assert level.total_volume == 0


def test_symbol_order_book_price_time_priority():
    book = SymbolOrderBook("AAPL")

    # Add 3 sell orders: two at 150 (different times), one at 145 (better price)
    o1 = OrderNode(1, 1, "AAPL", "sell", 150, 10)
    o2 = OrderNode(2, 1, "AAPL", "sell", 145, 5)
    o3 = OrderNode(3, 1, "AAPL", "sell", 150, 15)

    book.add(o1)
    book.add(o2)
    book.add(o3)

    # Buy incoming at 155 -> matching should return 145 first (price priority), then o1 before o3 (time priority)
    matches = book.get_matching_orders("buy", 155)
    assert [m.id for m in matches] == [2, 1, 3]


def test_direct_order_cancellation():
    book = SymbolOrderBook("AAPL")
    o1 = OrderNode(1, 1, "AAPL", "buy", 100, 10)
    book.add(o1)

    assert 1 in book.orders
    assert book.bids.find(100) is not None

    # Cancel order
    cancelled = book.remove(1)
    assert cancelled is not None
    assert 1 not in book.orders
    # Price level was empty so it should be removed from the RB tree
    assert book.bids.find(100) is None


def test_order_book_fill_updates():
    book = SymbolOrderBook("AAPL")
    o1 = OrderNode(1, 1, "AAPL", "buy", 100, 20)
    book.add(o1)

    # Partial fill
    book.update_fill(1, 5)
    assert o1.status == "partially_filled"
    assert o1.filled_quantity == 5
    assert book.orders[1].filled_quantity == 5

    # Full fill
    book.update_fill(1, 15)
    assert 1 not in book.orders
    assert book.bids.find(100) is None
