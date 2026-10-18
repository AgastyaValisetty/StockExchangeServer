# Stock Exchange Server - Version 1 (Python) Architecture & Benchmark Report

This document details the complete design, implementation, algorithmic complexity, load testing results, and architectural bottlenecks of **Version 1 (Python Exchange)**.

---

## 1. System Overview & What We Built in v1

Version 1 is an end-to-end Paper Stock Exchange Server built using:
- **Framework & Runtime**: Python 3, FastAPI, Uvicorn (ASGI server)
- **Database & ORM**: SQLite (`data/exchange.db`), SQLAlchemy 2.0
- **Validation**: Pydantic v2
- **Testing**: Pytest (34 passing test cases)

### Core Architectural Features:
1. **Integer Arithmetic Accounting**: All monetary values are strictly tracked in integer paise to eliminate floating-point precision drift.
2. **Dual-Side Financial Reservations**:
   - **Buy Orders**: Cash reserved upfront (`price × quantity`).
   - **Sell Orders**: Shares reserved upfront (`quantity`).
   - Prevents double-spending, overdrafts, and phantom short sales.
3. **Deterministic Price-Time Priority Matching Engine**:
   - Match condition: $\text{buy\_price} \ge \text{sell\_price}$.
   - Priority: Best price first (highest bids, lowest asks), then oldest order first (FIFO by `created_at`).
   - Maker-Taker Execution Pricing: Resting orders determine the trade execution price.
   - Automatic Price Improvement: When a buyer's limit order matches against a lower-priced resting ask, excess reserved cash is instantly released back to available balance.
4. **Self-Trade Prevention (STP)**: Orders submitted by the same account are prevented from matching against each other.
5. **Partial Fills & Order Book State**: Orders transition cleanly through `open` $\rightarrow$ `partially_filled` $\rightarrow$ `filled`, and unused reservations on cancelled orders (`DELETE /orders/{id}`) are refunded atomically.
6. **Full REST API Suite (9 Endpoints)**:
   - `POST /orders` (Submit limit order with validation, reservation, and matching)
   - `GET /orders` (List orders with optional symbol & status filters)
   - `GET /orders/{id}` (Get order details and fill status)
   - `DELETE /orders/{id}` (Cancel order & release remaining reservation)
   - `GET /account` (Cash balance, reserved balance, available balance)
   - `GET /holdings` (Shares owned, reserved shares, available shares)
   - `GET /trades` (Executed trade history)
   - `GET /orderbook/{symbol}` (Active bid and ask books)
   - `GET /portfolio` (Total portfolio net worth and unrealized P&L)

---

## 2. Load Test Results (Autocannon Benchmark)

The server was load-tested using `autocannon` targeting the account state endpoint under heavy concurrent pressure.

### Test Configuration:
- **Target URL**: `http://localhost:8000/account`
- **Concurrent Connections**: 500
- **Duration**: 60 seconds
- **Pipelining Factor**: 10 (up to 5,000 requests in flight across all connections)

### Benchmark Output:

#### Latency
| Stat | 2.5% | 50% (Median) | 97.5% | 99% | Avg | Stdev | Max |
|---|---|---|---|---|---|---|---|
| **Latency** | 1,819 ms | 5,965 ms | 6,723 ms | 6,783 ms | **5,606.1 ms** | 1,174.92 ms | 9,381 ms |

#### Throughput (Requests / Second)
| Stat | 1% | 2.5% | 50% (Median) | 97.5% | Avg | Stdev | Min |
|---|---|---|---|---|---|---|---|
| **Req/Sec** | 638 | 672 | 780 | 1,398 | **846.55** | 164.26 | 638 |

#### Data Transfer Rate
| Stat | 1% | 2.5% | 50% (Median) | 97.5% | Avg | Stdev | Min |
|---|---|---|---|---|---|---|---|
| **Bytes/Sec** | 135 kB | 142 kB | 165 kB | 295 kB | **179 kB** | 34.7 kB | 135 kB |

---

## 3. Algorithmic Time & Space Complexity

| Operation | Time Complexity | Space Complexity | Explanation |
|---|---|---|---|
| **Cash / Share Validation** | $O(1)$ | $O(1)$ | Primary key lookup on `accounts` or indexed `(account_id, symbol)` on `account_holdings`. |
| **Order Insert & Persist** | $O(\log N)$ | $O(1)$ | $B$-tree index insertion for primary key, `symbol`, `side`, `status`, `price`, and `created_at`. |
| **Matching Order Search** | $O(K \log N)$ | $O(K)$ | Database index scan retrieving $K$ candidate resting orders for that symbol/side sorted by price-time. |
| **Order Matching Loop** | $O(M)$ | $O(M)$ | Iterating over $M$ matched counter-orders to produce trades (typically $M \le 5$). |
| **Trade Execution & Settlement** | $O(1)$ per trade | $O(1)$ | In-place update of order filled quantities, buyer/seller balance, and buyer/seller holdings. |
| **Total Order Placement** | $\mathcal{O}(K \log N + M)$ | $\mathcal{O}(K + M)$ | Total end-to-end execution of `POST /orders`. |
| **Order Cancellation** | $O(1)$ | $O(1)$ | Primary key fetch, remaining reservation release, and status flag update. |
| **Order Book Retrieval** | $O(B \log B + A \log A)$ | $O(B + A)$ | Fetching and sorting active bids ($B$) and asks ($A$) for the requested symbol. |
| **Portfolio Valuation & P&L** | $O(H \times T_h)$ | $O(H)$ | Scanning $H$ holdings and summing cost basis across $T_h$ historical buy trades. |

---

## 4. Deep-Dive: Bottlenecks in v1 (Why Latency Spiked to ~5.6s)

While **~846.55 requests/sec** is a solid baseline for a Python/FastAPI/SQLite stack with full database roundtrips, the high average latency (5,606 ms) under 500 connections highlights specific architectural bottlenecks:

### 1. Connection Queuing Delay (Little's Law)
* **The Math**: The benchmark used 500 connections with a pipelining factor of 10, creating a queue of up to **5,000 requests in flight**.
* At a processing rate of **846 requests/second**:
  $$\text{Expected Queue Waiting Time} \approx \frac{5,000 \text{ requests}}{846.55 \text{ req/sec}} \approx 5.9 \text{ seconds}$$
* **Finding**: The server was not crashing or dropping connections; requests simply sat in the socket backlog waiting for the single Python worker to process earlier requests in the FIFO queue.

### 2. Python GIL & Single-Process Sync Bottleneck
* Python's **Global Interpreter Lock (GIL)** restricts execution to one native thread at a time per process.
* FastAPI route handlers in v1 were defined with synchronous `def` (`def get_account_endpoint`), causing FastAPI to run each request inside an `anyio` threadpool worker, contending on the GIL during JSON serialization and ORM object hydration.

### 3. SQLite Concurrency & File-Level Locking
* SQLite is an embedded file-based database. Although WAL (Write-Ahead Logging) mode permits multiple readers, SQLite enforces a **single writer lock**.
* Under concurrent order submission, writes serialize on SQLite's lock table. Even read queries incur file system and OS cache overhead compared to pure in-memory memory structures.

### 4. SQLAlchemy ORM Overhead
* On every request, SQLAlchemy creates session contexts, reflects schema columns, validates types, and instantiates Python model instances (`AccountDB`).
* Object allocation and garbage collection in Python introduce significant microsecond overhead compared to static structs.

### 5. Relational Querying vs. In-Memory Order Book
* Storing the active order book in relational SQL tables (`orders` table filtered by `status="open"`) requires SQL query parsing, index traversal, and row materialization.
* In high-performance trading engines, the order book resides **100% in RAM** using cache-friendly structures (e.g. Radix Trees, B-Trees, or Arrays of doubly linked lists).

---

## 5. Architectural Recommendations for Next Versions (v2+)

When building the exchange in compiled, systems-level languages (e.g., **Go**, **Rust**, or **C++**):

| Bottleneck in v1 (Python) | High-Performance Solution for v2+ |
|---|---|
| **Python GIL** | True native multi-threading or single-threaded pinned core event loop with zero lock contention. |
| **SQLite File Locks** | Pure in-memory order book state + asynchronous Write-Ahead Logging (WAL) or snapshotting. |
| **SQL Index Scans for Matching** | **Price-Level Radix Tree / Red-Black Tree** with intrusive doubly linked lists for $O(1)$ FIFO time priority. |
| **Object Allocation & GC** | Object pooling and pre-allocated arrays to achieve **zero-allocation** hot paths. |
| **Throughput Target** | From ~850 req/sec (Python SQLite) $\longrightarrow$ **50,000 to 500,000+ req/sec** (Go / Rust / C++). |
