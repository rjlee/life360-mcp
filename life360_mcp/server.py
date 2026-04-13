import os
import json
import time
import logging
import io
from pathlib import Path
from typing import Any, Callable

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(dotenv_path=".env"):
        p = Path(dotenv_path)
        if p.is_file():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

try:
    import pycurl
except ImportError:
    import sys
    print("Error: pycurl not installed. Run: pip install pycurl", file=sys.stderr)
    sys.exit(1)

load_dotenv()

DEFAULT_CACHE_TTL = int(os.getenv("LIFE360_CACHE_TTL", "30"))
MAX_RETRIES = int(os.getenv("LIFE360_MAX_RETRIES", "5"))
TOKEN_PATH = Path.home() / ".life360" / "token.json"
TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=os.getenv("LIFE360_LOG_LEVEL", "INFO"))
logger = logging.getLogger("life360_mcp")


class Life360Client:
    """A client for the Life360 API with robust token handling, rate‑limit back‑off, caching, and defensive parsing.

    Supports two authentication methods:
    1. Username/password - OAuth login with LIFE360_USERNAME/PASSWORD
    2. Authorization token - Pre-existing token via LIFE360_AUTHORIZATION

    Environment variables:
        LIFE360_USERNAME, LIFE360_PASSWORD, LIFE360_CLIENT_ID – credentials.
        LIFE360_AUTHORIZATION, LIFE360_TOKEN_TYPE – token auth (alternative to username/password).
        LIFE360_CACHE_TTL – seconds to cache location results (default 30).
        LIFE360_MAX_RETRIES – max retries on 429/5xx responses (default 5).
        LIFE360_HTTP_HOST, LIFE360_HTTP_PORT – HTTP server bind settings.
    """

    def __init__(self) -> None:
        self.username = os.getenv("LIFE360_USERNAME", "")
        self.password = os.getenv("LIFE360_PASSWORD", "")
        self.client_id = os.getenv("LIFE360_CLIENT_ID", "life360_mobile_app")
        self.authorization = os.getenv("LIFE360_AUTHORIZATION", "")
        self.token_type = os.getenv("LIFE360_TOKEN_TYPE", "Bearer")
        self._client_token = "Y2F0aGFwYWNyQVBoZUtVc3RlOGV2ZXZldnVjSGFmZVRydVl1ZnJhYzpkOEM5ZVlVdkE2dUZ1YnJ1SmVnZXRyZVZ1dFJlQ1JVWQ=="
        self.headers = {
            "User-Agent": "com.life360.android.safetymapd/KOKO/23.50.0 android/13",
            "Accept": "application/json",
            "cache-control": "no-cache",
        }
        self._circle_cache = None
        self._member_cache = None
        self._location_cache = {}
        
        self._load_token()
        
        # Set authorization header - use the exact stored value (like HA does)
        if self.authorization:
            # If it's already prefixed, use as-is. Otherwise add the token_type prefix.
            if self.authorization.startswith(self.token_type + " "):
                self.headers["Authorization"] = self.authorization
            else:
                self.headers["Authorization"] = f"{self.token_type} {self.authorization}"

    def _load_token(self) -> None:
        """Load a saved token from disk (if it exists) and set the Authorization header."""
        if TOKEN_PATH.is_file():
            try:
                data = json.loads(TOKEN_PATH.read_text())
                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token")
                self.expires_at = data.get("expires_at", 0)
                stored_auth = data.get("authorization")
                stored_token_type = data.get("token_type", "Bearer")
                if stored_auth:
                    self.authorization = stored_auth
                    self.token_type = stored_token_type
                    self.headers["Authorization"] = f"{self.token_type} {self.authorization}"
                elif self.access_token:
                    self.headers["Authorization"] = f"Bearer {self.access_token}"
                logger.debug("Loaded Life360 token from %s", TOKEN_PATH)
            except Exception as exc:
                logger.warning("Failed to read Life360 token file: %s", exc)
        else:
            self.access_token = None
            self.refresh_token = None
            self.expires_at = 0

    def _save_token(self, data) -> None:
        """Persist a token to disk with mode 0600."""
        try:
            TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_PATH.write_text(json.dumps(data))
            os.chmod(TOKEN_PATH, 0o600)
            logger.debug("Saved Life360 token to %s with 0600 permissions", TOKEN_PATH)
        except Exception as exc:
            logger.error("Unable to write Life360 token file: %s", exc)

    def _login(self) -> None:
        """Perform OAuth login flow or use pre-existing authorization token."""
        if self.authorization:
            logger.info("Using pre-existing Life360 authorization token")
            self.headers["Authorization"] = f"{self.token_type} {self.authorization}"
            self._save_token({"authorization": self.authorization, "token_type": self.token_type})
            return
        
        if not all([self.username, self.password, self.client_id]):
            logger.warning("Life360 credentials missing")
        
        payload = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
            "client_id": self.client_id,
        }
        logger.info("Logging in to Life360 API")
        auth_header = f"Basic {self._client_token}"
        resp = requests.post(
            "https://api-cloudfront.life360.com/v3/oauth2/token",
            data=payload,
            headers={"Authorization": auth_header, "Accept": "application/json"},
            timeout=15,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Life360 login failed (status {resp.status_code}): {resp.text}")
        data = resp.json()
        self.access_token = data.get("access_token")
        self.refresh_token = data.get("refresh_token")
        self.expires_at = int(time.time()) + int(data.get("expires_in", 0))
        self.headers["Authorization"] = f"Bearer {self.access_token}"
        self._save_token({
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
        })

    def _ensure_token(self) -> None:
        """Ensure we have a valid token (either OAuth access token or authorization token)."""
        has_oauth_token = self.access_token and (self.expires_at - int(time.time())) >= 60
        has_auth_token = bool(self.authorization)
        
        if not has_oauth_token and not has_auth_token:
            logger.info("Life360 token expired or missing – refreshing")
            self._login()

    def _request(self, method, url, **kwargs):
        self._ensure_token()
        attempt = 0
        while True:
            attempt += 1
            try:
                # Use pycurl for HTTP requests (like curl, which works)
                buffer = io.BytesIO()
                c = pycurl.Curl()
                c.setopt(c.URL, url)
                c.setopt(c.WRITEFUNCTION, buffer.write)
                c.setopt(c.TIMEOUT, 15)
                c.setopt(c.HTTPHEADER, [
                    f"Authorization: {self.headers.get('Authorization', '')}",
                    f"User-Agent: {self.headers.get('User-Agent', '')}",
                    f"Accept: {self.headers.get('Accept', 'application/json')}",
                ])
                if method.upper() != "GET":
                    c.setopt(c.CUSTOMREQUEST, method.upper())
                
                c.perform()
                status_code = c.getinfo(c.RESPONSE_CODE)
                c.close()
                
                response_text = buffer.getvalue().decode('utf-8')
                
                if status_code == 401:
                    logger.warning("Life360 request returned 401 – re-authenticating")
                    self._login()
                    if attempt > 1:
                        raise RuntimeError("Authentication failed after token refresh")
                    continue
                if status_code == 429:
                    logger.warning("Life360 rate-limited – sleeping 60 seconds")
                    time.sleep(60)
                    if attempt >= MAX_RETRIES:
                        raise RuntimeError("Exceeded maximum retries after rate limiting")
                    continue
                if status_code >= 500:
                    logger.warning("Life360 server error %s – attempt %s", status_code, attempt)
                    if attempt >= MAX_RETRIES:
                        raise RuntimeError(f"Server error {status_code} after {attempt} attempts")
                    time.sleep(2 ** attempt)
                    continue
                    
                try:
                    return json.loads(response_text)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"Invalid JSON from Life360: {exc}")
                    
            except pycurl.error as exc:
                logger.error("Network error contacting Life360: %s", exc)
                if attempt >= MAX_RETRIES:
                    raise RuntimeError(f"Network error after {attempt} attempts: {exc}")
                time.sleep(2 ** attempt)

    def _get_circles(self):
        if self._circle_cache is None:
            data = self._request("GET", "https://api-cloudfront.life360.com/v4/circles")
            self._circle_cache = data.get("circles", [])
            self._member_cache = None
        return self._circle_cache

    def _get_members(self):
        if self._member_cache is None:
            members = {}
            for circle in self._get_circles():
                cid = circle.get("id")
                if not cid:
                    continue
                data = self._request("GET", f"https://api-cloudfront.life360.com/v3/circles/{cid}/members")
                for m in data.get("members", []):
                    name = m.get("firstName") or m.get("name")
                    if name:
                        members[name.lower()] = {"circle_id": cid, "member": m}
            self._member_cache = members
        return self._member_cache

    def list_circles(self):
        return self._get_circles()

    def list_members(self, circle_id):
        data = self._request("GET", f"https://api-cloudfront.life360.com/v3/circles/{circle_id}/members")
        return data.get("members", [])

    def get_location(self, member_name):
        key = member_name.lower()
        cached = self._location_cache.get(key)
        if cached and (time.time() - cached["_fetched_at"]) < DEFAULT_CACHE_TTL:
            result = cached.copy()
            result["cached"] = True
            return result
        members = self._get_members()
        if key not in members:
            raise RuntimeError(f"Member '{member_name}' not found in any circle")
        info = members[key]
        circle_id = info["circle_id"]
        member_id = info["member"].get("id")
        if not member_id:
            raise RuntimeError("Life360 API did not return a member ID")
        payload = self._request(
            "GET",
            f"https://api-cloudfront.life360.com/v3/circles/{circle_id}/members/{member_id}",
        )
        loc = payload.get("location", {})
        raw_ts = payload.get("timestamp") or loc.get("timestamp")
        if raw_ts:
            try:
                ts_int = int(raw_ts)
                if ts_int > 1_000_000_000_000:
                    ts_int //= 1000
                timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts_int))
            except Exception:
                timestamp = None
        else:
            timestamp = None
        battery = loc.get("battery") or payload.get("batteryLevel")
        result = {
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "accuracy": loc.get("accuracy"),
            "battery": battery,
            "timestamp": timestamp,
            "cached": False,
        }
        result_copy = result.copy()
        result_copy["_fetched_at"] = time.time()
        self._location_cache[key] = result_copy
        return result

    def run_http_server(self, host: str = None, port: int = None):
        if host is None:
            host = os.getenv("LIFE360_HTTP_HOST", "127.0.0.1")
        if port is None:
            port = int(os.getenv("LIFE360_HTTP_PORT", "8123"))
        from http.server import BaseHTTPRequestHandler, HTTPServer
        client = self
        
        MCP_TOOLS = [
            {
                "name": "list_circles",
                "description": "List all Life360 circles (groups)",
                "inputSchema": {"type": "object", "properties": {}}
            },
            {
                "name": "list_members",
                "description": "List all members in a circle",
                "inputSchema": {
                    "type": "object",
                    "properties": {"circle_id": {"type": "string", "description": "Circle ID"}},
                    "required": ["circle_id"]
                }
            },
            {
                "name": "get_location",
                "description": "Get location info for a specific member",
                "inputSchema": {
                    "type": "object",
                    "properties": {"member": {"type": "string", "description": "Member name"}},
                    "required": ["member"]
                }
            }
        ]
        
        class Handler(BaseHTTPRequestHandler):
            def _send(self, payload: Any, code: int = 200):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode()
                req_id = None
                logger.info("Incoming request: %s", body)
                try:
                    req = json.loads(body)
                    req_id = req.get("id")
                    method = req.get("method")
                    params = req.get("params") or {}
                    logger.info("RPC method=%s params=%s id=%s", method, params, req_id)
                    
                    if method == "initialize":
                        result = {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "life360-mcp", "version": "1.0.0"}
                        }
                    elif method == "tools/list":
                        result = {"tools": MCP_TOOLS}
                    elif method == "tools/call":
                        tool_name = params.get("name")
                        tool_args = params.get("arguments", {})
                        if tool_name == "list_circles":
                            result = {"content": [{"type": "text", "text": json.dumps(client.list_circles())}]}
                        elif tool_name == "list_members":
                            circle_id = tool_args.get("circle_id")
                            result = {"content": [{"type": "text", "text": json.dumps(client.list_members(circle_id))}]}
                        elif tool_name == "get_location":
                            member = tool_args.get("member")
                            result = {"content": [{"type": "text", "text": json.dumps(client.get_location(member))}]}
                        else:
                            raise ValueError(f"Unknown tool: {tool_name}")
                    elif method == "ping":
                        result = {}
                    elif method.startswith("notifications/"):
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(b"{}")
                        return
                    else:
                        raise ValueError(f"Unsupported method {method}")
                    self._send({"jsonrpc": "2.0", "result": result, "id": req.get("id")})
                except Exception as exc:
                    logger.exception("Error handling RPC: %s", exc)
                    self._send({"jsonrpc": "2.0", "error": {"code": -32603, "message": str(exc)}, "id": req_id}, code=500)
            def do_GET(self):
                self._send({"jsonrpc": "2.0", "error": {"code": -32603, "message": "Use POST for MCP calls"}}, code=501)
        server = HTTPServer((host, port), Handler)
        logger.info("Life360 MCP HTTP server listening on %s:%s", host, port)
        server.serve_forever()


_client_instance = Life360Client()
_LOCATION_CACHE = _client_instance._location_cache


def _load_token():
    _client_instance._load_token()
    class _Token:
        pass
    token = _Token()
    token.access_token = getattr(_client_instance, "access_token", None)
    return token

def _login():
    _client_instance._login()
    class _Token:
        pass
    token = _Token()
    token.access_token = getattr(_client_instance, "access_token", None)
    return token

def list_circles():
    _client_instance._circle_cache = None
    return _client_instance.list_circles()

def list_members(circle_id):
    return _client_instance.list_members(circle_id)

def get_location(member_name):
    return _client_instance.get_location(member_name)

def _read_stdin() -> str:
    import sys
    return sys.stdin.read()

def _write_stdout(message: str) -> None:
    import sys
    sys.stdout.write(message)
    sys.stdout.flush()

def _handle_rpc(request) -> dict:
    method = request.get("method")
    params = request.get("params")
    try:
        if method == "list_circles":
            result = list_circles()
        elif method == "list_members":
            if isinstance(params, list) and params:
                circle_id = params[0]
            elif isinstance(params, dict):
                circle_id = params.get("circle_id")
            else:
                raise ValueError("Missing circle_id for list_members")
            result = list_members(circle_id)
        elif method == "get_location":
            if isinstance(params, list) and params:
                member = params[0]
            elif isinstance(params, dict):
                member = params.get("member")
            else:
                member = params
            result = get_location(member)
        else:
            raise ValueError(f"Method {method} not supported")
        return {"jsonrpc": "2.0", "result": result, "id": request.get("id")}
    except Exception as exc:
        logger.exception("Error handling RPC method %s", method)
        return {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(exc)}, "id": request.get("id")}

def main() -> None:
    raw = _read_stdin()
    if not raw.strip():
        return
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        _write_stdout(json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": f"Parse error: {exc}"}, "id": None}))
        return
    response = _handle_rpc(request)
    _write_stdout(json.dumps(response))

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        # Clear any cached import to avoid the warning
        if 'life360_mcp' in sys.modules:
            del sys.modules['life360_mcp']
        if 'life360_mcp.server' in sys.modules:
            del sys.modules['life360_mcp.server']
        _client_instance.run_http_server()
    else:
        main()