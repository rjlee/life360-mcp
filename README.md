# Life360 MCP Server

> This implementation is based on the [ha-life360](https://github.com/pnbruckner/life360) Home Assistant integration. It uses the same API endpoints, authentication methods, and request patterns.

This repository provides a **minimal MCP (JSON‑RPC) server** that exposes the Life360 location‑tracking API to the Hermes agent. It mirrors the behaviour of the Home Assistant `ha-life360` integration but is deliberately lightweight so that it can run inside the same Docker image as the Hermes stack.

## Features

* **Authentication** – two methods supported (see Authentication section below)
* **Rate‑limit handling** – respects the `Retry‑After` header on HTTP 429 responses
* **Caching** – recent location look‑ups are cached for a configurable TTL (`LIFE360_CACHE_TTL`, default 30s)
* **MCP methods** – `list_circles()`, `list_members(circle_id)`, and `get_location(member_name)`
* **Transport** – runs by default over **stdin/stdout** (compatible with MCP clients). An optional HTTP server can be started with `--http`

## Quick Start

### Using Docker

```bash
# Build the image
docker build -t life360-mcp .

# Run with environment variables
docker run -d \
  -e LIFE360_AUTHORIZATION=your_token_here \
  -p 8123:8123 \
  life360-mcp

# Or use a .env file
docker run -d \
  --env-file .env \
  -p 8123:8123 \
  life360-mcp
```

### Manual Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure .env
cp .env.example .env
# Edit .env with your credentials

# Run the server
python cli.py --http
```

The server will listen on `http://127.0.0.1:8123` (or `http://localhost:8123`).

## Authentication

Two authentication methods are supported:

### Method 1: Username & Password (OAuth)

```bash
LIFE360_USERNAME=your_email@example.com
LIFE360_PASSWORD=your_password
LIFE360_CLIENT_ID=life360_mobile_app   # optional
```

### Method 2: Authorization Token

Get this from the Life360 app: **Settings → Account → Authorization Token**

```bash
LIFE360_AUTHORIZATION=your_token_here
LIFE360_TOKEN_TYPE=Bearer   # optional, defaults to Bearer
```

## API Endpoints

Once the server is running, you can use the HTTP API:

```bash
# List all circles
curl -X POST http://127.0.0.1:8123 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "list_circles", "id": 1}'

# List members in a circle
curl -X POST http://127.0.0.1:8123 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "list_members", "params": ["circle_id"], "id": 2}'

# Get location for a member
curl -X POST http://127.0.0.1:8123 \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "get_location", "params": ["MemberName"], "id": 3}'
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LIFE360_USERNAME` | - | Life360 email (for OAuth login) |
| `LIFE360_PASSWORD` | - | Life360 password |
| `LIFE360_CLIENT_ID` | `life360_mobile_app` | OAuth client ID |
| `LIFE360_AUTHORIZATION` | - | Pre-existing auth token |
| `LIFE360_TOKEN_TYPE` | `Bearer` | Token type |
| `LIFE360_CACHE_TTL` | `30` | Cache TTL in seconds |
| `LIFE360_MAX_RETRIES` | `5` | Max retries for 429/5xx errors |
| `LIFE360_LOG_LEVEL` | `INFO` | Logging level |
| `LIFE360_HTTP_HOST` | `127.0.0.1` | HTTP server bind host |
| `LIFE360_HTTP_PORT` | `8123` | HTTP server port |

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run in HTTP mode for testing
python cli.py --http

# Or run in stdio mode (for MCP integration)
python cli.py
```

## Installation

```bash
pip install -r requirements.txt
```

## License

MIT License - see LICENSE file.
