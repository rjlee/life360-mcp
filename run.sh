#!/bin/bash
# Life360 MCP Server - Development script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check for .env file
if [ ! -f .env ]; then
    log_warn ".env file not found. Copying from .env.example..."
    if [ -f .env.example ]; then
        cp .env.example .env
        log_info "Created .env file. Please edit it with your credentials."
        exit 0
    else
        log_error ".env.example not found either."
        exit 1
    fi
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    log_info "Creating virtual environment..."
    python3 -m venv venv
fi

# Install dependencies
log_info "Installing dependencies..."
./venv/bin/pip install -q requests python-dotenv certifi aiohttp pycurl

# Check if we should run or just install
MODE="${1:-http}"
PORT="${2:-8123}"

if [ "$MODE" = "--install-only" ] || [ "$MODE" = "-i" ]; then
    log_info "Dependencies installed. Run './run.sh --http' to start the server."
    exit 0
fi

# Run the server
log_info "Starting Life360 MCP server on http://127.0.0.1:$PORT"
log_info "Press Ctrl+C to stop"

./venv/bin/python cli.py --http &
SERVER_PID=$!

# Wait a moment for server to start
sleep 1

# Send a test request
log_info "Sending test request..."
curl -s -X POST "http://127.0.0.1:$PORT" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc": "2.0", "method": "list_circles", "id": 1}' | python3 -m json.tool 2>/dev/null || \
curl -s -X POST "http://127.0.0.1:$PORT" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc": "2.0", "method": "list_circles", "id": 1}'

echo ""
log_info "Server running on http://127.0.0.1:$PORT"
log_info "Test endpoints:"
echo "  curl -X POST http://127.0.0.1:$PORT -H 'Content-Type: application/json' -d '{\"jsonrpc\": \"2.0\", \"method\": \"list_circles\", \"id\": 1}'"
echo "  curl -X POST http://127.0.0.1:$PORT -H 'Content-Type: application/json' -d '{\"jsonrpc\": \"2.0\", \"method\": \"get_location\", \"params\": [\"MemberName\"], \"id\": 1}'"

# Wait for Ctrl+C
trap "log_info 'Stopping server...'; kill $SERVER_PID 2>/dev/null; exit 0" INT TERM
wait $SERVER_PID