# Stock Exchange Server - API Documentation & Architecture Reference

This document provides a complete reference for all REST API endpoints, internal service/engine functions, data models, and load testing instructions.

---

## 1. REST API Endpoints

Base URL: `http://localhost:8000`

### 1.1 `POST /orders`
- **Purpose**: Submit a new limit buy or sell order. Validates available cash or shares, reserves them, creates the order record, and executes immediate matching against resting counter-orders.
- **Status Code**: `201 Created` on success; `400 Bad Request` on insufficient funds/shares or invalid input; `404 Not Found` if account does not exist.
- **Request Body (JSON)**:
  ```json
  {
    "symbol": "AAPL",
    "side": "buy",
    "type": "limit",
    "price": 150,
    "quantity": 10,
    "account_id": 1
  }
  ```
- **Response (JSON)**:
  ```json
  {
    "id": 1,
    "account_id": 1,
    "symbol": "AAPL",
    "side": "buy",
    "type": "limit",
    "price": 150,
    "quantity": 10,
    "status": "open",
    "filled_quantity": 0,
    "created_at": "2026-10-18T14:38:00.000000+00:00"
  }
  ```

---

### 1.2 `GET /orders`
- **Purpose**: List all orders with optional filtering by symbol and status.
- **Query Parameters**:
  - `symbol` *(optional, string)*: e.g. `AAPL`
  - `status` *(optional, string)*: e.g. `open`, `partially_filled`, `filled`, `cancelled`
- **Response (JSON)**:
  ```json
  [
    {
      "id": 1,
      "account_id": 1,
      "symbol": "AAPL",
      "side": "buy",
      "type": "limit",
      "price": 150,
      "quantity": 10,
      "status": "open",
      "filled_quantity": 0,
      "created_at": "2026-10-18T14:38:00.000000+00:00"
    }
  ]
  ```

---

### 1.3 `GET /orders/{id}`
- **Purpose**: Retrieve order details and execution fill progress by ID.
- **Path Parameters**:
  - `id` *(integer, required)*: Order ID
- **Status Codes**: `200 OK` or `404 Not Found`.
- **Response (JSON)**:
  ```json
  {
    "id": 1,
    "account_id": 1,
    "symbol": "AAPL",
    "side": "buy",
    "type": "limit",
    "price": 150,
    "quantity": 10,
    "status": "partially_filled",
    "filled_quantity": 4,
    "created_at": "2026-10-18T14:38:00.000000+00:00"
  }
  ```

---

### 1.4 `DELETE /orders/{id}`
- **Purpose**: Cancel an open or partially filled order. Releases any unused cash or share reservations.
- **Path Parameters**:
  - `id` *(integer, required)*: Order ID
- **Status Codes**: `200 OK`, `400 Bad Request` (if order is already filled or cancelled), or `404 Not Found`.
- **Response (JSON)**:
  ```json
  {
    "id": 1,
    "account_id": 1,
    "symbol": "AAPL",
    "side": "buy",
    "type": "limit",
    "price": 150,
    "quantity": 10,
    "status": "cancelled",
    "filled_quantity": 4,
    "message": "Order cancelled successfully"
  }
  ```

---

### 1.5 `GET /account`
- **Purpose**: Retrieve account balances (total balance, reserved cash, and available cash).
- **Query Parameters**:
  - `account_id` *(optional, integer, default: 1)*
- **Response (JSON)**:
  ```json
  {
    "account_id": 1,
    "balance": 10000000,
    "reserved_balance": 15000,
    "available_balance": 9985000
  }
  ```

---

### 1.6 `GET /holdings`
- **Purpose**: Retrieve share holdings for an account (owned shares, reserved shares, and available shares per symbol).
- **Query Parameters**:
  - `account_id` *(optional, integer, default: 1)*
- **Response (JSON)**:
  ```json
  [
    {
      "symbol": "AAPL",
      "quantity": 50,
      "reserved_quantity": 10,
      "available_quantity": 40
    }
  ]
  ```

---

### 1.7 `GET /trades`
- **Purpose**: List executed trades and their execution prices/quantities.
- **Query Parameters**:
  - `symbol` *(optional, string)*: Filter by ticker symbol
  - `order_id` *(optional, integer)*: Filter by buy or sell order ID
- **Response (JSON)**:
  ```json
  [
    {
      "id": 1,
      "buy_order_id": 1,
      "sell_order_id": 2,
      "price": 150,
      "quantity": 10,
      "executed_at": "2026-10-18T14:38:05.000000+00:00"
    }
  ]
  ```

---

### 1.8 `GET /orderbook/{symbol}`
- **Purpose**: Display open bids (buys) and asks (sells) for a symbol, sorted by price-time priority.
  - Bids: ordered by `price DESC, created_at ASC`
  - Asks: ordered by `price ASC, created_at ASC`
- **Path Parameters**:
  - `symbol` *(string, required)*: e.g. `AAPL`
- **Response (JSON)**:
  ```json
  {
    "symbol": "AAPL",
    "bids": [
      { "id": 1, "price": 150, "quantity": 10 }
    ],
    "asks": [
      { "id": 2, "price": 155, "quantity": 5 }
    ]
  }
  ```

---

### 1.9 `GET /portfolio`
- **Purpose**: Calculates total portfolio value and unrealized profit/loss (P&L) across all stock holdings using simulated/market prices.
- **Query Parameters**:
  - `account_id` *(optional, integer, default: 1)*
- **Response (JSON)**:
  ```json
  {
    "account_id": 1,
    "cash_balance": 9985000,
    "reserved_cash": 15000,
    "available_cash": 9970000,
    "holdings_value": 750000,
    "total_portfolio_value": 10735000,
    "total_unrealized_pnl": 50000,
    "holdings": [
      {
        "symbol": "AAPL",
        "quantity": 50,
        "market_price": 15000,
        "current_value": 750000,
        "cost_basis": 700000,
        "unrealized_pnl": 50000
      }
    ]
  }
  ```

---

## 2. Core Functions & Internal Modules

### 2.1 Engine Module (`app/engine.py`)

| Function | Arguments | Description | Return |
|---|---|---|---|
| `submit_order()` | `session: Session, order_request: OrderRequest` | Validates cash/share availability, reserves funds or shares, writes order to DB, and executes order matching. | `OrderDB` |
| `get_matching_orders()` | `session: Session, symbol: str, side: str, price: int, incoming_account_id: Optional[int]` | Queries compatible resting orders (`buy_price >= sell_price`) with self-trade prevention (`account_id != incoming_account_id`) sorted by price-time priority. | `List[OrderDB]` |
| `match_orders()` | `session: Session, incoming_order: OrderDB` | Loops through compatible resting orders until incoming order is filled or book is exhausted. | `List[TradeDB]` |
| `execute_trade()` | `session: Session, buy_order: OrderDB, sell_order: OrderDB, price: int, quantity: int` | Creates a `TradeDB` record, adjusts order fills, and settles accounts/holdings atomically. | `TradeDB` |
| `update_order_fill()` | `order: OrderDB, fill_qty: int` | Increments `filled_quantity` and updates status to `partially_filled` or `filled`. | `None` |
| `release_buy_reservation()` | `session: Session, account: AccountDB, order: OrderDB, released_qty: int` | Releases reserved cash (`order.price * released_qty`). | `None` |
| `release_sell_reservation()` | `session: Session, holding: AccountHoldingDB, order: OrderDB, released_qty: int` | Releases reserved shares (`released_qty`). | `None` |
| `cancel_order()` | `session: Session, order_id: int` | Validates cancellation eligibility, releases remaining reservations, and marks status `cancelled`. | `OrderDB` |
| `get_orderbook()` | `session: Session, symbol: str` | Retrieves active bids and asks with unfilled quantities formatted for book view. | `dict` |

### 2.2 Service Module (`app/service.py`)

| Function | Arguments | Description | Return |
|---|---|---|---|
| `create_order()` | `order_request: OrderRequest` | Wraps `engine.submit_order()` in an atomic session transaction with commit and error handling. | `OrderDB` |
| `cancel_order()` | `order_id: int` | Wraps `engine.cancel_order()` in a transactional session commit. | `OrderDB` |
| `get_order()` | `order_id: int` | Fetches an order by ID or raises HTTP 404. | `OrderDB` |
| `list_orders()` | `symbol: Optional[str], status: Optional[str]` | Queries order list with optional symbol and status filters. | `List[dict]` |
| `get_account()` | `account_id: int = 1` | Retrieves balance, reserved cash, and available cash. | `dict` |
| `get_holdings()` | `account_id: int = 1` | Retrieves owned, reserved, and available quantities per symbol. | `List[dict]` |
| `get_trades()` | `symbol: Optional[str], order_id: Optional[int]` | Retrieves executed trades matching criteria. | `List[dict]` |
| `get_orderbook()` | `symbol: str` | Calls `engine.get_orderbook()`. | `dict` |
| `get_market_price()` | `session: Session, symbol: str` | Resolves market price via last trade price, latest order, or simulated pricing. | `int` |
| `get_portfolio()` | `account_id: int = 1` | Computes portfolio net worth, holding value, and unrealized P&L. | `dict` |

---

## 3. Database Schema (`app/models.py`)

1. **`AccountDB` (`accounts`)**
   - `id`: Primary Key (Integer)
   - `balance`: Total cash in paise (Integer, >= 0)
   - `reserved_balance`: Reserved cash in paise (Integer, >= 0, <= balance)

2. **`AccountHoldingDB` (`account_holdings`)**
   - `id`: Primary Key (Integer)
   - `account_id`: Foreign Key (`accounts.id`)
   - `symbol`: Ticker symbol (VARCHAR(10))
   - `quantity`: Total shares owned (Integer, >= 0)
   - `reserved_quantity`: Reserved shares for open sells (Integer, >= 0, <= quantity)
   - Unique Constraint: `(account_id, symbol)`

3. **`OrderDB` (`orders`)**
   - `id`: Primary Key (Integer)
   - `account_id`: Foreign Key (`accounts.id`)
   - `symbol`: Stock symbol (VARCHAR(10), indexed)
   - `side`: `"buy"` or `"sell"` (VARCHAR(4), indexed)
   - `type`: `"limit"` (VARCHAR(5))
   - `price`: Limit price in paise (Integer > 0, indexed)
   - `quantity`: Total shares (Integer > 0)
   - `status`: `"open"`, `"partially_filled"`, `"filled"`, `"cancelled"`, `"rejected"` (VARCHAR(20), indexed)
   - `filled_quantity`: Filled shares (0 <= filled_quantity <= quantity)
   - `created_at`: UTC timestamp (DateTime, indexed)

4. **`TradeDB` (`trades`)**
   - `id`: Primary Key (Integer)
   - `buy_order_id`: Foreign Key (`orders.id`)
   - `sell_order_id`: Foreign Key (`orders.id`)
   - `price`: Execution price in paise (Integer > 0)
   - `quantity`: Executed shares (Integer > 0)
   - `executed_at`: UTC timestamp (DateTime)

---

## 4. How to Run the Load Test

### Step 1: Start the Server (Terminal 1)
```bash
PYTHONPATH=. uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Step 2: Run the Traffic Test Script (Terminal 2)
```bash
./traffic_test/run_traffic_test.sh
```

#### Custom Options:
You can pass a custom URL and number of concurrent connections:
```bash
# Test orderbook endpoint with 100 concurrent connections for 25 seconds:
./traffic_test/run_traffic_test.sh http://localhost:8000/orderbook/AAPL 100

# Test orders listing endpoint with 50 concurrent connections:
./traffic_test/run_traffic_test.sh http://localhost:8000/orders 50
```
