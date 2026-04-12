#!/usr/bin/env python3
"""CLI entry point for Life360 MCP server.

Usage:
    python cli.py              # stdio mode
    python cli.py --http     # HTTP mode
"""
import sys
import os

# Ensure we import from this package, not the parent
if __name__ == "__main__":
    # Import after path is set
    from life360_mcp import server
    
    if len(sys.argv) > 1 and sys.argv[1] == "--http":
        client = server.Life360Client()
        client.run_http_server()
    else:
        server.main()