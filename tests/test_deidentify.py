#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["typer>=0.12", "pyyaml>=6", "presidio-anonymizer>=2.2.364,<3"]
# ///
"""Contract tests for the deidentify skill's deid.py CLI.

Offline by default (no spaCy, no network): the module is imported in-process with only its
light top-level deps, and verbs are driven through typer's CliRunner. These pin the exit-code
contract (policy/request validation happens before any engine loads), the custom operators
(pseudonym, date_shift) and their reversal, the sidecar schema, and every shipped preset.

    uv run tests/test_deidentify.py
    DEID_LIVE=1 uv run tests/test_deidentify.py            # + real spaCy/Tesseract E2E on fixtures
    DEID_PRESIDIO_TESTDATA=<dir> ...                        # + DICOM E2E on presidio's test data
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = REPO_ROOT / "plugins" / "privacy" / "skills" / "deidentify"
SCRIPT = SKILL / "scripts" / "deid.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "deid"

spec = importlib.util.spec_from_file_location("deid", SCRIPT)
deid = importlib.util.module_from_spec(spec)
sys.modules["deid"] = deid
spec.loader.exec_module(deid)

runner = CliRunner()


def invoke(*args: str, env: dict | None = None):
    return runner.invoke(deid.app, list(args), env=env)


class TestHelpAndRouting(unittest.TestCase):
    def test_help_lists_every_verb(self):
        r = invoke("--help")
        self.assertEqual(r.exit_code, 0)
        for verb in ("entities", "scan", "anonymize", "verify", "restore", "doctor"):
            self.assertIn(verb, r.output)

    def test_missing_input_exits_2(self):
        r = invoke("scan", "nope.md")
        self.assertEqual(r.exit_code, 2)
        self.assertIn("not found", r.output)

    def test_pdf_refused_with_parse_to_md_hint(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.pdf"
            p.write_bytes(b"%PDF")
            r = invoke("scan", str(p))
        self.assertEqual(r.exit_code, 2)
        self.assertIn("parse-to-md", r.output)

    def test_unknown_extension_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.xyz"
            p.write_text("hi")
            r = invoke("scan", str(p))
        self.assertEqual(r.exit_code, 2)

    def test_kind_of(self):
        self.assertEqual(deid.kind_of(Path("a.md")), "text")
        self.assertEqual(deid.kind_of(Path("a.csv")), "csv")
        self.assertEqual(deid.kind_of(Path("a.json")), "json")
        self.assertEqual(deid.kind_of(Path("a.PNG")), "image")
        self.assertEqual(deid.kind_of(Path("a.dcm")), "dicom")
        self.assertEqual(deid.kind_of(Path("somedir"), dicom_flag=True), "dicom")


class TestPolicyValidation(unittest.TestCase):
    def policy(self, text: str):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write(text)
        return f.name

    def test_unknown_preset_lists_presets(self):
        r = invoke("scan", str(FIXTURES / "note.md"), "--policy", "nope")
        self.assertEqual(r.exit_code, 2)
        self.assertIn("presets:", r.output)
        self.assertIn("safe-harbor", r.output)

    def test_every_shipped_preset_loads(self):
        presets = sorted((SKILL / "references" / "policies").glob("*.yaml"))
        self.assertGreaterEqual(len(presets), 4)
        for p in presets:
            pol = deid.Policy.load(p.stem)
            self.assertIn("DEFAULT", pol.operators, p.name)

    def test_unknown_op_exits_2(self):
        r = invoke("scan", str(FIXTURES / "note.md"), "--policy", self.policy("operators:\n  PERSON: {op: vanish}\n"))
        self.assertEqual(r.exit_code, 2)
        self.assertIn("unknown op", r.output)

    def test_mask_needs_chars_to_mask(self):
        with self.assertRaises(deid.PolicyError):
            deid.Policy.from_dict({"operators": {"PHONE_NUMBER": {"op": "mask"}}})

    def test_encrypt_key_in_policy_refused(self):
        with self.assertRaises(deid.PolicyError) as cm:
            deid.Policy.from_dict({"operators": {"US_SSN": {"op": "encrypt", "key": "x" * 16}}})
        self.assertIn("DEID_KEY", str(cm.exception))

    def test_unknown_top_level_key(self):
        with self.assertRaises(deid.PolicyError):
            deid.Policy.from_dict({"operator": {}})

    def test_bad_regex_pattern(self):
        with self.assertRaises(deid.PolicyError):
            deid.Policy.from_dict({"patterns": [{"name": "hn", "entity": "ID", "regex": "("}]})

    def test_columns_forced_entity_matches_last_segment(self):
        pol = deid.Policy.from_dict({"columns": {"hn": "ID"}})
        self.assertEqual(pol.forced_entity("hn"), "ID")
        self.assertEqual(pol.forced_entity("patient.hn"), "ID")
        self.assertIsNone(pol.forced_entity("name"))

    def test_columns_cli_parsing(self):
        self.assertEqual(deid._validate_columns("hn=ID, mrn=ID"), {"hn": "ID", "mrn": "ID"})
        with self.assertRaises(deid.PolicyError):
            deid._validate_columns("hn")

    def test_entity_names_must_be_upper_snake(self):
        with self.assertRaises(deid.PolicyError):
            deid.Policy.from_dict({"entities": ["person"]})

    def test_sidecar_and_residual_properties(self):
        pseudo = deid.Policy.load("pseudonym")
        self.assertTrue(pseudo.needs_sidecar)
        self.assertIn("DATE_TIME", pseudo.residual_entities)
        harbor = deid.Policy.load("safe-harbor")
        self.assertFalse(harbor.needs_sidecar)  # date_shift alone stays irreversible without a sidecar
        self.assertTrue(harbor.reversible)
        self.assertFalse(deid.Policy.load("redact").reversible)


class TestLlmGuard(unittest.TestCase):
    def test_cloud_tags_refused_before_any_engine(self):
        for ref in ("ollama:gpt-oss:120b-cloud", "ollama:qwen3.5:cloud"):
            r = invoke("scan", str(FIXTURES / "note.md"), "--llm", ref)
            self.assertEqual(r.exit_code, 2, ref)
            self.assertIn("leave this machine", r.output)

    def test_only_ollama_provider(self):
        r = invoke("scan", str(FIXTURES / "note.md"), "--llm", "openai:gpt-4o")
        self.assertEqual(r.exit_code, 2)

    def test_is_cloud_model(self):
        self.assertTrue(deid.is_cloud_model("gpt-oss:120b-cloud"))
        self.assertTrue(deid.is_cloud_model("deepseek-v4-flash:cloud"))
        self.assertFalse(deid.is_cloud_model("gemma4:e4b"))
        self.assertFalse(deid.is_cloud_model("hf.co/x/cloudy-model-GGUF:Q6_K"))  # only the tag counts


class TestAnonymizeGuards(unittest.TestCase):
    def test_pseudonym_without_sidecar_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            r = invoke("anonymize", str(FIXTURES / "note.md"), "-o", f"{d}/out.md", "--policy", "pseudonym")
        self.assertEqual(r.exit_code, 2)
        self.assertIn("--sidecar", r.output)

    def test_refuses_to_overwrite_input(self):
        src = str(FIXTURES / "note.md")
        r = invoke("anonymize", src, "-o", src, "--policy", "redact")
        self.assertEqual(r.exit_code, 2)
        self.assertIn("overwrite", r.output)

    def test_encrypt_needs_deid_key(self):
        pol = deid.Policy.from_dict({"operators": {"US_SSN": {"op": "encrypt"}}})
        env = {k: v for k, v in os.environ.items() if k != "DEID_KEY"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(deid.typer.Exit) as cm:
                deid.RunState.start(pol)
        self.assertEqual(cm.exception.exit_code, deid.EXIT_ENV)

    def test_restore_rejects_foreign_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            side = Path(d) / "map.json"
            side.write_text('{"foo": 1}')
            r = invoke("restore", str(FIXTURES / "note.md"), "-o", f"{d}/x.md", "--sidecar", str(side))
        self.assertEqual(r.exit_code, 2)
        self.assertIn("not a deid sidecar", r.output)


class TestOperators(unittest.TestCase):
    def test_pseudonym_is_consistent_and_reversible(self):
        mapping: dict = {}
        op = deid.Pseudonym()
        p = {"entity_type": "PERSON", "entity_mapping": mapping, "format": "<{entity}_{n}>"}
        self.assertEqual(op.operate("Jane Doe", p), "<PERSON_1>")
        self.assertEqual(op.operate("Somchai", p), "<PERSON_2>")
        self.assertEqual(op.operate("Jane Doe", p), "<PERSON_1>")
        rev = deid.PseudonymReverse()
        self.assertEqual(rev.operate("<PERSON_2>", {"entity_mapping": mapping}), "Somchai")
        self.assertEqual(rev.operate("<UNKNOWN_9>", {"entity_mapping": mapping}), "<UNKNOWN_9>")

    def test_date_shift_preserves_format_and_reverses(self):
        for text in ("1985-03-14", "12/06/2024", "14 March 1985", "Mar 14, 1985", "2024-06-12 09:30"):
            shifted = deid.shift_date(text, 37)
            self.assertIsNotNone(shifted, text)
            self.assertNotEqual(shifted, text)
            self.assertEqual(deid.shift_date(shifted, -37), text)

    def test_date_shift_unparseable_falls_back_to_counter(self):
        mapping: dict = {}
        params = {"entity_type": "DATE_TIME", "days": 10, "entity_mapping": mapping}
        self.assertEqual(deid.DateShift().operate("next week", params), "<DATE_TIME_1>")
        self.assertEqual(deid.DateShift().operate("1985-03-14", params), "1985-03-24")
        self.assertEqual(deid.DateShiftReverse().operate("<DATE_TIME_1>", params), "next week")
        self.assertEqual(deid.DateShiftReverse().operate("1985-03-24", params), "1985-03-14")

    def test_operator_configs_forward_and_reverse(self):
        pol = deid.Policy.from_dict({"operators": {
            "PERSON": {"op": "pseudonym"}, "DATE_TIME": {"op": "date_shift", "days": 5},
            "PHONE_NUMBER": {"op": "mask", "chars_to_mask": 4}, "US_SSN": {"op": "encrypt"}}})
        with mock.patch.dict(os.environ, {"DEID_KEY": "k" * 32}):
            state = deid.RunState.start(pol)
            fwd = state.operator_configs()
            rev = state.operator_configs(reverse=True)
        self.assertEqual(state.date_offset_days, 5)
        self.assertEqual({k: v.operator_name for k, v in fwd.items()},
                         {"PERSON": "pseudonym", "DATE_TIME": "date_shift", "PHONE_NUMBER": "mask", "US_SSN": "encrypt", "DEFAULT": "replace"})
        self.assertEqual({k: v.operator_name for k, v in rev.items()},
                         {"PERSON": "pseudonym", "DATE_TIME": "date_shift", "US_SSN": "decrypt"})

    def test_random_offset_never_zero(self):
        pol = deid.Policy.from_dict({"operators": {"DATE_TIME": {"op": "date_shift", "range": 1}}})
        for _ in range(20):
            self.assertIn(deid.RunState.start(pol).date_offset_days, (-1, 1))


class TestStructuredHelpers(unittest.TestCase):
    def test_placeholder_detection(self):
        for v in ("<PERSON>", "<ID_12>", " <TH_TNIN_1> "):
            self.assertTrue(deid.is_placeholder(v), v)
        for v in ("Jane", "<person>", "12345678", "<PERSON_1> and more"):
            self.assertFalse(deid.is_placeholder(v), v)

    def test_group_context_words(self):
        self.assertEqual(deid.group_context("patient.phone_number"), ["patient", "phone", "number"])

    def test_json_leaves_and_dotted(self):
        data = {"a": {"b": "x"}, "l": ["y", {"c": "z"}], "n": 1}
        leaves = list(deid.json_leaves(data))
        self.assertEqual([v for _, v in leaves], ["x", "y", "z"])
        self.assertEqual([deid.dotted(p) for p, _ in leaves], ["a.b", "l", "l.c"])
        cell = deid.Cell("l.c", {"path": ["l", 1, "c"]}, "z")
        deid.store_cell("json", data, cell, "Q")
        self.assertEqual(data["l"][1]["c"], "Q")

    def test_sidecar_roundtrip_and_version(self):
        pol = deid.Policy.load("pseudonym")
        state = deid.RunState(policy=pol, entity_mapping={"PERSON": {"Jane": "<PERSON_1>"}}, date_offset_days=-3)
        with tempfile.TemporaryDirectory() as d:
            side = Path(d) / "map.json"
            deid.sidecar_write(side, state, "text", Path("in.md"), {"items": [{"start": 0, "end": 10, "entity_type": "PERSON", "text": "<PERSON_1>", "operator": "pseudonym"}]})
            data = deid.sidecar_read(side)
        self.assertEqual(data["version"], deid.SIDECAR_VERSION)
        self.assertEqual(data["date_offset_days"], -3)
        restored = deid.state_from_sidecar(data, pol)
        self.assertEqual(restored.entity_mapping["PERSON"]["Jane"], "<PERSON_1>")
        self.assertEqual(data["operators"]["PERSON"], {"op": "pseudonym", "format": "<{entity}_{n}>"})

    def test_restore_rebuilds_custom_policy_from_sidecar(self):
        """A custom policy YAML (not a preset) must restore even after the file is gone."""
        custom = deid.Policy.from_dict({"operators": {"DEFAULT": "replace", "PERSON": "pseudonym", "ID": "pseudonym",
                                                       "DATE_TIME": {"op": "date_shift", "days": 4}}}, name="my-policy")
        state = deid.RunState.start(custom)
        with tempfile.TemporaryDirectory() as d:
            side = Path(d) / "map.json"
            deid.sidecar_write(side, state, "text", Path("in.md"), {"items": []})
            data = deid.sidecar_read(side)
        rebuilt = deid.state_from_sidecar(data)
        self.assertEqual(rebuilt.policy.name, "my-policy")
        self.assertEqual({k: v.op for k, v in rebuilt.policy.operators.items()},
                         {"DEFAULT": "replace", "PERSON": "pseudonym", "ID": "pseudonym", "DATE_TIME": "date_shift"})
        self.assertEqual(rebuilt.date_offset_days, 4)
        reverse = rebuilt.operator_configs(reverse=True)
        self.assertNotIn("DEFAULT", reverse)  # never hand presidio's deanonymizer a `keep`
        self.assertEqual({k: v.operator_name for k, v in reverse.items()}, {"PERSON": "pseudonym", "ID": "pseudonym", "DATE_TIME": "date_shift"})

    def test_legacy_sidecar_without_operators(self):
        preset = deid.state_from_sidecar({"version": 1, "kind": "text", "policy": "pseudonym"})
        self.assertTrue(preset.policy.needs_sidecar)
        with self.assertRaises(deid.typer.Exit) as cm:
            deid.state_from_sidecar({"version": 1, "kind": "text", "policy": "gone.yaml"})
        self.assertEqual(cm.exception.exit_code, deid.EXIT_PARAMS)


@unittest.skipUnless(os.environ.get("DEID_LIVE"), "set DEID_LIVE=1 for the spaCy/Tesseract E2E")
class TestLiveEndToEnd(unittest.TestCase):
    """Real engines on the synthetic fixtures. Slow (first run downloads the spaCy model)."""

    def run_cli(self, *args: str):
        return subprocess.run(["uv", "run", str(SCRIPT), *args], capture_output=True, text=True)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_text_scan_pseudonym_restore_verify(self):
        r = self.run_cli("scan", str(FIXTURES / "note.md"), "--json")
        self.assertEqual(r.returncode, 1, r.stderr)
        found = {f["entity_type"] for f in json.loads(r.stdout)["findings"]}
        self.assertTrue({"PERSON", "EMAIL_ADDRESS", "TH_TNIN", "DATE_TIME"} <= found, found)
        out, side = self.out / "p.md", self.out / "map.json"
        self.assertEqual(self.run_cli("anonymize", str(FIXTURES / "note.md"), "-o", str(out), "--policy", "pseudonym", "--sidecar", str(side)).returncode, 0)
        self.assertNotIn("Jane Doe", out.read_text())
        self.assertEqual(self.run_cli("verify", str(out), "--policy", "pseudonym").returncode, 0)
        restored = self.out / "r.md"
        self.assertEqual(self.run_cli("restore", str(out), "-o", str(restored), "--sidecar", str(side)).returncode, 0)
        self.assertEqual(restored.read_text(), (FIXTURES / "note.md").read_text())

    def test_custom_policy_with_patterns_roundtrip(self):
        """SKILL.md's documented path: copy a preset, add patterns:, restore later — the policy file may be gone by then."""
        policy = self.out / "policy.yaml"
        policy.write_text(
            "operators:\n  DEFAULT: {op: pseudonym}\n  DATE_TIME: {op: date_shift}\n  ORGANIZATION: {op: keep}\n"
            "patterns:\n  - {name: hn, entity: ID, regex: '\\bHN\\s?\\d{6,10}\\b', score: 0.7}\n"
        )
        out, side, back = self.out / "p.md", self.out / "map.json", self.out / "r.md"
        r = self.run_cli("anonymize", str(FIXTURES / "note.md"), "-o", str(out), "--policy", str(policy), "--sidecar", str(side), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ID", json.loads(r.stdout)["by_entity"])
        self.assertNotIn("HN 12345678", out.read_text())
        policy.unlink()
        r = self.run_cli("restore", str(out), "-o", str(back), "--sidecar", str(side))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(back.read_text(), (FIXTURES / "note.md").read_text())

    def test_safe_harbor_verify_clean(self):
        out = self.out / "sh.md"
        self.assertEqual(self.run_cli("anonymize", str(FIXTURES / "note.md"), "-o", str(out), "--policy", "safe-harbor").returncode, 0)
        r = self.run_cli("verify", str(out), "--policy", "safe-harbor")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_csv_roundtrip(self):
        out, side, back = self.out / "p.csv", self.out / "map.json", self.out / "r.csv"
        r = self.run_cli("anonymize", str(FIXTURES / "patients.csv"), "-o", str(out), "--policy", "pseudonym", "--sidecar", str(side), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        typed = json.loads(r.stdout)["typed"]
        self.assertEqual(typed.get("hn"), "ID")
        self.assertEqual(typed.get("name"), "PERSON")
        self.assertEqual(self.run_cli("verify", str(out), "--policy", "pseudonym").returncode, 0)
        self.assertEqual(self.run_cli("restore", str(out), "-o", str(back), "--sidecar", str(side)).returncode, 0)
        self.assertEqual(list(csv.reader(back.open())), list(csv.reader((FIXTURES / "patients.csv").open())))

    def test_json_roundtrip(self):
        out, side, back = self.out / "p.json", self.out / "map.json", self.out / "r.json"
        self.assertEqual(self.run_cli("anonymize", str(FIXTURES / "record.json"), "-o", str(out), "--policy", "pseudonym", "--sidecar", str(side)).returncode, 0)
        self.assertNotIn("Jane Doe", out.read_text())
        self.assertEqual(self.run_cli("restore", str(out), "-o", str(back), "--sidecar", str(side)).returncode, 0)
        self.assertEqual(json.loads(back.read_text()), json.loads((FIXTURES / "record.json").read_text()))

    def test_png_scan_redact_verify(self):
        self.assertEqual(self.run_cli("scan", str(FIXTURES / "report.png")).returncode, 1)
        out = self.out / "red.png"
        self.assertEqual(self.run_cli("anonymize", str(FIXTURES / "report.png"), "-o", str(out)).returncode, 0)
        self.assertEqual(self.run_cli("verify", str(out)).returncode, 0)

    @unittest.skipUnless(os.environ.get("DEID_PRESIDIO_TESTDATA"), "set DEID_PRESIDIO_TESTDATA to presidio-image-redactor/tests/test_data")
    def test_dicom_scan_and_redact(self):
        dcm = Path(os.environ["DEID_PRESIDIO_TESTDATA"]) / "0_ORIGINAL.dcm"
        self.assertEqual(self.run_cli("scan", str(dcm)).returncode, 1)
        r = self.run_cli("anonymize", str(dcm), "-o", str(self.out / "dicom"), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.out / "dicom" / "0_ORIGINAL.dcm").exists())


if __name__ == "__main__":
    unittest.main()
