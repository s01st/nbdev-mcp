#!/usr/bin/env python3
"""Compatibility wrapper for legacy script-based MCP launchers.

This path is kept so existing MCP client configs that reference
`scripts/mcp.nbdev.py` continue to work.
"""

from nbdev_mcp.mcp import main


if __name__ == "__main__":
    main()
