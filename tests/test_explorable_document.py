#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer==0.19.2", "jsonschema==4.25.1"]
# ///
"""Hermetic source/storage/receiver contracts; no Node, browser, or external service."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import importlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins/experiment/skills/explorable-document/scripts"
sys.path.insert(0, str(SCRIPTS))
core = importlib.import_module("ed_core")
viewer = importlib.import_module("ed_viewer")
cli = importlib.import_module("explorable_document")

SNAPSHOT = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"count": {"type": "integer", "minimum": 0, "maximum": 100}},
    "required": ["count"],
}


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        shutil.copytree(core.RUNTIME / "templates/tsx", self.source)
        self.root = self.base / "state"

    def tearDown(self):
        self.temp.cleanup()

    def validate(self):
        return core.validate_source(self.source, self.base / "validated")

    def edit(self, name, value):
        core.write_json(self.source / name, value)

    def fixture(self, handoff=False):
        work = self.base / f"work-{len(list(self.base.glob('work-*')))}"
        work.mkdir()
        descriptor = core.validate_source(self.source, work / "source")
        shutil.copytree(core.RUNTIME, work / "source/_toolchain")
        (work / "rendered").mkdir()
        core.write_json(
            work / "rendered/document.json", {"schema": SNAPSHOT if handoff else None}
        )
        for name in ["index.html", "viewer.js", "theme.css", "viewer.css"]:
            (work / "rendered" / name).write_text("fixture")
        evidence = {
            "schema_version": 1,
            "source_hash": "source",
            "toolchain_hash": "toolchain",
            "rendered_hash": "rendered",
            "browser": {"status": "not_run"},
            "static": "passed",
        }
        directory, manifest = core.publish(work, self.root, descriptor, evidence)
        return directory, manifest

    def test_templates_validate(self):
        for format in ["mdx", "tsx", "dataset"]:
            core.validate_source(
                core.RUNTIME / "templates" / format, self.base / format
            )

    def test_descriptor_rejects_extras_and_versions(self):
        for field, value in [
            ("schema_version", 2),
            ("surprise", True),
            ("title", "x" * 201),
        ]:
            with self.subTest(field=field):
                descriptor = core.read_json(
                    core.RUNTIME / "templates/tsx/artifact.json"
                )
                descriptor[field] = value
                self.edit("artifact.json", descriptor)
                with self.assertRaises(core.Failure):
                    self.validate()

    def test_duplicates_and_nonfinite_rejected(self):
        for text in ['{"a":1,"a":2}', '{"x":NaN}', "[]", "null"]:
            (self.source / "artifact.json").write_text(text)
            with self.assertRaises(core.Failure):
                self.validate()

    def test_traversal_and_symlink(self):
        for name in ["../secret", "/tmp/test", ".env", "data/../../escape", "x?raw"]:
            with self.assertRaises(core.Failure):
                core.relative(self.source, name)
        (self.source / "linked.ts").symlink_to(self.source / "document.tsx")
        with self.assertRaises(core.Failure):
            self.validate()

    def test_reserved_and_unlisted_files(self):
        for name in ["package.json", ".env", "unexpected.png"]:
            path = self.source / name
            path.write_text("{}")
            with self.assertRaises(core.Failure):
                self.validate()
            path.unlink()

    def test_text_limit(self):
        (self.source / "large.md").write_bytes(b"x" * (10 * 1024**2 + 1))
        with self.assertRaises(core.Failure):
            self.validate()

    def test_asset_and_rendered_byte_budgets(self):
        descriptor = core.read_json(self.source / "artifact.json")
        descriptor["assets"] = ["large.png"]
        self.edit("artifact.json", descriptor)
        with (self.source / "large.png").open("wb") as stream:
            stream.truncate(50 * 1024**2 + 1)
        with self.assertRaises(core.Failure):
            self.validate()
        rendered = self.base / "rendered"
        rendered.mkdir()
        with (rendered / "large.js").open("wb") as stream:
            stream.truncate(100 * 1024**2 + 1)
        with self.assertRaises(core.Failure):
            core.rendered_files(rendered)

    def test_closed_bounded_schema(self):
        core.bounded_schema(SNAPSHOT)
        for schema in [
            {"$ref": "https://example.com/schema"},
            {"type": "object"},
            {"type": "string"},
            {"type": "array", "maxItems": 10001},
            {"type": "number"},
            {"type": "string", "maxLength": 20, "pattern": "(x+)+"},
        ]:
            with self.assertRaises(core.Failure):
                core.bounded_schema(schema)

    def test_select_check_requires_a_string_value(self):
        checks = {
            "version": 1,
            "scenarios": [
                {
                    "interaction": "next",
                    "steps": [
                        {"action": "select", "selector": "select", "value": "1024"},
                        {"action": "value", "selector": "select", "value": "1024"},
                    ],
                }
            ],
        }
        self.edit("checks.json", checks)
        self.validate()
        checks["scenarios"][0]["steps"][0]["value"] = 1024
        self.edit("checks.json", checks)
        with self.assertRaises(core.Failure):
            self.validate()

    def test_assertions_are_required(self):
        self.edit(
            "checks.json",
            {
                "version": 1,
                "scenarios": [
                    {
                        "interaction": "next",
                        "steps": [{"action": "click", "selector": "button"}],
                    }
                ],
            },
        )
        with self.assertRaises(core.Failure):
            self.validate()

    def test_evidence_is_bound_and_excludes_cli_paths(self):
        current = {
            "schema_version": 1,
            "source_hash": "s",
            "toolchain_hash": "t",
            "rendered_hash": "r",
            "environment": {},
            "static": "passed",
            "browser": {"status": "not_run"},
        }
        descriptor = {"interactions": [{"id": "change"}]}
        self.assertEqual(core.matched_evidence(current, current, descriptor), current)
        for value in [
            {**current, "source_hash": "different"},
            {**current, "evidence_path": "/local/path"},
            {**current, "browser": {"status": "passed", "interactions": []}},
            {**current, "browser": {"status": "failed"}},
        ]:
            with self.assertRaises(core.Failure):
                core.matched_evidence(value, current, descriptor)

    def test_css_cannot_read_outside_assets(self):
        for css in [
            '@import "../../private.css";',
            "a{background:url(../../private.png)}",
            r"a{background:u\72l(private.png)}",
        ]:
            (self.source / "styles.css").write_text(css)
            with self.assertRaises(core.Failure):
                self.validate()

    def test_descriptor_size_and_interaction_bounds(self):
        (self.source / "artifact.json").write_text(" " * 65537)
        with self.assertRaises(core.Failure):
            self.validate()
        descriptor = core.read_json(core.RUNTIME / "templates/tsx/artifact.json")
        descriptor["interactions"] = [descriptor["interactions"][0]] * 101
        self.edit("artifact.json", descriptor)
        with self.assertRaises(core.Failure):
            self.validate()

    def test_immutable_publication_and_hashes(self):
        directory, manifest = self.fixture()
        directory2, manifest2 = self.fixture()
        self.assertNotEqual(manifest["id"], manifest2["id"])
        self.assertEqual(core.artifact(self.root, manifest["id"])[0], directory)
        shutil.rmtree(self.source)
        self.assertEqual(core.artifact(self.root, manifest2["id"])[0], directory2)
        (directory / "rendered/index.html").write_text("changed")
        with self.assertRaises(core.Failure):
            core.artifact(self.root, manifest["id"])

    def test_evidence_tamper(self):
        directory, manifest = self.fixture()
        core.write_json(directory / "verification.json", {"status": "passed"})
        with self.assertRaises(core.Failure):
            core.artifact(self.root, manifest["id"])

    def test_failed_publication_does_not_replace_existing(self):
        directory, manifest = self.fixture()
        with patch("ed_core.shutil.copytree", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                core.publish(
                    self.base / "work-0",
                    self.root,
                    core.read_json(self.source / "artifact.json"),
                    core.read_json(directory / "verification.json"),
                )
        self.assertTrue(directory.exists())
        core.artifact(self.root, manifest["id"])

    def test_submission_retry_and_conflict(self):
        _, manifest = self.fixture(True)
        value = {"snapshot": {"count": 4}, "comment": "reviewed"}
        key = "request_1234567890"
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(
                pool.map(
                    lambda _: viewer.save_submission(
                        self.root, manifest, SNAPSHOT, key, value
                    ),
                    range(4),
                )
            )
        self.assertEqual(len({r["submission_id"] for r in receipts}), 1)
        self.assertEqual(
            len(list((self.root / "submissions" / manifest["id"]).glob("*.json"))), 1
        )
        with self.assertRaises(core.Failure) as raised:
            viewer.save_submission(
                self.root, manifest, SNAPSHOT, key, {**value, "comment": "different"}
            )
        self.assertEqual(raised.exception.result["stage"], "conflict")

    def test_bad_snapshot_and_failed_save(self):
        _, manifest = self.fixture(True)
        for value in [
            {"snapshot": {"count": 101}, "comment": ""},
            {"snapshot": {"count": 1, "extra": 2}, "comment": ""},
            {"snapshot": {"count": 1}, "comment": "x" * 4001},
        ]:
            with self.assertRaises(core.Failure):
                viewer.save_submission(
                    self.root, manifest, SNAPSHOT, "request_1234567890", value
                )
        with patch("ed_viewer.os.link", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                viewer.save_submission(
                    self.root,
                    manifest,
                    SNAPSHOT,
                    "request_1234567890",
                    {"snapshot": {"count": 1}, "comment": ""},
                )
        self.assertEqual(
            list((self.root / "submissions" / manifest["id"]).glob("*.json")), []
        )

    def test_receiver_boundary(self):
        directory, manifest = self.fixture(True)
        server = viewer.make_server(directory, self.root, "secret-session")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        def request(route, data=None, **headers):
            try:
                with urlopen(
                    Request(base + route, data=data, headers=headers), timeout=2
                ) as response:
                    return response.status, response.read()
            except HTTPError as error:
                return error.code, error.read()

        try:
            self.assertEqual(request("/")[0], 200)
            self.assertEqual(request("/", Host="localhost")[0], 403)
            self.assertEqual(request("/../manifest.json")[0], 404)
            self.assertEqual(
                request("/api/session", Authorization="Bearer secret-session")[0], 200
            )
            payload = json.dumps({"snapshot": {"count": 2}, "comment": ""}).encode()
            headers = {
                "Authorization": "Bearer secret-session",
                "Content-Type": "application/json",
                "Idempotency-Key": "request_1234567890",
            }
            self.assertEqual(request("/api/submissions", payload, **headers)[0], 403)
            self.assertEqual(
                request("/api/submissions", payload, Origin="null", **headers)[0], 403
            )
            self.assertEqual(
                request("/api/submissions", payload, Origin=base, **headers)[0], 200
            )
            self.assertEqual(
                request(
                    "/api/submissions",
                    b"{}",
                    **{"Content-Length": str(core.MAX_JSON + 1)},
                    Origin=base,
                    **headers,
                )[0],
                413,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        self.assertEqual(
            len(list((self.root / "submissions" / manifest["id"]).glob("*.json"))), 1
        )

    def test_exploration_has_no_submission_route(self):
        directory, _ = self.fixture()
        server = viewer.make_server(directory, self.root, "token")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            request = Request(
                base + "/api/submissions",
                data=b"{}",
                headers={"Origin": base, "Authorization": "Bearer token"},
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request)
            self.assertEqual(raised.exception.code, 404)
            self.assertFalse((self.root / "submissions").exists())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_cli_retrieval_export_and_overwrite(self):
        _, manifest = self.fixture(True)
        identifier = manifest["id"]
        receipts = [
            viewer.save_submission(
                self.root,
                manifest,
                SNAPSHOT,
                f"request_123456789{x}",
                {"snapshot": {"count": x}, "comment": "note"},
            )
            for x in range(3)
        ]
        runner = CliRunner()
        with patch("explorable_document.store_root", return_value=self.root):
            result = runner.invoke(
                cli.app, ["responses", identifier, "--limit", "2", "--json"]
            )
            self.assertEqual(result.exit_code, 0, result.output)
            first = json.loads(result.output)
            self.assertEqual(len(first["items"]), 2)
            self.assertNotIn("snapshot", first["items"][0])
            result = runner.invoke(
                cli.app,
                ["responses", identifier, "--after", first["next_cursor"], "--json"],
            )
            self.assertEqual(len(json.loads(result.output)["items"]), 1)
            result = runner.invoke(
                cli.app,
                [
                    "response",
                    identifier,
                    receipts[0]["submission_id"],
                    "--field",
                    "/snapshot/count",
                    "--json",
                ],
            )
            self.assertEqual(json.loads(result.output)["value"], 0)
            out = self.base / "export"
            result = runner.invoke(
                cli.app, ["export", identifier, "--out", str(out), "--json"]
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertFalse((out / "submissions").exists())
            result = runner.invoke(
                cli.app, ["export", identifier, "--out", str(out), "--json"]
            )
            self.assertEqual(result.exit_code, 4)

    def test_no_build_reopen(self):
        directory, manifest = self.fixture()
        runner = CliRunner()
        with (
            patch("explorable_document.store_root", return_value=self.root),
            patch(
                "explorable_document.build",
                side_effect=AssertionError("Must not compile"),
            ),
            patch(
                "explorable_document.launch", return_value={"status": "ready"}
            ) as launch,
        ):
            result = runner.invoke(
                cli.app, ["open", manifest["id"], "--no-open", "--json"]
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(launch.call_args.args[0], directory)


if __name__ == "__main__":
    unittest.main()
