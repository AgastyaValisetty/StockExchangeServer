#!/usr/bin/env bash

# Stock Exchange Server - Traffic Load Test using autocannon
# Duration: 25 seconds

TARGET_URL="${1:-http://localhost:8000/account}"
CONNECTIONS="${2:-100}"
DURATION=60

echo "=========================================================="
echo " Starting autocannon load test"
echo " Target URL   : ${TARGET_URL}"
echo " Connections  : ${CONNECTIONS}"
echo " Duration     : ${DURATION} seconds"
echo "=========================================================="

# Check if autocannon is available directly or via npx
if command -v autocannon &> /dev/null; then
    CMD="autocannon"
elif command -v npx &> /dev/null; then
    CMD="npx autocannon"
else
    echo "Error: Neither 'autocannon' nor 'npx' was found."
    echo "Please install Node.js/npm or install autocannon globally:"
    echo "  npm install -g autocannon"
    exit 1
fi

# Verify server is reachable before hammering it
echo "Checking connection to ${TARGET_URL}..."
if ! curl -s -f -o /dev/null --max-time 3 "${TARGET_URL}"; then
    echo "Warning: Could not reach ${TARGET_URL}."
    echo "Ensure your FastAPI server is running with:"
    echo "  uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"
    echo ""
    read -p "Do you still want to proceed? (y/N): " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Running benchmark for ${DURATION}s..."
${CMD} -c "${CONNECTIONS}" -d "${DURATION}" -p 10 "${TARGET_URL}"
