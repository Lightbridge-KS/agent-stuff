#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer==0.19.2", "jsonschema==4.25.1"]
# ///
"""Opt-in real compiler/browser/receiver/export acceptance, with isolated lb state."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/experiment/skills/explorable-document"
CLI = SKILL / "scripts/explorable_document.py"


@unittest.skipUnless(
    os.environ.get("EXPLORABLE_DOCUMENT_LIVE") == "1",
    "Set EXPLORABLE_DOCUMENT_LIVE=1 for real browser/toolchain gates",
)
class Live(unittest.TestCase):
    def test_lifecycle_handoff_export(self):
        with tempfile.TemporaryDirectory(prefix="explorable-live-") as temporary:
            base = Path(temporary)
            environment = {**os.environ, "LIGHTBRIDGE_STATE_DIR": str(base / "state")}
            running = []

            def command(args, cwd=base):
                result = subprocess.run(
                    args,
                    cwd=cwd,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                return result.stdout

            def cli(*args):
                return json.loads(command(["uv", "run", str(CLI), *args, "--json"]))

            try:
                source = base / "source"
                cli("init", str(source), "--format", "mdx")
                descriptor = json.loads((source / "artifact.json").read_text())
                descriptor["handoff"] = {"schema": "snapshot.schema.json"}
                (source / "artifact.json").write_text(json.dumps(descriptor))
                schema = {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["arrival", "service", "jobs"],
                    "properties": {
                        "arrival": {"type": "number", "minimum": 0, "maximum": 20},
                        "service": {"type": "number", "minimum": 1, "maximum": 20},
                        "jobs": {
                            "type": ["number", "null"],
                            "minimum": 0,
                            "maximum": 1000,
                        },
                    },
                }
                (source / "snapshot.schema.json").write_text(json.dumps(schema))
                checked = cli("check", str(source), "--browser")
                presented = cli(
                    "present",
                    str(source),
                    "--no-open",
                    "--evidence",
                    checked["evidence_path"],
                )
                identifier = presented["artifact_id"]
                running.append(identifier)
                second = cli(
                    "present", str(source), "--no-open", "--revision-of", identifier
                )
                running.append(second["artifact_id"])
                self.assertNotEqual(identifier, second["artifact_id"])
                manifest = json.loads(
                    (Path(second["artifact_path"]) / "manifest.json").read_text()
                )
                self.assertEqual(manifest["revision_of"], identifier)
                exported = base / "export"
                cli("export", identifier, "--out", str(exported))
                self.assertFalse((exported / "submissions").exists())
                # Standalone frozen rebuild uses only the exported source/toolchain.
                toolchain = exported / "source/_toolchain"
                command(
                    ["pnpm", "install", "--frozen-lockfile", "--ignore-scripts"],
                    toolchain,
                )
                rebuilt = base / "rebuilt"
                command(["node", "build.mjs", "..", str(rebuilt)], toolchain)
                self.assertEqual(
                    (rebuilt / "document.json").read_bytes(),
                    (exported / "rendered/document.json").read_bytes(),
                )
                # The live harness prints no capability URL or token.
                live = json.loads(
                    command(
                        [
                            "node",
                            "live.mjs",
                            presented["url"],
                            str(exported),
                            str(base / "evidence"),
                        ],
                        toolchain,
                    )
                )
                self.assertEqual(live["status"], "passed")
                responses = cli("responses", identifier, "--limit", "1")
                self.assertEqual(len(responses["items"]), 1)
                self.assertTrue(responses["has_more"])
                next_page = cli(
                    "responses", identifier, "--after", responses["next_cursor"]
                )
                self.assertEqual(len(next_page["items"]), 1)
                result = cli(
                    "response",
                    identifier,
                    responses["items"][0]["submission_id"],
                    "--field",
                    "/snapshot/arrival",
                )
                self.assertEqual(result["value"], 6)
                cli("stop", identifier)
                shutil.rmtree(source)
                # Reopen succeeds with no original source and build tools unavailable.
                without_node = base / "no-build-tools"
                without_node.mkdir()
                for name in ["node", "pnpm"]:
                    stub = without_node / name
                    stub.write_text("#!/bin/sh\nexit 99\n")
                    stub.chmod(0o755)
                environment["PATH"] = (
                    str(without_node) + os.pathsep + environment["PATH"]
                )
                reopened = cli("open", identifier, "--no-open")
                self.assertEqual(reopened["status"], "ready")
                self.assertEqual(cli("stop", identifier)["status"], "stopped")
                print(
                    json.dumps(
                        {
                            "status": "passed",
                            "checks": live["checks"]
                            + [
                                "lineage",
                                "standalone rebuild",
                                "pagination",
                                "no-source/no-Node reopen",
                                "stop",
                            ],
                        }
                    )
                )
            finally:
                for identifier in running:
                    cli("stop", identifier)


if __name__ == "__main__":
    unittest.main()
