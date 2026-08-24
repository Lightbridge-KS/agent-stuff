#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.60", "typer>=0.12"]
# ///
"""Offline contract tests for the image-gen skill's imagegen.py CLI.

No network, no key. Subprocess tests pin the exit-code contract (params are
validated before any spend; a missing key teaches `lb key run`); in-process
tests mock the OpenAI client seam to verify output writing and the iterate
session sidecar's previous_response_id chaining.

    uv run tests/test_imagegen.py
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (
    REPO_ROOT / "plugins" / "creative" / "skills" / "image-gen" / "scripts" / "imagegen.py"
)

FAKE_B64 = base64.b64encode(b"not-a-real-png").decode()


def run_cli(*args: str, with_key: bool = False) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    if with_key:
        env["OPENAI_API_KEY"] = "sk-test-dummy"
    return subprocess.run(
        ["uv", "run", str(SCRIPT), *args], capture_output=True, text=True, env=env
    )


def load_module():
    spec = importlib.util.spec_from_file_location("imagegen", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestExitCodeContract(unittest.TestCase):
    """Parameter validation fires before the key check, which fires before any network."""

    def test_help_exits_zero(self):
        proc = run_cli("--help")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("generate", proc.stdout)

    def test_bad_size_exits_2_without_key(self):
        proc = run_cli("generate", "x", "-o", "out.png", "--size", "1000x1000")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("multiples of 16", proc.stderr)

    def test_size_ratio_and_pixel_bounds(self):
        for size in ("4096x1024", "3840x1024", "256x256"):
            proc = run_cli("generate", "x", "-o", "out.png", "--size", size)
            self.assertEqual(proc.returncode, 2, f"size {size}: {proc.stderr}")

    def test_transparent_jpeg_exits_2(self):
        proc = run_cli(
            "generate", "x", "-o", "out.jpg", "--background", "transparent", "-f", "jpeg"
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("png or webp", proc.stderr)

    def test_bulk_guard(self):
        proc = run_cli("generate", "x", "-o", "out.png", "-n", "5")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--allow-bulk", proc.stderr)

    def test_missing_key_exits_4_and_teaches_lb(self):
        proc = run_cli("generate", "x", "-o", "out.png")
        self.assertEqual(proc.returncode, 4)
        self.assertIn("lb key run openai-image-gen", proc.stderr)

    def test_malformed_session_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            sess = Path(tmp) / "bad.json"
            sess.write_text('{"turns": "nope"}')
            proc = run_cli(
                "iterate", "x", "-o", f"{tmp}/v.png", "--session", str(sess), with_key=True
            )
            self.assertEqual(proc.returncode, 2)
            self.assertIn("not a valid imagegen session", proc.stderr)


class TestMockedClient(unittest.TestCase):
    """Drive the app in-process with the OpenAI client seam mocked."""

    def setUp(self):
        from typer.testing import CliRunner

        self.imagegen = load_module()
        self.runner = CliRunner()
        self.env_patch = mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-dummy"})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def invoke(self, *args: str):
        return self.runner.invoke(self.imagegen.app, list(args))

    def test_generate_writes_numbered_outputs(self):
        client = mock.MagicMock()
        client.images.generate.return_value = SimpleNamespace(
            data=[SimpleNamespace(b64_json=FAKE_B64)] * 2,
            usage=SimpleNamespace(input_tokens=10, output_tokens=1056, total_tokens=1066),
        )
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            self.imagegen, "_client", return_value=client
        ):
            out = Path(tmp) / "logo.png"
            result = self.invoke("generate", "a fox", "-o", str(out), "-n", "2", "--json")
            self.assertEqual(result.exit_code, 0, result.output)
            payload = json.loads(result.output)
            self.assertEqual(len(payload["paths"]), 2)
            self.assertTrue((Path(tmp) / "logo_1.png").exists())
            self.assertTrue((Path(tmp) / "logo_2.png").exists())
            self.assertEqual(payload["usage"]["output_tokens"], 1056)
            self.assertEqual(client.images.generate.call_args.kwargs["quality"], "medium")

    def test_iterate_creates_then_chains_session(self):
        client = mock.MagicMock()

        def fake_response(rid):
            return SimpleNamespace(
                id=rid,
                usage=None,
                output=[
                    SimpleNamespace(
                        type="image_generation_call", result=FAKE_B64, revised_prompt="rp"
                    )
                ],
            )

        client.responses.create.side_effect = [fake_response("resp_1"), fake_response("resp_2")]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            self.imagegen, "_client", return_value=client
        ):
            sess = Path(tmp) / "s.json"
            r1 = self.invoke("iterate", "a fox", "-o", f"{tmp}/v1.png", "--session", str(sess))
            self.assertEqual(r1.exit_code, 0, r1.output)
            self.assertNotIn(
                "previous_response_id", client.responses.create.call_args.kwargs
            )
            saved = json.loads(sess.read_text())
            self.assertEqual(saved["turns"][0]["response_id"], "resp_1")

            r2 = self.invoke("iterate", "warmer", "-o", f"{tmp}/v2.png", "--session", str(sess))
            self.assertEqual(r2.exit_code, 0, r2.output)
            self.assertEqual(
                client.responses.create.call_args.kwargs["previous_response_id"], "resp_1"
            )
            saved = json.loads(sess.read_text())
            self.assertEqual([t["response_id"] for t in saved["turns"]], ["resp_1", "resp_2"])
            self.assertTrue((Path(tmp) / "v2.png").exists())

    def test_iterate_no_image_exits_3_with_driver_text(self):
        client = mock.MagicMock()
        client.responses.create.return_value = SimpleNamespace(
            id="resp_1",
            usage=None,
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="output_text", text="Which style?")],
                )
            ],
        )
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            self.imagegen, "_client", return_value=client
        ):
            result = self.invoke(
                "iterate", "a fox", "-o", f"{tmp}/v1.png", "--session", f"{tmp}/s.json"
            )
            self.assertEqual(result.exit_code, 3)
            self.assertIn("Which style?", result.output)
            self.assertFalse(Path(tmp, "s.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
