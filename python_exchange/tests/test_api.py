from fastapi.testclient import TestClient
from app.database import SessionLocal
from app.main import app
from app.models import AccountHoldingDB

client = TestClient(app)


def test_api_create_and_get_order():
    response = client.post(
        "/orders",
        json={
            "symbol": "AAPL",
            "side": "buy",
            "type": "limit",
            "price": 150,
            "quantity": 10,
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["symbol"] == "AAPL"
    assert data["side"] == "buy"
    assert data["status"] == "open"
    order_id = data["id"]

    # Get single order
    get_res = client.get(f"/orders/{order_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == order_id


def test_api_orders_filtering():
    # Submit one AAPL and one MSFT order
    client.post(
        "/orders",
        json={"symbol": "AAPL", "side": "buy", "price": 100, "quantity": 1},
    )
    client.post(
        "/orders",
        json={"symbol": "MSFT", "side": "buy", "price": 200, "quantity": 1},
    )

    # Filter by symbol
    res_aapl = client.get("/orders?symbol=AAPL")
    assert res_aapl.status_code == 200
    orders_aapl = res_aapl.json()
    assert len(orders_aapl) == 1
    assert orders_aapl[0]["symbol"] == "AAPL"

    # Filter by status
    res_open = client.get("/orders?status=open")
    assert res_open.status_code == 200
    assert len(res_open.json()) >= 2


def test_api_cancel_order():
    res = client.post(
        "/orders",
        json={"symbol": "AAPL", "side": "buy", "price": 100, "quantity": 5},
    )
    order_id = res.json()["id"]

    del_res = client.delete(f"/orders/{order_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "cancelled"

    # Attempt to cancel again should fail with 400
    del_res2 = client.delete(f"/orders/{order_id}")
    assert del_res2.status_code == 400


def test_api_account_and_holdings():
    # Check account
    res = client.get("/account")
    assert res.status_code == 200
    data = res.json()
    assert data["account_id"] == 1
    assert data["balance"] == 10000000

    # Add holding to database
    with SessionLocal() as session:
        session.add(
            AccountHoldingDB(
                account_id=1, symbol="GOOGL", quantity=10, reserved_quantity=2
            )
        )
        session.commit()

    res_h = client.get("/holdings")
    assert res_h.status_code == 200
    holdings = res_h.json()
    assert len(holdings) == 1
    assert holdings[0]["symbol"] == "GOOGL"
    assert holdings[0]["quantity"] == 10
    assert holdings[0]["reserved_quantity"] == 2
    assert holdings[0]["available_quantity"] == 8


def test_api_trades_and_orderbook():
    # Seed holding for account 2
    with SessionLocal() as session:
        session.add(
            AccountHoldingDB(
                account_id=2, symbol="AAPL", quantity=20, reserved_quantity=0
            )
        )
        session.commit()

    # Seller rests
    client.post(
        "/orders",
        json={
            "account_id": 2,
            "symbol": "AAPL",
            "side": "sell",
            "price": 150,
            "quantity": 10,
        },
    )

    # Orderbook shows 1 ask
    ob_res = client.get("/orderbook/AAPL")
    assert ob_res.status_code == 200
    book = ob_res.json()
    assert len(book["asks"]) == 1
    assert book["asks"][0]["price"] == 150

    # Buyer matches
    client.post(
        "/orders",
        json={
            "account_id": 1,
            "symbol": "AAPL",
            "side": "buy",
            "price": 150,
            "quantity": 10,
        },
    )

    # Trades endpoint returns trade
    trades_res = client.get("/trades?symbol=AAPL")
    assert trades_res.status_code == 200
    trades = trades_res.json()
    assert len(trades) == 1
    assert trades[0]["price"] == 150
    assert trades[0]["quantity"] == 10


def test_api_portfolio():
    # Check portfolio endpoint
    res = client.get("/portfolio")
    assert res.status_code == 200
    data = res.json()
    assert "cash_balance" in data
    assert "total_portfolio_value" in data
    assert "total_unrealized_pnl" in data
    assert "holdings" in data


def test_api_batch_orders():
    # Submit batch of 3 buy orders in a single transaction
    orders_payload = [
        {"account_id": 1, "symbol": "AAPL", "side": "buy", "price": 100, "quantity": 2},
        {"account_id": 1, "symbol": "MSFT", "side": "buy", "price": 200, "quantity": 1},
        {"account_id": 1, "symbol": "TSLA", "side": "buy", "price": 300, "quantity": 1},
    ]
    res = client.post("/orders/batch", json=orders_payload)
    assert res.status_code == 201
    created = res.json()
    assert len(created) == 3
    order_ids = [o["id"] for o in created]

    # Batch get
    get_res = client.post("/orders/batch-get", json={"order_ids": order_ids})
    assert get_res.status_code == 200
    retrieved = get_res.json()
    assert len(retrieved) == 3
    assert [o["id"] for o in retrieved] == order_ids

