#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "platformdirs>=4.3,<5",
#   "typer>=0.16,<1",
# ]
# ///
"""Manage fallback filesystem roots for notebook-tools plugin installations."""

from __future__ import annotations

from pathlib import Path

import typer

from notebook_tools.roots import (
    canonical_directories,
    default_config_path,
    read_config_roots,
    write_config_roots,
)


app = typer.Typer(no_args_is_help=True, help="Manage notebook-tools fallback roots.")


@app.command("path")
def show_path() -> None:
    """Print the platform-native configuration path."""

    typer.echo(default_config_path())


@app.command("list")
def list_roots() -> None:
    """List configured fallback roots, one per line."""

    for root in read_config_roots():
        typer.echo(root)


@app.command()
def add(root: Path) -> None:
    """Add an existing absolute directory; repeated additions are harmless."""

    try:
        candidate = canonical_directories([root])[0]
        roots = canonical_directories([*read_config_roots(), candidate])
    except (ValueError, IndexError) as exc:
        raise typer.BadParameter(str(exc), param_hint="ROOT") from exc
    path = write_config_roots(roots)
    typer.echo(f"Configured {candidate} in {path}")


@app.command()
def remove(root: Path) -> None:
    """Remove a configured root; removing an absent root is harmless."""

    if not root.is_absolute():
        raise typer.BadParameter("Root must be absolute.", param_hint="ROOT")
    candidate = root.expanduser().resolve(strict=False)
    roots = tuple(item for item in read_config_roots() if item != candidate)
    path = write_config_roots(roots)
    typer.echo(f"Removed {candidate} from {path}")


if __name__ == "__main__":
    app()
