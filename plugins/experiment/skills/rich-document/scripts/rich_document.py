#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer==0.19.2", "PyYAML==6.0.3", "markdown-it-py==4.0.0"]
# ///
"""One-shot rich documents: a deterministic Quarto profile and local viewer."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import shutil
import webbrowser

import typer
from click import ClickException

from rd_core import ASSETS, Failure, artifact_root, build, engine, parse_source, read_artifact
import rd_viewer

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False,
                  help="Render and reopen rich documents. No code execution or viewer expiry.")


def emit(value: dict, as_json: bool):
    if as_json:
        print(json.dumps(value, ensure_ascii=False))
    else:
        if "items" in value:
            for item in value["items"]:
                print(f"{item['id']}  {item['title']}")
        else:
            print(value.get("status", "ok"))
            for key in ("artifact_id", "url", "html_path", "message", "location"):
                if key in value:
                    print(f"{key}: {value[key]}")
            for warning in value.get("warnings", []):
                print(f"warning: {warning}", file=sys.stderr)


def perform(operation, as_json: bool):
    try:
        result = operation()
    except Failure as exc:
        emit(exc.result, as_json)
        raise typer.Exit(exc.code)
    except (OSError, ValueError, KeyError) as exc:
        emit({"status": "error", "stage": "io", "message": str(exc)}, as_json)
        raise typer.Exit(4)
    emit(result, as_json)


def launch(result: dict, no_open: bool) -> dict:
    if not no_open:
        try:
            if not webbrowser.open(result["url"]):
                result["warnings"].append("Browser launch failed; open the returned URL.")
        except (OSError, webbrowser.Error):
            result["warnings"].append("Browser launch failed; open the returned URL.")
    return result


@app.command()
def example():
    """Print a supported source exercising every block type."""
    print((ASSETS / "example.qmd").read_text(), end="")


@app.command()
def schema():
    """Print metadata schema and supported block constraints."""
    print((ASSETS / "schema.json").read_text(), end="")


@app.command()
def validate(source: Path, json_output: bool = typer.Option(False, "--json")):
    """Check source, assets, and Mermaid syntax without publishing."""
    def operation():
        with tempfile.TemporaryDirectory(prefix="rich-document-validate-") as temp:
            work = Path(temp)
            doc = parse_source(source.resolve(), work, engine(work))
            return {"status": "valid", "title": doc["meta"]["title"],
                    "diagrams": len(doc["diagrams"]), "assets": len(doc["assets"])}
    perform(operation, json_output)


@app.command()
def present(source: Path, no_open: bool = False, no_save: bool = False,
            json_output: bool = typer.Option(False, "--json")):
    """Validate, render, save, open a local viewer, and return."""
    def operation():
        artifact, manifest = build(source, saved=not no_save)
        try:
            return launch(rd_viewer.start(artifact, Path(__file__).resolve()), no_open)
        except Failure as exc:
            if no_save:
                shutil.rmtree(artifact, ignore_errors=True)
                exc.result.pop("html_path", None)
                exc.result["temporary_output_removed"] = True
            raise
    perform(operation, json_output)


@app.command("open")
def open_artifact(artifact_id: str, no_open: bool = False,
                  json_output: bool = typer.Option(False, "--json")):
    """Reopen a saved artifact without rendering or the original source."""
    perform(lambda: launch(rd_viewer.start(read_artifact(artifact_id), Path(__file__).resolve()), no_open), json_output)


@app.command("list")
def list_artifacts(limit: int = typer.Option(10, min=1, max=100),
                   json_output: bool = typer.Option(False, "--json")):
    """List recent saved artifacts for the invocation project."""
    def operation():
        root = artifact_root()
        items, warnings = [], []
        for path in sorted(root.glob("*/manifest.json"), reverse=True):
            if path.parent.name.startswith("."):
                continue
            try:
                item = json.loads(path.read_text())
                items.append({key: item[key] for key in ("id", "title", "created")})
            except (OSError, ValueError, KeyError):
                warnings.append(f"Skipped unreadable artifact {path.parent.name}")
            if len(items) >= limit:
                break
        return {"status": "ok", "items": items, "warnings": warnings}
    perform(operation, json_output)


@app.command()
def stop(artifact_id: str, json_output: bool = typer.Option(False, "--json")):
    """Stop this artifact's viewer; preserve saved output."""
    perform(lambda: rd_viewer.stop(artifact_id), json_output)


@app.command()
def serve(artifact_id: str):
    """Foreground no-expiry fallback for a harness background runner."""
    try:
        artifact = read_artifact(artifact_id)
        rd_viewer.serve(artifact, guard_startup=True)
    except Failure as exc:
        emit(exc.result, True)
        raise typer.Exit(exc.code)


@app.command("_serve", hidden=True)
def internal_serve(artifact: Path):
    rd_viewer.serve(artifact)


if __name__ == "__main__":
    try:
        exit_code = app(standalone_mode=False)
        if isinstance(exit_code, int):
            sys.exit(exit_code)
    except ClickException as exc:
        if "--json" in sys.argv:
            emit({"status": "error", "stage": "usage", "message": exc.format_message()}, True)
        else:
            exc.show()
        sys.exit(exc.exit_code)
