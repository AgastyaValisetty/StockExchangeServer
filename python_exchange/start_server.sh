#!/usr/bin/env bash

# Start high-performance multi-worker exchange server
cd "$(dirname "$0")"

WORKERS="${1:-32}"

echo "=========================================================="
echo " Starting Stock Exchange Server"
echo " Host     : 0.0.0.0:8000"
echo " Workers  : ${WORKERS} (Multiprocess GIL bypass)"
echo " Loop     : uvloop (C-based libuv)"
echo " Parser   : httptools (C-based HTTP parser)"
echo "=========================================================="

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
