#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["jsonschema>=4.23"]
# ///
"""Behavioral tests for the ask-form skill's bundled CLI (`ask_form.py`).

The validator is exercised through the real process (`--validate`, `--example`, `--schema`),
and `--schema` is held to agree with it case by case (the CLI itself stays stdlib-only);
the server is started with `--no-open`, its URL read from the first stderr line, and driven
over HTTP with urllib exactly as the browser page would be — token scope, route contract,
answer validation, the terminal state machine (submit / cancel / timeout, first writer wins)
and stdout purity (one JSON document per run, every exit path).

    uv run tests/test_ask_form.py
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "plugins" / "productivity" / "skills" / "ask-form" / "scripts" / "ask_form.py"
SCRIPT_SPEC = importlib.util.spec_from_file_location("ask_form_under_test", SCRIPT)
assert SCRIPT_SPEC and SCRIPT_SPEC.loader
ASK_FORM = importlib.util.module_from_spec(SCRIPT_SPEC)
SCRIPT_SPEC.loader.exec_module(ASK_FORM)

# 1×1 transparent PNG, for the asset whitelist tests.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000" "01f15c4890000000d4944415478da6364f8cf0000020001010" "0a6d2f0b60000000049454e44ae426082"
)


def script_argv(script: Path, *args: str) -> list[str]:
    """argv launching a PEP 723 script the way its real consumer does (see test_repo_links.py)."""
    if os.name != "nt":
        return [str(script), *args]
    return ["uv", "run", str(script), *args]


def run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(script_argv(SCRIPT, *args), input=stdin, capture_output=True, text=True, timeout=120)


def spec(*questions: dict, **top) -> dict:
    return {"spec_version": 1, "title": "t", "questions": list(questions), **top}


def q(type_: str, id_: str = "q1", **kw) -> dict:
    return {"id": id_, "type": type_, "label": "Label", **kw}


OPTS = [{"value": "a", "label": "A"}, {"value": "b", "label": "B", "description": "d"}]


class Server:
    """Context manager around one running form: gives the URL, token and HTTP helpers."""

    def __init__(self, body: dict, timeout: float = 20, *args: str, state_dir: Path | None = None, cwd: Path | None = None) -> None:
        self.body, self.timeout, self.args, self.state_dir, self.cwd = body, timeout, list(args), state_dir, cwd

    def __enter__(self) -> "Server":
        env = {**os.environ}
        env["LIGHTBRIDGE_STATE_DIR"] = str(self.state_dir) if self.state_dir else str(Path(tempfile.gettempdir()) / "ask-form-tests-unused")
        self.proc = subprocess.Popen(
            script_argv(SCRIPT, "-", "--no-open", "--timeout", str(self.timeout), *self.args),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=self.cwd,
        )
        assert self.proc.stdin and self.proc.stderr
        self.proc.stdin.write(json.dumps(self.body))
        self.proc.stdin.close()
        self.proc.stdin = None  # so communicate() does not try to flush a closed pipe
        self.url = self.proc.stderr.readline().strip()
        assert self.url.startswith("http://127.0.0.1:"), self.url
        self.base, _, self.token = self.url.partition("/?t=")
        self.stderr_notes: list[str] = []
        return self

    def __exit__(self, *exc: object) -> None:
        try:
            self.proc.wait(timeout=60)
        finally:
            for s in (self.proc.stdout, self.proc.stderr):
                if s:
                    s.close()

    def finish(self) -> tuple[int, dict]:
        out, err = self.proc.communicate(timeout=150)
        self.err = "".join(self.stderr_notes) + err
        return self.proc.returncode, json.loads(out)

    def save_request(self) -> dict:
        """Read stderr notes through the staged-save request and return its JSON payload."""
        assert self.proc.stderr
        for _ in range(4):
            line = self.proc.stderr.readline()
            self.stderr_notes.append(line)
            if line.startswith("ASK_FORM_SAVE_REQUEST "):
                return json.loads(line.removeprefix("ASK_FORM_SAVE_REQUEST "))
        self.fail(f"staged-save request not found in stderr: {self.stderr_notes}")

    def get(self, path: str, token: bool = True) -> tuple[int, bytes]:
        sep = "&" if "?" in path else "?"
        url = self.base + path + (f"{sep}t={self.token}" if token else "")
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def post(self, path: str, body: object, token: bool = True, ctype: str = "application/json") -> tuple[int, dict]:
        """POST and return (status, json). A server that already shut down reads as status 0."""
        url = self.base + path + (f"?t={self.token}" if token else "")
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read()
                return r.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return e.code, {"raw": raw.decode(errors="replace")}
        except (urllib.error.URLError, ConnectionError):
            return 0, {}


class ValidatorCase(unittest.TestCase):
    def assert_invalid(self, body: dict, path_fragment: str) -> None:
        r = run("--validate", stdin=json.dumps(body))
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["status"], "invalid")
        self.assertTrue(any(path_fragment in e["path"] for e in out["errors"]), out["errors"])

    def assert_valid(self, body: dict) -> dict:
        r = run("--validate", stdin=json.dumps(body))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_example_validates_and_covers_every_type(self):
        ex = run("--example")
        self.assertEqual(ex.returncode, 0)
        body = json.loads(ex.stdout)
        types = {el["type"] for el in body["questions"]}
        self.assertEqual(len(types), 11, types)  # 10 catalog types + section
        self.assert_valid(body)

    def test_schema_is_json(self):
        r = run("--schema")
        self.assertEqual(r.returncode, 0)
        self.assertIn("oneOf", json.loads(r.stdout)["properties"]["questions"]["items"])

    def test_top_level(self):
        self.assert_invalid({"title": "t", "questions": [q("short_text")]}, "spec_version")
        self.assert_invalid(spec(q("short_text"), title=""), "title")
        self.assert_invalid({"spec_version": 1, "title": "t", "questions": []}, "questions")
        self.assert_invalid(spec(q("short_text", "Bad Id")), "id")
        self.assert_invalid(spec(q("short_text"), q("short_text")), "questions[1].id")
        self.assert_invalid(spec(q("mystery")), "type")

    def test_each_type_valid_and_invalid(self):
        cases = {
            "single_select": ({"options": OPTS, "allow_other": True}, {"options": []}, "options"),
            "multi_select": ({"options": OPTS, "min": 1, "max": 2}, {"options": OPTS, "min": 3, "max": 1}, "min"),
            "ranking": ({"options": OPTS}, {"options": [{"value": "a", "label": "A"}, {"value": "a", "label": "B"}]}, "value"),
            "scale": ({"min": 1, "max": 5, "labels": {"1": "lo"}}, {"min": 1}, "max"),
            "number": ({"min": 0, "max": 10, "step": 0.5, "unit": "mm"}, {"step": -1}, "step"),
            "short_text": ({"max_length": 40}, {"max_length": 0}, "max_length"),
            "long_text": ({"placeholder": "p"}, {"help": 5}, "help"),
            "matrix": ({"rows": OPTS, "columns": OPTS}, {"rows": OPTS}, "columns"),
            "review": ({"items": [{"id": "i1", "label": "I"}]}, {"items": [{"id": "i1", "label": "I"}], "decisions": ["one"]}, "decisions"),
            "context": ({"format": "markdown", "content": "hi"}, {"format": "image", "src": "/nope/none.png"}, "src"),
            "section": ({}, {"label": ""}, "label"),
        }
        # recommendation fields
        two_rec = [{"value": "a", "label": "A", "recommended": True}, {"value": "b", "label": "B", "recommended": True}]
        self.assert_valid(spec(q("single_select", options=[two_rec[0], {"value": "b", "label": "B"}], recommendation="A, because.")))
        self.assert_valid(spec(q("multi_select", options=two_rec)))
        self.assert_invalid(spec(q("single_select", options=two_rec)), "options")
        self.assert_invalid(spec(q("ranking", options=two_rec)), "options")
        self.assert_invalid(spec(q("scale", min=1, max=5, recommended=9)), "recommended")
        self.assert_invalid(spec(q("short_text", recommendation="")), "recommendation")
        self.assert_invalid(spec(q("review", items=[{"id": "i", "label": "I", "recommended": "maybe"}])), "recommended")
        for type_, (good, bad, frag) in cases.items():
            with self.subTest(type_=type_):
                self.assert_valid(spec(q(type_, **good)))
                self.assert_invalid(spec(q(type_, **bad)), frag)

    def test_rich_content_fields(self):
        """v2 additions are optional and validated: option detail, tabs panels, collapsed."""
        detailed = [{"value": "a", "label": "A", "detail": "```mermaid\nflowchart LR\n  A --> B\n```"}, {"value": "b", "label": "B"}]
        panels = [{"label": "Now", "content": "x"}, {"label": "Then", "content": "y"}]
        self.assert_valid(spec(q("single_select", options=detailed), q("multi_select", "m", options=detailed)))
        self.assert_valid(spec(q("context", format="tabs", panels=panels, collapsed=True)))
        self.assert_valid(spec(q("context", format="markdown", content="x", collapsed=False)))
        self.assert_invalid(spec(q("single_select", options=[{"value": "a", "label": "A", "detail": ""}])), "options[0].detail")
        self.assert_invalid(spec(q("context", format="tabs", panels=panels[:1])), "panels")
        self.assert_invalid(spec(q("context", format="tabs", panels=[*panels] * 4)), "panels")
        self.assert_invalid(spec(q("context", format="tabs", panels=[panels[0], {"label": "B"}])), "panels[1].content")
        self.assert_invalid(spec(q("context", format="markdown", content="x", collapsed="yes")), "collapsed")
        self.assert_invalid(spec(q("context", format="video", content="x")), "format")
        self.assert_valid(spec(q("context", format="diff", content="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b")))
        self.assert_invalid(spec(q("context", format="diff")), "content")
        self.assert_valid(spec(q("short_text"), layout="split"))
        self.assert_invalid(spec(q("short_text"), layout="grid"), "layout")
        self.assert_valid(spec(q("review", items=[{"id": "i", "label": "I", "detail": "```diff\n-a\n+b\n```"}])))
        self.assert_invalid(spec(q("review", items=[{"id": "i", "label": "I", "detail": 3}])), "items[0].detail")

    def test_matrix_row_and_column_fields(self):
        """A matrix row takes a description and recommends a column; anything the page drops is rejected."""
        rows = [{"value": "push", "label": "git push", "description": "Publishes commits.", "recommended": "ask"},
                {"value": "status", "label": "git status"}]
        cols = [{"value": "allow", "label": "Allow", "description": "no prompt"}, {"value": "ask", "label": "Ask"}]
        self.assert_valid(spec(q("matrix", rows=rows, columns=cols, recommendation="Ask before anything leaves the machine.")))
        self.assert_invalid(spec(q("matrix", rows=[{**rows[0], "recommended": "deny"}], columns=cols)), "rows[0].recommended")
        self.assert_invalid(spec(q("matrix", rows=[{**rows[0], "recommended": True}], columns=cols)), "rows[0].recommended")
        self.assert_invalid(spec(q("matrix", rows=[{**rows[1], "detail": "x"}], columns=cols)), "rows[0].detail")
        self.assert_invalid(spec(q("matrix", rows=rows, columns=[{**cols[0], "detail": "x"}, cols[1]])), "columns[0].detail")
        self.assert_invalid(spec(q("matrix", rows=rows, columns=[cols[0], {**cols[1], "recommended": True}])), "columns[1].recommended")

    def test_ranking_options_take_no_detail(self):
        """The ranking page shows label and description only, so a detail would reach the record unseen."""
        self.assert_valid(spec(q("ranking", options=OPTS)))
        for detail in ("Why **A**.", "  "):
            r = run("--validate", stdin=json.dumps(spec(q("ranking", options=[{**OPTS[0], "detail": detail}, OPTS[1]]))))
            self.assertEqual(r.returncode, 2, r.stdout)
            errors = [e for e in json.loads(r.stdout)["errors"] if e["path"].endswith("options[0].detail")]
            self.assertEqual([e["message"] for e in errors], [ASK_FORM.NO_DETAIL["ranking"]])

    def test_malformed_lists_are_exit_2_not_a_traceback(self):
        self.assert_invalid(spec(q("review", items=5)), "items")
        self.assert_invalid(spec(q("matrix", rows=None, columns=7)), "rows")
        self.assert_invalid(spec(q("single_select", options=None)), "options")

    def test_validate_reports_answerable_required_assets(self):
        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / "pic.png"
            img.write_bytes(PNG)
            out = self.assert_valid(spec(
                q("section", "s"), q("context", "c", format="image", src=str(img)),
                q("short_text", "a", required=True), q("number", "b"),
            ))
        self.assertEqual(out["answerable"], ["a", "b"])
        self.assertEqual(out["required"], ["a"])
        self.assertEqual(len(out["assets"]), 1)

    def test_bad_json_and_missing_file(self):
        r = run("--validate", stdin="{not json")
        self.assertEqual(r.returncode, 2)
        self.assertIn("not valid JSON", json.loads(r.stdout)["errors"][0]["message"])
        r = run("--validate", "/definitely/missing.json")
        self.assertEqual(r.returncode, 2)

    @unittest.skipIf(os.name == "nt", "pty is POSIX only")
    def test_tty_stdin_without_spec_exits_2(self):
        import pty

        try:
            master, slave = pty.openpty()
        except OSError as e:  # sandboxes without pty devices
            self.skipTest(f"no pty available: {e}")
        try:
            r = subprocess.run(script_argv(SCRIPT, "--validate"), stdin=slave, capture_output=True, text=True, timeout=60)
        finally:
            os.close(master)
            os.close(slave)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("terminal", json.loads(r.stdout)["errors"][0]["message"])


ONE_REC = [{"value": "a", "label": "A", "recommended": True}, {"value": "b", "label": "B"}]
TWO_REC = [{"value": "a", "label": "A", "recommended": True}, {"value": "b", "label": "B", "recommended": True}]
PANELS = [{"label": "Now", "content": "x"}, {"label": "Then", "content": "y"}]

# (case, spec, both must accept?) — every rule JSON Schema can express, on both sides of it.
AGREEMENT_CASES = [
    ("multi_select counts", spec(q("multi_select", options=OPTS, min=0, max=2)), True),
    ("multi_select fractional min", spec(q("multi_select", options=OPTS, min=1.5)), False),
    ("multi_select negative max", spec(q("multi_select", options=OPTS, max=-1)), False),
    ("multi_select boolean min", spec(q("multi_select", options=OPTS, min=True)), False),
    ("multi_select two recommended", spec(q("multi_select", options=TWO_REC)), True),
    ("single_select one recommended", spec(q("single_select", options=ONE_REC)), True),
    ("single_select two recommended", spec(q("single_select", options=TWO_REC)), False),
    ("ranking recommended false", spec(q("ranking", options=[{**OPTS[0], "recommended": False}, OPTS[1]])), True),
    ("ranking recommended true", spec(q("ranking", options=ONE_REC)), False),
    ("option detail blank", spec(q("single_select", options=[{**OPTS[0], "detail": "  "}, OPTS[1]])), False),
    ("single_select option detail", spec(q("single_select", options=[{**OPTS[0], "detail": "x"}, OPTS[1]])), True),
    ("multi_select option detail", spec(q("multi_select", options=[{**OPTS[0], "detail": "x"}, OPTS[1]])), True),
    ("ranking option description", spec(q("ranking", options=OPTS)), True),
    ("ranking option detail", spec(q("ranking", options=[{**OPTS[0], "detail": "x"}, OPTS[1]])), False),
    ("matrix row description", spec(q("matrix", rows=OPTS, columns=OPTS)), True),
    ("matrix row recommends a column", spec(q("matrix", rows=[{**OPTS[0], "recommended": "b"}], columns=OPTS)), True),
    ("matrix row recommended boolean", spec(q("matrix", rows=[{**OPTS[0], "recommended": True}], columns=OPTS)), False),
    ("matrix row detail", spec(q("matrix", rows=[{**OPTS[0], "detail": "x"}], columns=OPTS)), False),
    ("matrix column detail", spec(q("matrix", rows=OPTS, columns=[{**OPTS[0], "detail": "x"}])), False),
    ("matrix column recommended", spec(q("matrix", rows=OPTS, columns=[{**OPTS[0], "recommended": False}])), False),
    ("option label empty", spec(q("ranking", options=[{"value": "a", "label": ""}])), False),
    ("title blank", spec(q("short_text"), title="   "), False),
    ("label blank", spec(q("short_text", label="   ")), False),
    ("recommendation blank", spec(q("short_text", recommendation="  ")), False),
    ("short_text boolean max_length", spec(q("short_text", max_length=True)), False),
    ("short_text placeholder", spec(q("short_text", placeholder="p")), True),
    ("long_text placeholder not text", spec(q("long_text", placeholder=5)), False),
    ("scale fractional step", spec(q("scale", min=0, max=1, step=0.25)), True),
    ("scale zero step", spec(q("scale", min=0, max=1, step=0)), False),
    ("number negative step", spec(q("number", step=-1)), False),
    ("number unbounded", spec(q("number")), True),
    ("context markdown", spec(q("context", format="markdown", content="x")), True),
    ("context markdown no content", spec(q("context", format="markdown")), False),
    ("context mermaid empty content", spec(q("context", format="mermaid", content="")), False),
    ("context image url", spec(q("context", format="image", src="https://example.com/a.png")), True),
    ("context image no src", spec(q("context", format="image")), False),
    ("context tabs", spec(q("context", format="tabs", panels=PANELS)), True),
    ("context tabs no panels", spec(q("context", format="tabs")), False),
    ("context tabs one panel", spec(q("context", format="tabs", panels=PANELS[:1])), False),
    ("context tabs blank panel", spec(q("context", format="tabs", panels=[PANELS[0], {"label": "B", "content": " "}])), False),
    ("context without label", spec({"id": "c", "type": "context", "format": "markdown", "content": "x"}), True),
    ("context empty label", spec(q("context", format="markdown", content="x", label="")), False),
    ("review custom decisions", spec(q("review", items=[{"id": "i", "label": "I", "recommended": "yes"}], decisions=["yes", "no"])), True),
    ("review empty item id", spec(q("review", items=[{"id": "", "label": "I"}])), False),
    ("review empty decision", spec(q("review", items=[{"id": "i", "label": "I"}], decisions=["ok", ""])), False),
    ("review blank detail", spec(q("review", items=[{"id": "i", "label": "I", "detail": " "}])), False),
]

# Rules only `--validate` can check; the schema's `$comment` names each of them.
VALIDATOR_ONLY_CASES = [
    ("duplicate element id", spec(q("short_text"), q("long_text"))),
    ("duplicate option value", spec(q("single_select", options=[OPTS[0], {**OPTS[1], "value": "a"}]))),
    ("min above max", spec(q("number", min=5, max=1))),
    ("recommended outside range", spec(q("scale", min=1, max=5, recommended=9))),
    ("review recommended not a decision", spec(q("review", items=[{"id": "i", "label": "I", "recommended": "maybe"}]))),
    ("matrix row recommended not a column", spec(q("matrix", rows=[{**OPTS[0], "recommended": "zzz"}], columns=OPTS))),
    ("unreadable image src", spec(q("context", format="image", src="/definitely/missing.png"))),
]


class SchemaConformanceCase(unittest.TestCase):
    """`--schema` is the documented single source of truth for fields: it must agree with `--validate`."""

    @classmethod
    def setUpClass(cls):
        import jsonschema

        r = run("--schema")
        assert r.returncode == 0, r.stderr
        cls.schema = json.loads(r.stdout)
        jsonschema.Draft202012Validator.check_schema(cls.schema)
        cls.checker = jsonschema.Draft202012Validator(cls.schema)

    def verdicts(self, body: dict) -> tuple[bool, bool]:
        errors, _ = ASK_FORM.validate_spec(copy.deepcopy(body))  # the validator annotates the spec it checks
        return self.checker.is_valid(body), not errors

    def test_example_conforms_to_schema(self):
        example = json.loads(run("--example").stdout)
        self.assertEqual([e.message for e in self.checker.iter_errors(example)], [])

    def test_schema_and_validator_agree(self):
        for name, body, ok in AGREEMENT_CASES:
            with self.subTest(case=name):
                self.assertEqual(self.verdicts(body), (ok, ok), "(schema, validator)")

    def test_validator_only_rules_are_named_in_the_schema(self):
        for name, body in VALIDATOR_ONLY_CASES:
            with self.subTest(case=name):
                self.assertEqual(self.verdicts(body), (True, False), "(schema, validator)")
        for phrase in ("ids unique", "values unique", "min ≤ max", "within min..max", "one of its decisions",
                       "one of its column values", "readable image file"):
            self.assertIn(phrase, self.schema["$comment"])


class ServerCase(unittest.TestCase):
    def form(self) -> dict:
        return spec(
            q("single_select", "pick", options=OPTS, allow_other=True, required=True),
            q("multi_select", "many", options=OPTS),
            q("long_text", "notes"),
            title="Round trip",
        )

    def test_token_scope_and_page(self):
        with Server(self.form()) as s:
            self.assertEqual(s.get("/", token=False)[0], 403)
            status, page = s.get("/")
            self.assertEqual(status, 200)
            html = page.decode()
            self.assertIn("Round trip", html)
            self.assertIn('id="spec"', html)
            self.assertEqual(s.get("/static/styles.css", token=False)[0], 200)
            self.assertEqual(s.get("/static/../scripts/ask_form.py", token=False)[0], 404)
            self.assertEqual(s.get("/asset/0")[0], 404)
            self.assertEqual(s.get("/nope")[0], 404)
            self.assertEqual(s.post("/submit", {"answers": {}}, token=False)[0], 403)
            s.post("/cancel", {})
            code, out = s.finish()
        self.assertEqual((code, out["status"]), (1, "cancelled"))

    def test_page_is_self_contained(self):
        """v2: every library is vendored; the CSP allows scripts from self only."""
        with Server(self.form()) as s:
            html = s.get("/")[1].decode()
            self.assertIn("script-src 'self';", html)
            self.assertNotIn("cdnjs", html)
            self.assertIn("/static/rich.js", html)
            head = html.split("</head>", 1)[0]
            # reader preferences apply before first paint: prefs.js precedes the stylesheet in <head>
            self.assertLess(head.index("/static/prefs.js"), head.index("/static/styles.css"))
            for path in ("/static/prefs.js", "/static/rich.js", "/static/vendor/mermaid.min.js", "/static/vendor/highlight.min.js"):
                self.assertEqual(s.get(path, token=False)[0], 200, path)
            s.post("/cancel", {})
            s.finish()
        static = SCRIPT.parent.parent / "static"
        for own in ("app.js", "rich.js", "prefs.js"):
            self.assertNotRegex((static / own).read_text(), r"https?://", own)

    def test_asset_whitelist(self):
        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / "pic.png"
            img.write_bytes(PNG)
            body = spec(q("context", "c", format="image", src=str(img)), q("short_text", "a"))
            with Server(body) as s:
                self.assertEqual(s.get("/asset/0", token=False)[0], 403)
                status, data = s.get("/asset/0")
                self.assertEqual((status, data), (200, PNG))
                self.assertEqual(s.get("/asset/9")[0], 404)
                s.post("/cancel", {})
                s.finish()

    def test_submit_round_trip(self):
        with Server(self.form()) as s:
            self.assertEqual(s.post("/submit", {"answers": {"pick": "a"}, "notes": {"ghost": "x"}})[0], 400)  # note for unknown id
            self.assertEqual(s.post("/submit", {"answers": {"pick": "a"}, "comments": 5})[0], 400)
            status, out = s.post("/submit", {"answers": {"pick": "something else", "many": ["a", "b"]}, "other": ["pick"],
                                             "notes": {"many": "  web first  ", "notes": ""}, "comments": "Nice form."})
            self.assertEqual((status, out["status"]), (200, "submitted"))
            # a later terminal POST hits the 0.3 s grace window (409) or a server already gone (0)
            self.assertIn(s.post("/submit", {"answers": {"pick": "a"}})[0], (409, 0))
            code, out = s.finish()
        self.assertEqual(code, 0)
        self.assertEqual(out["status"], "submitted")
        self.assertEqual(out["answers"], {"pick": "something else", "many": ["a", "b"]})
        self.assertEqual(out["meta"]["skipped"], ["notes"])
        self.assertEqual(out["meta"]["other"], ["pick"])
        self.assertEqual(out["meta"]["notes"], {"many": "web first"})  # blank notes dropped, text stripped
        self.assertEqual(out["meta"]["comments"], "Nice form.")
        self.assertIsInstance(out["meta"]["duration_s"], float)

    def test_answer_validation_keeps_the_run_alive(self):
        with Server(self.form()) as s:
            self.assertEqual(s.post("/submit", {"answers": {"many": ["a"]}})[0], 400)  # required missing
            self.assertEqual(s.post("/submit", {"answers": {"pick": "zzz"}})[0], 400)  # not an option, not other
            self.assertEqual(s.post("/submit", {"answers": {"pick": "a", "ghost": 1}})[0], 400)
            self.assertEqual(s.post("/submit", {"answers": {"pick": "a", "many": ["a", "typed"]}, "other": ["many"]})[0], 200)  # allow_other defaults on
            code0, out0 = s.finish()
        self.assertEqual((code0, out0["answers"]["many"]), (0, ["a", "typed"]))
        self.assertNotIn("notes", out0["meta"])
        with Server(self.form()) as s:
            self.assertEqual(s.post("/submit", b"{}", ctype="text/plain")[0], 415)
            self.assertEqual(s.post("/submit", b"{nope", ctype="application/json")[0], 400)
            status, _ = s.post("/submit", {"answers": {"pick": "a"}})
            self.assertEqual(status, 200)
            code, out = s.finish()
        self.assertEqual(code, 0)
        self.assertEqual(out["answers"], {"pick": "a"})

    def test_every_type_accepts_a_well_formed_answer(self):
        ex = json.loads(run("--example").stdout)
        answers = {
            "approach": "cli", "surfaces": ["web"], "priority": ["polish", "speed", "safety"], "confidence": 4,
            "budget_days": 2.5, "codename": "glasshouse", "concerns": "none",
            "fit": {"cli": "good", "renderer": "ok"},
            "decisions": {"name": {"decision": "approve", "comment": ""}, "home": {"decision": "revise", "comment": "why"}},
        }
        with Server(ex) as s:
            self.assertEqual(s.post("/submit", {"answers": {**answers, "priority": ["speed"]}})[0], 400)  # partial ranking
            self.assertEqual(s.post("/submit", {"answers": {**answers, "confidence": 9}})[0], 400)
            self.assertEqual(s.post("/submit", {"answers": {**answers, "fit": {"cli": "nope"}}})[0], 400)
            self.assertEqual(s.post("/submit", {"answers": {**answers, "decisions": {"name": {"decision": "maybe"}}}})[0], 400)
            self.assertEqual(s.post("/submit", {"answers": answers})[0], 200)
            code, out = s.finish()
        self.assertEqual(code, 0)
        self.assertEqual(out["answers"], answers)
        self.assertEqual(out["meta"]["skipped"], [])

    def test_diverged_reports_choices_against_recommendations(self):
        ex = json.loads(run("--example").stdout)  # cli recommended; confidence 4; both review items approve; fit cli → good
        base = {"approach": "cli", "confidence": 4,
                "decisions": {"name": {"decision": "approve", "comment": ""}, "home": {"decision": "approve", "comment": ""}},
                "fit": {"cli": "good", "renderer": "bad"}}  # renderer carries no recommendation
        with Server(ex) as s:
            s.post("/submit", {"answers": base})
            code, out = s.finish()
        self.assertEqual(code, 0)
        self.assertNotIn("diverged", out["meta"])
        with Server(ex) as s:
            s.post("/submit", {"answers": {**base, "approach": "mcp", "confidence": 2,
                                           "decisions": {"name": {"decision": "approve", "comment": ""}, "home": {"decision": "reject", "comment": "no"}},
                                           "fit": {"cli": "ok", "renderer": "bad"}}})
            code, out = s.finish()
        self.assertEqual(out["meta"]["diverged"], ["approach", "confidence", "decisions", "fit"])

    def test_page_carries_matrix_row_and_column_fields(self):
        """Regression: row descriptions and recommendations must reach the page, not only the schema."""
        ex = json.loads(run("--example").stdout)
        with Server(ex) as s:
            html = s.get("/")[1].decode()
            s.post("/cancel", {})
            s.finish()
        inlined = json.loads(html.split('<script id="spec" type="application/json">', 1)[1].split("</script>", 1)[0])
        fit = next(e for e in inlined["questions"] if e["id"] == "fit")
        self.assertTrue(all(r.get("description") for r in fit["rows"]), fit["rows"])
        self.assertEqual(fit["rows"][0]["recommended"], "good")
        self.assertTrue(any(c.get("description") for c in fit["columns"]), fit["columns"])
        self.assertNotIn("_recommended", fit)  # validator scratch stays server-side
        app = (SCRIPT.parent.parent / "static" / "app.js").read_text()
        matrix = app.split("const renderMatrix", 1)[1].split("const renderReview", 1)[0]
        for field in ("r.description", "r.recommended", "c.description"):
            self.assertIn(field, matrix, f"renderMatrix ignores {field}")

    def test_record_saved_under_project_asks(self):
        ex = json.loads(run("--example").stdout)
        answers = {"approach": "mcp", "surfaces": ["web"], "confidence": 2, "codename": "glasshouse",
                   "fit": {"cli": "good", "renderer": "ok"},
                   "decisions": {"name": {"decision": "approve", "comment": ""}, "home": {"decision": "revise", "comment": "why"}}}
        with tempfile.TemporaryDirectory() as td:
            state, proj = Path(td) / "state", Path(td) / "proj"
            proj.mkdir()  # not a git repo → keyed by its own path, git: none
            with Server(ex, state_dir=state, cwd=proj) as s:
                s.post("/submit", {"answers": answers, "notes": {"approach": "loopback is proven"}, "comments": "Ship it."})
                code, out = s.finish()
            self.assertEqual(code, 0)
            files = list((state).glob("*/asks/*.md"))
            self.assertEqual(len(files), 1, files)
            record = files[0]
            self.assertEqual(out["meta"]["saved"], str(record))
            self.assertIn(f"saved {record}", s.err)
            self.assertRegex(record.name, r"^\d{4}-\d{2}-\d{2}_\d{4}_ask-form-every-element-type\.md$")
            text = record.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"))
            self.assertIn("status: submitted", text)
            self.assertIn("git: none", text)
            self.assertIn(f"project: {json.dumps(str(proj.resolve()))}", text)
            for eid in out["answers"]:
                self.assertEqual(text.count(f"`{eid}`"), 1, eid)
            self.assertIn("**Answer:** MCP first `mcp`", text)
            self.assertIn("**Diverged** from the recommendation.", text)
            self.assertIn("**Note:** loopback is proven", text)
            self.assertIn("**Answer:** _skipped_", text)
            self.assertIn("## Comments\n\nShip it.", text)
            tail = text.split("\n## Raw\n\n", 1)[1].strip().splitlines()
            self.assertRegex(tail[0], r"^````+json$")  # the example's detail carries ``` fences
            raw = json.loads("\n".join(tail[1:-1]))
            self.assertEqual(raw["result"]["answers"], out["answers"])
            self.assertEqual(raw["spec"]["title"], ex["title"])
            self.assertNotIn("_values", json.dumps(raw["spec"]))

    def test_record_keeps_context_panes_in_order(self):
        body = spec(
            q("context", "why", format="markdown", content="Because:\n\n```python\nx = 1\n```"),
            q("context", "flow", format="mermaid", content="flowchart LR\n  A --> B"),
            q("context", "shot", format="image", src="https://example.com/a.png"),
            q("short_text", "name"),
        )
        body["questions"][0].pop("label")
        result = {"answers": {"name": "x"}, "meta": {}}
        ctx = {"created": "2026-09-23T00:00:00", "project": "/p", "git": "none"}
        text = ASK_FORM.render_record(body, result, ctx)
        self.assertIn("*Context*\n\nBecause:\n\n```python\nx = 1\n```", text)
        self.assertIn("*Context — Label*\n\n```mermaid\nflowchart LR\n  A --> B\n```", text)
        self.assertIn("Image: `https://example.com/a.png`", text)
        self.assertLess(text.index("```mermaid"), text.index("### Label  `name`"))
        self.assertEqual(ASK_FORM._fence("text", "a ``` b"), "````text\na ``` b\n````")

    def test_record_keeps_tabs_and_compared_detail(self):
        body = spec(
            q("context", "c", format="tabs", panels=[{"label": "Now", "content": "old"}, {"label": "Then", "content": "new"}]),
            q("single_select", "pick", options=[{"value": "a", "label": "A", "detail": "Why **A**."}, {"value": "b", "label": "B"}]),
        )
        text = ASK_FORM.render_record(body, {"answers": {"pick": "a"}, "meta": {}}, {"created": "c", "project": "p", "git": "none"})
        self.assertIn("#### Now\n\nold\n\n#### Then\n\nnew", text)
        self.assertIn("<details><summary>Compared detail</summary>\n\n#### A\n\nWhy **A**.\n\n</details>", text)
        self.assertNotIn("#### B", text)

    def test_record_keeps_diff_and_item_detail(self):
        body = spec(
            q("context", "c", format="diff", content="@@ -1 +1 @@\n-a\n+b"),
            q("review", "r", items=[{"id": "i", "label": "Hunk 1", "detail": "Why."}]),
        )
        result = {"answers": {"r": {"i": {"decision": "approve", "comment": ""}}}, "meta": {}}
        text = ASK_FORM.render_record(body, result, {"created": "c", "project": "p", "git": "none"})
        self.assertIn("```diff\n@@ -1 +1 @@\n-a\n+b\n```", text)
        self.assertIn("<details><summary>Item detail</summary>\n\n#### Hunk 1\n\nWhy.", text)

    def test_record_keeps_matrix_row_descriptions_and_recommendations(self):
        body = spec(q("matrix", "perm",
                      rows=[{"value": "push", "label": "git push", "description": "Publishes commits.", "recommended": "ask"},
                            {"value": "status", "label": "git status"}],
                      columns=[{"value": "allow", "label": "Allow"}, {"value": "ask", "label": "Ask"}],
                      recommendation="Ask before anything leaves the machine."))
        result = {"answers": {"perm": {"push": "allow", "status": "allow"}}, "meta": {"diverged": ["perm"]}}
        text = ASK_FORM.render_record(body, result, {"created": "c", "project": "p", "git": "none"})
        self.assertIn("- git push → Allow — _Publishes commits._\n- git status → Allow\n", text)
        self.assertIn("**Recommended:** git push: Ask — Ask before anything leaves the machine.", text)
        self.assertIn("**Diverged** from the recommendation.", text)

    def test_record_ends_block_answers_before_the_next_line(self):
        """GFM reads a line right after a list or quote as a lazy continuation of its last item."""
        body = spec(q("multi_select", "ms", options=ONE_REC, recommendation="why"),
                    q("ranking", "rk", options=OPTS, recommendation="why"),
                    q("long_text", "lt"), q("single_select", "ss", options=ONE_REC))
        answers = {"ms": ["b"], "rk": ["b", "a"], "lt": "my answer", "ss": "b"}
        meta = {"diverged": ["ms", "ss"], "notes": {"lt": "a note"}}
        text = ASK_FORM.render_record(body, {"answers": answers, "meta": meta}, {"created": "c", "project": "p", "git": "none"})
        self.assertIn("- B `b`\n\n**Recommended:** A `a` — why\n**Diverged** from the recommendation.\n", text)
        self.assertIn("2. A\n\n**Recommended:** — — why\n", text)
        self.assertIn("> my answer\n\n**Note:** a note\n", text)
        self.assertIn("**Answer:** B `b`\n**Recommended:** A `a`\n", text)  # one-line answers stay one paragraph
        self.assertNotIn("\n\n\n", text.split("## Raw")[0])

    def test_record_puts_quoted_notes_in_their_own_block(self):
        body = spec(q("short_text", "a"), q("short_text", "b"))
        meta = {"notes": {"a": "> quoted line\n\nReply.", "b": "plain"}}
        text = ASK_FORM.render_record(body, {"answers": {}, "meta": meta}, {"created": "c", "project": "p", "git": "none"})
        self.assertIn("**Note:**\n\n> quoted line\n\nReply.", text)
        self.assertIn("**Note:** plain", text)

    def test_staged_record_is_verified_before_saved_is_reported(self):
        with tempfile.TemporaryDirectory() as td:
            state, proj = Path(td) / "state", Path(td) / "proj"
            proj.mkdir()
            with Server(self.form(), 20, "--stage-save", state_dir=state, cwd=proj) as s:
                s.post("/submit", {"answers": {"pick": "a"}})
                request = s.save_request()
                source, destination = Path(request["source"]), Path(request["destination"])
                stage_dir = source.parent
                self.assertTrue(source.is_file())
                self.assertEqual(source.stat().st_mode & 0o777, 0o600)
                self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), request["sha256"])
                self.assertEqual(request["timeout_s"], 120.0)
                self.assertEqual(destination.parent.parent.parent, state)
                self.assertEqual(destination.parent.name, "asks")
                destination.parent.mkdir(parents=True)
                destination.write_bytes(source.read_bytes())
                code, out = s.finish()
            self.assertEqual((code, out["status"]), (0, "submitted"))
            self.assertEqual(out["meta"]["saved"], str(destination))
            self.assertIn(f"saved {destination}", s.err)
            self.assertFalse(stage_dir.exists())

    def test_staged_record_abort_and_mismatch_are_best_effort(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state"
            with Server(self.form(), 20, "--stage-save", state_dir=state) as s:
                s.post("/submit", {"answers": {"pick": "a"}})
                request = s.save_request()
                stage_dir = Path(request["source"]).parent
                Path(request["abort"]).touch()
                code, out = s.finish()
            self.assertEqual((code, out["status"]), (0, "submitted"))
            self.assertNotIn("saved", out["meta"])
            self.assertIn("not saved: staged record commit aborted", s.err)
            self.assertFalse(stage_dir.exists())

            with Server(self.form(), 20, "--stage-save", state_dir=state) as s:
                s.post("/submit", {"answers": {"pick": "a"}})
                request = s.save_request()
                destination = Path(request["destination"])
                stage_dir = Path(request["source"]).parent
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text("different", encoding="utf-8")
                code, out = s.finish()
            self.assertEqual((code, out["status"]), (0, "submitted"))
            self.assertNotIn("saved", out["meta"])
            self.assertIn("not saved: staged record destination has different content", s.err)
            self.assertFalse(stage_dir.exists())

    def test_stage_save_conflicts_with_no_save(self):
        r = run("--stage-save", "--no-save", stdin=json.dumps(self.form()))
        self.assertEqual(r.returncode, 2)
        out = json.loads(r.stdout)
        self.assertEqual(out["status"], "invalid")
        self.assertEqual(out["errors"][0]["path"], "--stage-save")

    def test_staged_record_timeout_and_collision_planning(self):
        result = {"status": "submitted", "answers": {"pick": "a"},
                  "meta": {"duration_s": 1.0, "skipped": ["many", "notes"], "other": []}}
        fixed = datetime(2026, 9, 13, 23, 59)
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {"LIGHTBRIDGE_STATE_DIR": str(Path(td) / "state")}):
            proj = Path(td) / "proj"
            proj.mkdir()
            first, _ = ASK_FORM.prepare_record(self.form(), result, cwd=proj, now=fixed)
            first.parent.mkdir(parents=True)
            first.write_text("existing", encoding="utf-8")
            second, _ = ASK_FORM.prepare_record(self.form(), result, cwd=proj, now=fixed)
            self.assertEqual(second.name, "2026-09-13_2359_round-trip-2.md")

            notes = io.StringIO()
            with contextlib.redirect_stderr(notes), self.assertRaisesRegex(TimeoutError, "timed out"):
                ASK_FORM.save_record_staged(self.form(), result, cwd=proj, now=fixed, timeout=0.05)
            request_line = next(line for line in notes.getvalue().splitlines() if line.startswith("ASK_FORM_SAVE_REQUEST "))
            request = json.loads(request_line.removeprefix("ASK_FORM_SAVE_REQUEST "))
            self.assertFalse(Path(request["source"]).parent.exists())

    def test_no_save_and_cancel_write_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state"
            with Server(self.form(), 20, "--no-save", state_dir=state) as s:
                s.post("/submit", {"answers": {"pick": "a"}})
                code, out = s.finish()
            self.assertEqual(code, 0)
            self.assertNotIn("saved", out["meta"])
            with Server(self.form(), state_dir=state) as s:
                s.post("/cancel", {})
                s.finish()
            self.assertEqual(list(state.rglob("*.md")), [])

    def test_unwritable_state_dir_is_a_note_not_a_failure(self):
        with tempfile.TemporaryDirectory() as td:
            blocker = Path(td) / "file-not-dir"
            blocker.write_text("x")
            with Server(self.form(), state_dir=blocker) as s:  # mkdir under a regular file fails
                s.post("/submit", {"answers": {"pick": "a"}})
                code, out = s.finish()
            self.assertEqual((code, out["status"]), (0, "submitted"))
            self.assertNotIn("saved", out["meta"])
            self.assertIn("not saved:", s.err)

    def test_cancel_then_submit_conflicts(self):
        with Server(self.form()) as s:
            self.assertEqual(s.post("/cancel", {})[0], 200)
            self.assertIn(s.post("/cancel", {})[0], (409, 0))
            code, out = s.finish()
        self.assertEqual((code, out), (1, {"status": "cancelled"}))

    def test_timeout(self):
        with Server(self.form(), timeout=2) as s:
            code, out = s.finish()
        self.assertEqual((code, out), (1, {"status": "timeout"}))

    def test_stdout_is_one_json_document_on_every_path(self):
        for args, stdin in ((("--validate",), "{bad"), (("--example",), None), (("--schema",), None)):
            r = run(*args, stdin=stdin)
            json.loads(r.stdout)  # raises if anything but one document
        with Server(self.form(), timeout=2) as s:
            out, err = s.proc.communicate(timeout=60)
        json.loads(out)
        self.assertTrue(s.url.startswith("http://127.0.0.1:"))  # the first stderr line, already consumed


if __name__ == "__main__":
    unittest.main(verbosity=2)
