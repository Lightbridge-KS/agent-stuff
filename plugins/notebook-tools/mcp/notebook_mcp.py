#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mcp[cli]>=1.28,<2",
#   "nbclient>=0.11,<1",
#   "nbformat>=5.10,<6",
#   "platformdirs>=4.3,<5",
#   "pydantic>=2.12,<3",
# ]
# ///
"""Run the packaged notebook-tools MCP server over STDIO.

Direct registration uses explicit filesystem roots:

    uv run --script notebook_mcp.py --root /absolute/project

Plugin registration requests roots from the MCP client and fails closed:

    uv run --script notebook_mcp.py --use-client-roots
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from notebook_tools.server import create_server


PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def plugin_version() -> str:
    """Read the canonical version from the Codex plugin manifest."""

    manifest = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        version = data["version"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError) as exc:
        raise RuntimeError(
            f"Could not read plugin version from {manifest}: {exc}"
        ) from exc
    if not isinstance(version, str) or not version:
        raise RuntimeError(f"Plugin manifest has no valid version: {manifest}")
    return version


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cell-aware Jupyter notebook tools for Codex over STDIO MCP."
    )
    roots = parser.add_mutually_exclusive_group(required=True)
    roots.add_argument(
        "--root",
        action="append",
        help="Absolute allowed filesystem root; repeat for more than one root.",
    )
    roots.add_argument(
        "--use-client-roots",
        action="store_true",
        help="Use MCP client roots, falling back to the explicit user roots config.",
    )
    parser.add_argument("--version", action="version", version=plugin_version())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    create_server(args.root, use_client_roots=args.use_client_roots).run(
        transport="stdio"
    )


if __name__ == "__main__":
    main()
