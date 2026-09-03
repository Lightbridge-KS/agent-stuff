#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for the ask-form skill's bundled CLI (`ask_form.py`).

The validator is exercised through the real process (`--validate`, `--example`, `--schema`);
the server is started with `--no-open`, its URL read from the first stderr line, and driven
over HTTP with urllib exactly as the browser page would be — token scope, route contract,
answer validation, the terminal state machine (submit / cancel / timeout, first writer wins)
and stdout purity (one JSON document per run, every exit path).

    uv run tests/test_ask_form.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "plugins" / "productivity" / "skills" / "ask-form" / "scripts" / "ask_form.py"

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
        return self

    def __exit__(self, *exc: object) -> None:
        try:
            self.proc.wait(timeout=60)
        finally:
            for s in (self.proc.stdout, self.proc.stderr):
                if s:
                    s.close()

    def finish(self) -> tuple[int, dict]:
        out, self.err = self.proc.communicate(timeout=60)
        return self.proc.returncode, json.loads(out)

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
        ex = json.loads(run("--example").stdout)  # cli recommended; confidence 4; both review items approve
        base = {"approach": "cli", "confidence": 4,
                "decisions": {"name": {"decision": "approve", "comment": ""}, "home": {"decision": "approve", "comment": ""}}}
        with Server(ex) as s:
            s.post("/submit", {"answers": base})
            code, out = s.finish()
        self.assertEqual(code, 0)
        self.assertNotIn("diverged", out["meta"])
        with Server(ex) as s:
            s.post("/submit", {"answers": {**base, "approach": "mcp", "confidence": 2,
                                           "decisions": {"name": {"decision": "approve", "comment": ""}, "home": {"decision": "reject", "comment": "no"}}}})
            code, out = s.finish()
        self.assertEqual(out["meta"]["diverged"], ["approach", "confidence", "decisions"])

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
            raw = json.loads(text.split("```json\n", 1)[1].rsplit("\n```", 1)[0])
            self.assertEqual(raw["result"]["answers"], out["answers"])
            self.assertEqual(raw["spec"]["title"], ex["title"])
            self.assertNotIn("_values", json.dumps(raw["spec"]))

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
