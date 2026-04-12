"""Life360 MCP Server - Command-line entry point."""
import sys
import os
import json

# Add parent dir to path so we can import life360_mcp
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from life360_mcp import server

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        client = server.Life360Client()
        client.run_http_server()
    else:
        server.main()