#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp[cli]>=1.28,<2",
#   "nbclient>=0.11,<1",
#   "nbformat>=5.10,<6",
#   "pydantic>=2.12,<3",
# ]
# ///
"""Run the local notebook-tools MCP server over STDIO.

The server deliberately requires explicit filesystem roots:

    uv run --script notebook_mcp.py --root /absolute/project
"""

from __future__ import annotations

import argparse

from notebook_tools.server import create_server


__version__ = "0.2.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cell-aware Jupyter notebook tools for Codex over STDIO MCP."
    )
    parser.add_argument(
        "--root",
        action="append",
        required=True,
        help="Absolute allowed filesystem root; repeat for more than one root.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    create_server(args.root).run(transport="stdio")


if __name__ == "__main__":
    main()
