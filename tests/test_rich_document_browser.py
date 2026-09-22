#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer==0.19.2", "PyYAML==6.0.3", "markdown-it-py==4.0.0"]
# ///
"""Prepare a real browser regression page; readiness is not a test result.

Run with uv, open the returned URL, and inspect #rd-test-result for PASS/FAIL.
The page runs assertions with the real embedded Mermaid, Quarto, and viewer.
It injects one render failure in this temporary fixture only. Stop the returned
artifact ID with rich_document.py stop after inspection. No browser installation
or automation driver is required; an existing browser/harness can open the URL.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "plugins/experiment/skills/rich-document"
sys.path.insert(0, str(SKILL / "scripts"))
import rd_core as core
import rd_viewer as viewer


def prepare() -> dict:
    artifact, manifest = core.build(ROOT / "tests/fixtures/rich-document/regressions.qmd", saved=False)
    try:
        path = artifact / "rendered/index.html"
        html = path.read_text()
        marker = "// Renderer-owned reading controls."
        if html.count(marker) != 1:
            raise RuntimeError("Expected exactly one embedded viewer script")
        harness = (ROOT / "tests/fixtures/rich-document/browser-checks.js").read_text()
        html = html.replace(marker, harness + "\n" + marker, 1)
        path.write_text(html)
        manifest["html_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (artifact / "manifest.json").write_text(json.dumps(manifest))
        return viewer.start(artifact, SKILL / "scripts/rich_document.py")
    except BaseException:
        shutil.rmtree(artifact, ignore_errors=True)
        raise


if __name__ == "__main__":
    print(json.dumps(prepare()))
