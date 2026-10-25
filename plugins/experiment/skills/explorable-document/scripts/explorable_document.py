#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer==0.19.2", "jsonschema==4.25.1"]
# ///
"""Author, check, preserve, and explore MDX/TSX documents."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import shutil
import tempfile
import webbrowser

import typer
from ed_core import (
    RUNTIME,
    Failure,
    artifact,
    build,
    matched_evidence,
    publish,
    read_json,
    store_root,
)
import ed_viewer

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    help="Local source-backed explorations. Present returns immediately; stop ends its viewer.",
)


def perform(operation, as_json: bool = False):
    try:
        result = operation()
    except Failure as exc:
        print(json.dumps(exc.result, ensure_ascii=False))
        raise typer.Exit(exc.code) from exc
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "error", "stage": "storage", "message": str(exc)}))
        raise typer.Exit(4) from exc
    if as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def template(format: str) -> Path:
    if format not in {"mdx", "tsx", "dataset"}:
        raise Failure(2, "format", "Choose mdx, tsx, or dataset.")
    return RUNTIME / "templates" / format


@app.command()
def example(format: str = "mdx"):
    """Print a representative descriptor and source entry."""

    def operation():
        folder = template(format)
        descriptor = read_json(folder / "artifact.json")
        return {
            "descriptor": descriptor,
            "source": (folder / descriptor["entry"]).read_text(),
        }

    perform(operation, True)


@app.command()
def schema():
    """Print the authoritative descriptor schema and snapshot constraints."""
    perform(
        lambda: {
            "descriptor": read_json(RUNTIME / "descriptor.schema.json"),
            "snapshot": "JSON Schema draft-07 subset: explicit type; closed objects; bounded strings/arrays/numbers; no refs/patterns/combinators. See references/source.md.",
        },
        True,
    )


@app.command()
def init(
    path: Path, format: str = "mdx", json_output: bool = typer.Option(False, "--json")
):
    """Create maintained source, refusing to overwrite any destination."""

    def operation():
        if path.exists():
            raise Failure(
                2, "init", "Destination exists; choose a new source directory."
            )
        shutil.copytree(template(format), path)
        return {"status": "created", "source_path": str(path.resolve())}

    perform(operation, json_output)


@app.command()
def check(
    path: Path, browser: bool = False, json_output: bool = typer.Option(False, "--json")
):
    """Check/build without publication; optional fixed-runner Chromium checks."""

    def operation():
        work = Path(tempfile.mkdtemp(prefix="explorable-check-"))
        try:
            _, evidence = build(path, work, browser)
        except Failure as exc:
            exc.result["diagnostics_path"] = str(work)
            raise
        return {
            "status": "checked",
            **evidence,
            "evidence_path": str(work / "verification.json"),
            "preview_path": str(work / "rendered/index.html"),
            "screenshots_path": str(work / "screenshots") if browser else None,
        }

    perform(operation, json_output)


def launch(directory: Path, root: Path, no_open: bool, temporary: bool = False) -> dict:
    result = ed_viewer.start(directory, root, temporary)
    manifest = read_json(directory / "manifest.json")
    result.update(
        {
            "saved": not temporary,
            "artifact_path": str(directory),
            "source_path": str(directory / "source"),
            "browser_status": manifest["browser_status"],
        }
    )
    if not no_open:
        try:
            if not webbrowser.open(result["url"]):
                result["warning"] = "Browser launch unavailable; open the returned URL."
        except webbrowser.Error:
            result["warning"] = "Browser launch unavailable; open the returned URL."
    return result


@app.command()
def present(
    path: Path,
    revision_of: str | None = None,
    evidence: Path | None = None,
    no_open: bool = False,
    no_save: bool = False,
    json_output: bool = typer.Option(False, "--json"),
):
    """Check/build, publish a new immutable revision, and start its viewer."""

    def operation():
        root = (
            Path(tempfile.mkdtemp(prefix="explorable-temporary-"))
            if no_save
            else store_root()
        )
        if no_save and revision_of:
            raise Failure(
                2, "lineage", "Temporary artifacts cannot have saved lineage."
            )
        if revision_of:
            artifact(root, revision_of)
        with tempfile.TemporaryDirectory(prefix="explorable-present-") as temp:
            work = Path(temp)
            descriptor, verified = build(path, work)
            if evidence:
                supplied = read_json(evidence)
                verified = matched_evidence(supplied, verified, descriptor)
            directory, _ = publish(work, root, descriptor, verified, revision_of)
        return launch(directory, root, no_open, no_save)

    perform(operation, json_output)


@app.command("open")
def open_artifact(
    identifier: str,
    no_open: bool = False,
    json_output: bool = typer.Option(False, "--json"),
):
    """Verify archived hashes and serve saved output without Node or compilation."""

    def operation():
        root = store_root()
        directory, _ = artifact(root, identifier)
        return launch(directory, root, no_open)

    perform(operation, json_output)


@app.command("list")
def list_artifacts(
    limit: int = typer.Option(10, min=1, max=100),
    json_output: bool = typer.Option(False, "--json"),
):
    """List project-local artifact metadata, newest first."""

    def operation():
        items = [
            read_json(p) for p in (store_root() / "artifacts").glob("*/manifest.json")
        ]
        items.sort(key=lambda x: (x["created_at"], x["id"]), reverse=True)
        return {
            "items": [
                {
                    k: x[k]
                    for k in [
                        "id",
                        "title",
                        "created_at",
                        "revision_of",
                        "browser_status",
                    ]
                }
                for x in items[:limit]
            ]
        }

    perform(operation, json_output)


@app.command()
def stop(identifier: str, json_output: bool = typer.Option(False, "--json")):
    """Stop this viewer only; saved source and submissions remain."""
    perform(lambda: ed_viewer.stop(identifier), json_output)


@app.command()
def serve(identifier: str):
    """Foreground fallback; run in the harness's persistent terminal."""

    def operation():
        root = store_root()
        directory, _ = artifact(root, identifier)
        print(
            json.dumps(
                {
                    "status": "starting",
                    "artifact_id": identifier,
                    "hint": "Run open ID --no-open to obtain this foreground viewer URL.",
                }
            ),
            flush=True,
        )
        ed_viewer.serve(directory, root)
        return {"status": "stopped"}

    perform(operation)


@app.command()
def responses(
    identifier: str,
    after: str | None = None,
    limit: int = typer.Option(10, min=1, max=100),
    json_output: bool = typer.Option(False, "--json"),
):
    """Read submission metadata; explicit non-destructive pagination, no payload dump."""

    def operation():
        root = store_root()
        artifact(root, identifier)
        cursor = ("", "")
        if after:
            try:
                decoded = json.loads(base64.urlsafe_b64decode(after))
                if decoded["artifact"] != identifier:
                    raise ValueError("wrong artifact")
                cursor = (decoded["time"], decoded["id"])
            except (ValueError, KeyError, TypeError) as exc:
                raise Failure(
                    2, "cursor", "Use next_cursor returned for this artifact."
                ) from exc
        records = [
            read_json(p, 1_100_000)
            for p in (root / "submissions" / identifier).glob("*.json")
        ]
        records.sort(key=lambda x: (x["created_at"], x["submission_id"]))
        records = [x for x in records if (x["created_at"], x["submission_id"]) > cursor]
        page = records[:limit]
        next_cursor = None
        if page:
            last = page[-1]
            next_cursor = base64.urlsafe_b64encode(
                json.dumps(
                    {
                        "artifact": identifier,
                        "time": last["created_at"],
                        "id": last["submission_id"],
                    }
                ).encode()
            ).decode()
        return {
            "items": [
                {
                    k: x[k]
                    for k in [
                        "submission_id",
                        "created_at",
                        "artifact_id",
                        "rendered_hash",
                    ]
                }
                for x in page
            ],
            "next_cursor": next_cursor,
            "has_more": len(records) > limit,
        }

    perform(operation, json_output)


@app.command()
def response(
    identifier: str,
    submission_id: str,
    field: str | None = None,
    json_output: bool = typer.Option(False, "--json"),
):
    """Read one submission or JSON Pointer field with a 16 KiB output budget."""

    def operation():
        root = store_root()
        artifact(root, identifier)
        ed_viewer.record_path(
            submission_id
        )  # Validate opaque ID, never interpolate paths unchecked.
        record = read_json(
            root / "submissions" / identifier / f"{submission_id}.json", 1_100_000
        )
        value = record
        if field:
            if not field.startswith("/"):
                raise Failure(
                    2,
                    "pointer",
                    "JSON Pointer must start with /, for example /snapshot/arrival.",
                )
            try:
                for part in field[1:].split("/"):
                    part = part.replace("~1", "/").replace("~0", "~")
                    value = value[int(part)] if isinstance(value, list) else value[part]
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                raise Failure(
                    2,
                    "pointer",
                    "Field not found; choose a field in the snapshot schema.",
                ) from exc
        result = {"submission_id": submission_id, "value": value}
        if len(json.dumps(result, ensure_ascii=False).encode()) > 16384:
            return {
                "submission_id": submission_id,
                "status": "narrow_field",
                "message": "Result exceeds 16 KiB. Use --field /snapshot/<property>; no values were truncated.",
            }
        return result

    perform(operation, json_output)


@app.command("export")
def export_artifact(
    identifier: str,
    out: Path = typer.Option(..., "--out"),
    include_submissions: bool = False,
    json_output: bool = typer.Option(False, "--json"),
):
    """Create a portable source/static bundle; refuse an existing destination."""

    def operation():
        root = store_root()
        directory, _ = artifact(root, identifier)
        if out.exists():
            raise Failure(4, "export", "Destination exists; choose a new directory.")
        out.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".export-", dir=out.parent))
        try:
            shutil.copytree(directory, stage, dirs_exist_ok=True)
            if include_submissions and (root / "submissions" / identifier).exists():
                shutil.copytree(
                    root / "submissions" / identifier, stage / "submissions"
                )
            (stage / "README.md").write_text(
                "# Explorable document export\n\nView: `python3 -m http.server --bind 127.0.0.1 8000 --directory rendered` and open http://127.0.0.1:8000.\n\nRebuild with Node 26.7.0 and pnpm 10.18.2:\n\n```sh\ncd source/_toolchain\npnpm install --frozen-lockfile --ignore-scripts\nnode build.mjs .. ../../rebuilt\n```\n\nSource is executable browser content. Review it before rebuilding. Downloads do not submit to an agent. Dependencies require package availability; built viewing requires no Node or installed skill.\n"
            )
            stage.rename(out)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        return {
            "status": "exported",
            "path": str(out.resolve()),
            "included_submissions": include_submissions,
        }

    perform(operation, json_output)


if __name__ == "__main__":
    app()
