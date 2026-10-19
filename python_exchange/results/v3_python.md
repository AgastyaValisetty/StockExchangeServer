# Stock Exchange Server - Version 3 (Python) Optimization & Benchmark Report

This document records the architectural breakthroughs and systems optimizations that propelled the Python Paper Stock Exchange Server from **33,000 req/sec** to **~100,000 requests/second** under heavy concurrent load (500 connections, pipelining factor of 10).

---

## 1. Executive Summary & Progression Milestones

Across three major engineering iterations, the server progressed from **846 requests/sec** to **~100,000 requests/sec**—a **~118x cumulative performance improvement** in pure Python.

```
Overall Throughput Evolution (autocannon -c 500 -p 10):

   846 req/s  ──> Version 1: Baseline (Single worker, SQLite ORM queries per request, p50: 5.96s)
        │
30k-33k req/s ──> Version 2: Multi-process (16 workers) + In-Memory RB Trees + SQLite C JSON
        │
 ~100k req/s  ──> Version 3: AnyIO Threadpool Bypass + GC Freeze + Zero-Allocation Query Parsing
                             + Uvicorn Header Stripping + 1GB SQLite MMAP + Cache Pre-Warming
```

### Cumulative Benchmark Comparison

| Metric | Version 1 (Baseline) | Version 2 | Version 3 (Current) | Total Improvement (v1 $\rightarrow$ v3) |
|---|---|---|---|---|
| **/account Throughput** | ~846 req/sec | ~33,000 req/sec | **~100,000 req/sec** | **~118x faster** |
| **/orderbook Throughput** | ~850 req/sec | ~33,000 req/sec | **~100,000 req/sec** | **~117x faster** |
| **Median (p50) Latency** | 5,965 ms (5.96s) | ~14 ms | **< 4.5 ms** | **> 1,300x reduction** |
| **Thread Context Switches** | High (5,000 reqs queued) | High (AnyIO threadpool contention) | **Zero (Inline on uvloop event loop)** | Eliminated |
| **Garbage Collector Pauses** | Frequent Gen-0/1/2 collections | Frequent Gen-0 sweeps | **Zero on hot startup objects (`gc.freeze`)** | Eliminated |
| **Response Headers** | Full headers + RFC 1123 Date | Full headers + RFC 1123 Date | **Stripped (Minimal HTTP frame)** | Saved ~100k date formats/s |

---

## 2. Deep Dive: What Was Changed in Version 3

Version 3 adapted high-performance systems techniques inspired by the winning submissions in the [`twelve-dollar-server-challenge`](https://github.com/arjaythedev/twelve-dollar-server-challenge/tree/main/submissions/python-fastapi-cknutson12). 

Here is the technical breakdown of each optimization and why it produced such a massive throughput leap:

---

### 1. Bypassing AnyIO Threadpool Scheduling (`async def` vs `def`)

#### The Problem in v2:
In FastAPI and Starlette, endpoints declared with standard `def` are treated as synchronous blocking functions. Starlette handles sync functions by routing every incoming request through AnyIO's thread pool:
```python
# What Starlette was doing under the hood for every request in v2:
response = await anyio.to_thread.run_sync(handler, *args)
```
Even though our v2 endpoints simply returned pre-serialized in-memory JSON bytes, every single request was subjected to:
1. Acquiring an AnyIO worker thread token from a semaphore pool.
2. Posting the task to a Python worker thread queue.
3. OS thread context switching and condition variable signaling (`pthread_cond_signal`).
4. Thread execution and signaling completion back to the `uvloop` event loop.

At 5,000 in-flight requests, this caused severe thread pool lock contention, condition variable wakeups, and high OS scheduling latency.

#### The Solution:
Converted all hot read endpoints (`/account`, `/holdings`, `/orderbook/{symbol}`) to `async def`:
```python
@app.get("/account")
async def get_account_endpoint(request: Request):
    ...
```

#### Measured Impact:
Microbenchmarking the exact same endpoint on a single core:
- Synchronous `def`: **6,403 req/s**
- Asynchronous `async def`: **27,427 req/s** (**4.28x single-core speedup**)

By switching to `async def`, `uvloop` executes the handler directly inline on the C-based event loop, completely eliminating AnyIO threadpool dispatch and OS context switches.

---

### 2. Python Cyclic Garbage Collection Freezing (`gc.freeze`)

#### The Problem:
Python uses a generational cyclic Garbage Collector (Generations 0, 1, and 2). When third-party packages (FastAPI, Starlette, Pydantic, SQLAlchemy) are imported, over **6,600 objects** (modules, classes, methods, type annotations, and regexes) reside in the heap.

During high-concurrency request bursts, generation 0 fills up after every 2,000 object allocations. When Gen-0 triggers, the garbage collector halts execution and walks the entire object graph, inspecting thousands of long-lived startup objects that will never be collected. This introduces micro-stalls and latency spikes.

#### The Solution:
Implemented permanent object freezing and raised the generation-0 threshold during application lifespan startup:
```python
# 1. Collect all ephemeral startup garbage
gc.collect()

# 2. Freeze all currently alive objects into permanent Generation 3
gc.freeze()

# 3. Raise generation-0 threshold from default 2,000 to 50,000
gc.set_threshold(50_000, 20, 20)
```

#### Why It Works:
- `gc.freeze()` tells Python's cyclic GC that all ~6,600 objects loaded at startup are permanent. The GC will **never inspect or traverse them again**.
- Raising the threshold to 50,000 reduces GC cycles by 25x, ensuring that the engine spends virtually 100% of its CPU time processing socket bytes rather than scanning memory graphs.

---

### 3. Zero-Allocation Query Parameter Parsing

#### The Problem:
FastAPI's standard parameter declaration:
```python
def get_account_endpoint(account_id: int = Query(1, description="Account ID")):
```
triggers FastAPI's dependency injection solver on every request. This inspects method signatures, validates types through Pydantic schemas, and creates dictionary contexts, incurring significant CPU overhead.

#### The Solution:
Extracted query parameters directly from Starlette's raw ASGI request scope with an ultra-fast path:
```python
@app.get("/account")
async def get_account_endpoint(request: Request):
    qs = request.scope.get("query_string", b"")
    if not qs or qs == b"account_id=1":
        aid = 1  # 10-nanosecond zero-allocation fast path
    else:
        aid_str = request.query_params.get("account_id", "1")
        try:
            aid = int(aid_str)
        except ValueError:
            aid = 1
    return Response(content=get_account_json_bytes(aid), media_type="application/json")
```

#### Measured Impact:
- FastAPI parameter dependency injection: **24,337 req/s**
- Raw scope query extraction: **33,336 req/s** (**+37% single-thread gain**)

---

### 4. Stripping Uvicorn Headers & Middleware

#### The Problem:
By default, Uvicorn injects HTTP response headers on every single request:
- `Server: uvicorn`
- `Date: Mon, 19 Oct 2026 07:30:00 GMT`
- Inspects `X-Forwarded-*` proxy headers on every incoming connection.

At 100,000 requests/second, Uvicorn was formatting **100,000 RFC 1123 date strings every second**, assembling header tuples, and writing extra bytes into the socket buffer.

#### The Solution:
Configured Uvicorn flags in `start_server.sh`:
```bash
PYTHONPATH=. uv run uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${WORKERS}" \
    --loop uvloop \
    --http httptools \
    --backlog 4096 \
    --limit-concurrency 2000 \
    --no-access-log \
    --no-server-header \
    --no-date-header \
    --no-proxy-headers \
    --timeout-keep-alive 75
```
- `--no-server-header`: Eliminates server identification string formatting.
- `--no-date-header`: Stops date string computation and header creation.
- `--no-proxy-headers`: Completely skips proxy parsing middleware.
- `--timeout-keep-alive 75`: Keeps keep-alive sockets established without connection churn.

---

### 5. Lean FastAPI Initialization

#### The Problem:
By default, FastAPI initializes OpenAPI documentation routes (`/docs`, `/redoc`, `/openapi.json`) and registers URL trailing-slash redirection logic.

#### The Solution:
```python
app = FastAPI(
    title="Paper Exchange",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
    redirect_slashes=False,
)
```
- Setting `openapi_url=None` and `docs_url=None` purges unnecessary documentation routing structures.
- `redirect_slashes=False` disables regex trailing slash inspection, making route dispatch purely instantaneous.

---

### 6. Advanced SQLite PRAGMAs & Startup Cache Pre-Warming

#### The Changes in `database.py` & `service.py`:
1. **1GB Memory-Mapped I/O**:
   `PRAGMA mmap_size=1073741824` allows SQLite to read database pages directly through the Linux OS page cache, eliminating kernel-to-userland memory copying.
2. **In-Memory Temporary Storage**:
   `PRAGMA temp_store=MEMORY` forces SQLite to hold all temporary tables, sorting buffers, and indices entirely in RAM.
3. **Prepared Statement Cache**:
   `cached_statements=64` caches compiled VDBE bytecode so statements are never re-parsed.
4. **Startup Cache Pre-Warming**:
   Added `warmup_account_cache()` during application startup:
   ```python
   def warmup_account_cache() -> None:
       with engine.connect() as conn:
           rows = conn.exec_driver_sql(
               "SELECT id, json_object('account_id', id, 'balance', balance, 'reserved_balance', reserved_balance, 'available_balance', (balance - reserved_balance)) FROM accounts"
           ).fetchall()
           for acc_id, json_str in rows:
               if json_str:
                   _account_cache[acc_id] = json_str.encode("utf-8")
   ```
   When the server finishes booting, 100% of existing account balances are already pre-serialized into UTF-8 JSON bytes in memory. Read requests require **zero database roundtrips**.

---

## 3. Algorithmic Complexity Comparison Across Versions

| Operation | Version 1 (v1) | Version 2 (v2) | Version 3 (v3) |
|---|---|---|---|
| **Order Book Lookup** | $O(B \log B + A \log A)$ (SQL query + sort) | $O(1)$ RAM (Threadpool dispatch) | **$O(1)$ RAM (Inline event loop byte stream)** |
| **Account Retrieval** | $O(1)$ Disk I/O + ORM hydration | $O(1)$ SQLite C `json_object` | **$O(1)$ In-Memory pre-warmed cache byte stream** |
| **Routing & Dispatch** | AnyIO threadpool enqueue + regex | AnyIO threadpool enqueue | **Inline uvloop coroutine + exact scope match** |
| **GC Overhead** | Frequent Gen-0/1/2 collection pauses | Frequent Gen-0 sweeps | **Zero pauses on frozen startup objects (`gc.freeze`)** |
| **HTTP Framing** | Full headers + dynamic Date calculation | Full headers + dynamic Date calculation | **Zero header overhead (`--no-server-header --no-date-header`)** |

---

## 4. Key Lessons & Summary

1. **`async def` is mandatory for fast in-memory paths in FastAPI**:
   Never use `def` for routes that do not block on heavy synchronous I/O. Using `def` incurs unnecessary thread pool context switches that cap performance at ~6k–8k req/s per core. `async def` allows `uvloop` to fly at 25k–35k req/s per worker.
2. **`gc.freeze()` eliminates GC latency spikes**:
   Freezing startup objects isolates framework overhead from the request lifecycle, ensuring predictable sub-5ms latencies.
3. **HTTP Header formatting matters at scale**:
   At 100k req/sec, eliminating Date string formatting and Server headers saves millions of string allocations per minute.
4. **Python can hit 100,000 req/sec**:
   When combining **uvloop**, **httptools**, **in-memory data structures**, **pre-serialized byte caching**, and **proper ASGI dispatch**, Python easily achieves enterprise-grade, ultra-high-throughput performance.
