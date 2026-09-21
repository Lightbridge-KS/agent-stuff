#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer==0.19.2", "PyYAML==6.0.3", "markdown-it-py==4.0.0"]
# ///
"""Hermetic contract checks; RICH_DOCUMENT_LIVE=1 adds real Quarto/server checks."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "plugins/experiment/skills/rich-document"
sys.path.insert(0, str(SKILL / "scripts"))
import rd_core as core
import rd_viewer as viewer

SCRIPT = SKILL / "scripts/rich_document.py"
LIVE = os.environ.get("RICH_DOCUMENT_LIVE") == "1"


def ast(*blocks):
    return {"pandoc-api-version": [1, 23, 1], "meta": {}, "blocks": list(blocks)}


def block(kind, content):
    return {"t": kind, "c": content}


def text(value):
    return block("Para", [block("Str", value)])


def div(name, *children, props=None):
    return block("Div", [["", [name], props or []], list(children)])


def heading(label):
    return block("Header", [2, [label.lower(), [], []], [block("Str", label)]])


class ProfileTests(unittest.TestCase):
    def test_metadata_defaults_and_unknown_options(self):
        meta, body, offset = core.metadata("---\ntitle: Example\n---\nBody\n")
        self.assertEqual(meta, {"title": "Example"})
        self.assertEqual(body, "Body\n")
        self.assertEqual(offset, 3)
        for field in ("filters: [evil.lua]", "format: html", "execute: true", "title: Duplicate"):
            with self.subTest(field=field), self.assertRaises(core.Failure):
                core.metadata(f"---\ntitle: Example\n{field}\n---\nBody")

    def test_aliases_versions_and_nonliteral_titles(self):
        for metadata in ("title: &t Example\nsubtitle: *t", "title: Example\nartifact: {version: true}",
                         "title: Example\nartifact: {version: 2}", "title: '![x](https://example.com/image.png)'",
                         "title: Example\nassets: []", "title: '<script>bad</script>'"):
            with self.subTest(metadata=metadata), self.assertRaises(core.Failure):
                core.metadata(f"---\n{metadata}\n---\nBody")

    def test_fence_distinction_and_literal_nested_example(self):
        source = "```{mermaid}\nflowchart LR\n A-->B\n```\n"
        self.assertIn("{.mermaid}", core.normalize_fences(source, 0))
        literal = "````markdown\n```{python}\nprint('display only')\n```\n````\n"
        self.assertEqual(core.normalize_fences(literal, 0), literal)
        for source in ("```{python}\nprint('bad')\n```", "```{r}\n1+1\n```", "```python eval=true\nx\n```"):
            with self.subTest(source=source), self.assertRaises(core.Failure):
                core.normalize_fences(source, 3)

    def test_active_content_rejected_but_literal_code_preserved(self):
        for node in (block("RawBlock", ["html", "<script>x</script>"]),
                     block("RawInline", ["html", "<img src=x>"]), text("{{<"),
                     block("Link", [["", [], []], [block("Str", "bad")], ["javascript:alert(1)", ""]])):
            with self.subTest(node=node), self.assertRaises(core.Failure):
                core.validate_tree(ast(node), {})
        literal = block("CodeBlock", [["", ["html"], []], "<script>{{< include }}</script>"])
        self.assertEqual(core.validate_tree(ast(literal), {}), [])

    def test_catalog_layout_constraints(self):
        tabs = div("panel-tabset", heading("Before"), text("Old"), heading("After"), text("New"))
        columns = div("columns", div("column", text("Left")), div("column", text("Right")))
        self.assertEqual(core.validate_tree(ast(tabs, columns), {}), [])
        invalid = [div("panel-tabset", heading("Only")), div("columns", div("column", text("one"))),
                   div("column", text("outside")), div("callout-note", tabs),
                   div("callout-tip", text("x"), props=[["onclick", "bad"]])]
        for node in invalid:
            with self.subTest(node=node), self.assertRaises(core.Failure):
                core.validate_tree(ast(node), {})

    def test_mermaid_config_handlers_and_styles(self):
        for diagram in ('%%{init: {securityLevel: "loose"}}%%\nflowchart LR\nA-->B',
                        'flowchart LR; click A "https://example.com"', 'flowchart LR\nclassDef custom fill:red',
                        'flowchart LR\nA["<img src=x>"]'):
            with self.subTest(diagram=diagram), self.assertRaises(core.Failure):
                core.validate_tree(ast(block("CodeBlock", [["", ["mermaid"], []], diagram])), {})

    def test_table_attribute_injection(self):
        with self.assertRaises(core.Failure):
            core.validate_tree(ast(block("Table", [["", [], [["onclick", "bad"]]], []])), {})

    def test_asset_escape_signature_and_alt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.qmd"
            image = root / "tiny.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 12)
            assets = core.resolve_assets({"assets": {"tiny": "tiny.png"}}, source)
            image_ast = ast(block("Image", [["", [], []], [block("Str", "Tiny")], ["asset:tiny", ""]]))
            core.validate_tree(image_ast, assets)
            self.assertEqual(image_ast["blocks"][0]["c"][2][0], "assets/tiny.png")
            for metadata in ({"assets": {"bad": "../outside.png"}}, {"assets": {"bad": str(image)}},
                             {"assets": {"bad": "https://example.com/x.png"}}):
                with self.subTest(metadata=metadata), self.assertRaises(core.Failure):
                    core.resolve_assets(metadata, source)
            with self.assertRaises(core.Failure):
                core.validate_tree(ast(block("Image", [["", [], []], [], ["asset:tiny", ""]])), assets)
            image.write_text("<svg/>")
            with self.assertRaises(core.Failure):
                core.resolve_assets({"assets": {"tiny": "tiny.png"}}, source)

    def test_environment_scrubs_engine_overrides(self):
        with patch.dict(os.environ, {"QUARTO_PROFILE": "evil", "DENO_DIR": "evil", "PANDOC_DATA_DIR": "evil"}):
            clean = core.clean_env()
        self.assertFalse(any(k in clean for k in ("QUARTO_PROFILE", "DENO_DIR", "PANDOC_DATA_DIR")))
        self.assertIn("PATH", clean)

    def test_rendered_resource_audit(self):
        core.audit_html('<script>console.log("owned")</script><img src="data:image/png;base64,abcd"><a href="https://example.com">Link</a>')
        for html in ('<script src="https://example.com/evil.js"></script>', '<img src="file:///secret">',
                     '<iframe src="data:text/html,x"></iframe>', '<link href="document_files/theme.css">'):
            with self.subTest(html=html), self.assertRaises(core.Failure):
                core.audit_html(html)

    def test_ids_and_runtime_url_validation(self):
        for value in ("../elsewhere", "anything", "20260101T000000Z-abcdefabcdef/other"):
            with self.subTest(value=value), self.assertRaises(core.Failure):
                core.check_id(value)
        core.check_id("20260101T000000Z-abcdefabcdef")

    def test_cli_schema_and_json_invalid_id(self):
        proc = subprocess.run([sys.executable, str(SCRIPT), "schema"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("x-markdown-profile", json.loads(proc.stdout))
        proc = subprocess.run([sys.executable, str(SCRIPT), "stop", "../escape", "--json"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["stage"], "usage")
        proc = subprocess.run([sys.executable, str(SCRIPT), "list", "--limit", "0", "--json"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["stage"], "usage")


@unittest.skipUnless(LIVE, "set RICH_DOCUMENT_LIVE=1 for real Quarto/server acceptance")
class LiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rich-document-test-")
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.env = {**os.environ, "LIGHTBRIDGE_STATE_DIR": str(self.state)}
        self.ids = []

    def tearDown(self):
        for artifact_id in self.ids:
            viewer.stop(artifact_id)
        self.temp.cleanup()

    def cli(self, *args, expected=0):
        proc = subprocess.run([sys.executable, str(SCRIPT), *args, "--json"], cwd=self.root,
                              env=self.env, capture_output=True, text=True, timeout=150)
        self.assertEqual(proc.returncode, expected, proc.stderr + proc.stdout)
        return json.loads(proc.stdout)

    def source(self, body=None):
        path = self.root / "source.qmd"
        path.write_text(body or (SKILL / "assets/example.qmd").read_text())
        return path

    def test_present_stop_reopen_survives_source_and_parent(self):
        source = self.source()
        result = self.cli("present", str(source), "--no-open")
        artifact_id = result["artifact_id"]
        self.ids.append(artifact_id)
        self.assertTrue(result["saved"])
        html = Path(result["html_path"])
        digest = hashlib.sha256(html.read_bytes()).hexdigest()
        with urllib.request.urlopen(result["url"]) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("connect-src 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(self.cli("open", artifact_id, "--no-open")["url"], result["url"])
        base = result["url"].split("/?")[0]
        for req in (base + "/", result["url"].replace("/?", "/source.qmd?"),
                    urllib.request.Request(result["url"], headers={"Host": "evil.invalid"}),
                    urllib.request.Request(result["url"], headers={"Origin": "https://evil.invalid"})):
            with self.subTest(req=req), self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(req)
        source.unlink()
        self.cli("stop", artifact_id)
        self.assertTrue(html.exists())
        with ThreadPoolExecutor(max_workers=2) as pool:
            opened = list(pool.map(lambda _: self.cli("open", artifact_id, "--no-open"), range(2)))
        self.assertEqual(opened[0]["url"], opened[1]["url"])
        reopened = opened[0]
        foreground = subprocess.run([sys.executable, str(SCRIPT), "serve", artifact_id],
                                    cwd=self.root, env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(foreground.returncode, 0, foreground.stderr)
        self.assertEqual(json.loads(foreground.stdout)["url"], reopened["url"])
        self.assertEqual(hashlib.sha256(html.read_bytes()).hexdigest(), digest)
        self.assertEqual(reopened["html_path"], result["html_path"])
        self.assertEqual(self.cli("list")["items"][0]["id"], artifact_id)

    def test_temp_cleanup_and_invalid_mermaid(self):
        source = self.source("---\ntitle: Invalid diagram\n---\n\n```{mermaid}\nflowchart LR\n A -->\n```\n")
        result = self.cli("present", str(source), "--no-open", "--no-save", expected=2)
        self.assertEqual(result["location"], "diagram[0]")
        self.assertFalse(self.state.exists())
        source = self.source("---\ntitle: Temporary\n---\n\nA temporary document.\n")
        result = self.cli("present", str(source), "--no-open", "--no-save")
        self.ids.append(result["artifact_id"])
        html = Path(result["html_path"])
        self.assertFalse(result["saved"])
        self.cli("stop", result["artifact_id"])
        for _ in range(50):
            if not html.exists():
                break
            time.sleep(.02)
        self.assertFalse(html.exists())

    def test_no_execution_or_project_inheritance_and_image_copy(self):
        marker = self.root / "EXECUTED"
        (self.root / "_quarto.yml").write_text("project:\n  pre-render: python -c \"open('EXECUTED','w').write('bad')\"\n")
        # Tiny real PNG with a declared input; show executable-looking content literally.
        png = self.root / "tiny.png"
        png.write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c63606060f80f0001040100b51c0c020000000049454e44ae426082"))
        source = self.source('---\ntitle: Display only\nassets: {tiny: tiny.png}\n---\n\n![A tiny image](asset:tiny)\n\n```python\nfrom pathlib import Path\nPath("EXECUTED").write_text("bad")\n```\n\n````markdown\n```{python}\nprint("example")\n```\n{{< include evil >}}\n````\n')
        result = self.cli("present", str(source), "--no-open")
        self.ids.append(result["artifact_id"])
        self.assertFalse(marker.exists())
        html = Path(result["html_path"]).read_text()
        self.assertIn("data:image/png;base64", html)
        self.assertIn("EXECUTED", html)
        png.unlink()
        archived = Path(result["source_path"])
        self.assertTrue((archived.parent / "assets/tiny.png").is_file())


if __name__ == "__main__":
    unittest.main()
