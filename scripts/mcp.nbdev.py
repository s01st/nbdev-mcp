#!/usr/bin/env python3
"""Compatibility wrapper for the nbdev_mcp CLI.

All maintained MCP server logic lives in `nbs/` and is exported to
`nbdev_mcp.mcp`. This script is kept as a thin legacy entrypoint.
"""

from nbdev_mcp.mcp import main


if __name__ == "__main__":
    main()
