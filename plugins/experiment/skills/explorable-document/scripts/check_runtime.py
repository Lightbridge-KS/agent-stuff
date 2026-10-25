#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer==0.19.2", "jsonschema==4.25.1", "ruff==0.11.10", "pyright==1.1.407"]
# ///
"""Maintainer Python dry checks with one manifest for local and CI tool versions."""

from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
for command in [
    ["ruff", "check", str(root)],
    ["ruff", "format", "--check", str(root)],
    ["pyright", str(root)],
]:
    subprocess.run(command, check=True)
