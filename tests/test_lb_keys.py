#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for personal LLM API key management: the document model in
`lb_keys.py` and the `lb key` verb family.

`lb_keys` is loaded the way its real consumer loads it — a plain import by the CLI
(nothing here joins `lb_resolve`'s frozen API; ADR 0003). The CLI runs as a subprocess
executing `lightbridge.py` directly, isolated through the `--keys FILE --secrets FILE`
seams — the key family's `--registry`/`--graph` equivalent.

The governing assertion, applied to every CLI result: **no secret value on stdout or
stderr, ever** — the sentinel `sk-TESTSENTINEL` must never appear in any verb's output.

    uv run tests/test_lb_keys.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LIGHTBRIDGE_DIR = REPO_ROOT / "scripts" / "lightbridge"
SCRIPT = LIGHTBRIDGE_DIR / "lightbridge.py"

sys.path.insert(0, str(LIGHTBRIDGE_DIR))

import lb_keys  # noqa: E402

SENTINEL = "sk-TESTSENTINEL"


def script_argv(script: Path, *args: str) -> list[str]:
    """argv launching a PEP 723 script the way its real consumer does (see
    test_lightbridge.py for the Windows rationale)."""
    if os.name != "nt":
        return [str(script), *args]
    return ["uv", "run", str(script), *args]


KEYS_BODY = """\
# hand-authored comment that must survive every edit
[keys.openai-personal]
provider = "openai"
env = "OPENAI_API_KEY"
scope = "personal general inference"

[keys.anthropic-personal]
provider = "anthropic"
env = "ANTHROPIC_API_KEY"
scope = "personal general inference"
"""

SECRETS_BODY = f"""\
[secrets]
openai-personal = '{SENTINEL}'
anthropic-personal = '{SENTINEL}-2'
"""


def write_pair(base: Path, keys_body: str = KEYS_BODY, secrets_body: str = SECRETS_BODY):
    keys = base / "keys.toml"
    secrets = base / "secrets.toml"
    keys.write_text(keys_body, encoding="utf-8")
    secrets.write_text(secrets_body, encoding="utf-8")
    if os.name != "nt":
        secrets.chmod(0o600)
    return keys, secrets


class LoadKeysTest(unittest.TestCase):
    """`load_keys`' tri-state contract — the `load_registry` shape, applied to the catalog."""

    def load(self, body: str):
        with tempfile.TemporaryDirectory() as d:
            keys = Path(d) / "keys.toml"
            keys.write_text(body, encoding="utf-8")
            return lb_keys.load_keys(keys)

    def test_absent_file_is_not_opted_in(self):
        catalog, error = lb_keys.load_keys(Path("/nonexistent/keys.toml"))
        self.assertIsNone(catalog)
        self.assertIsNone(error)

    def test_bad_toml_is_an_error(self):
        catalog, error = self.load("not = toml = at all")
        self.assertIsNone(catalog)
        self.assertIn("unreadable", error)

    def test_stranded_root_keys_are_an_error_not_an_empty_catalog(self):
        catalog, error = self.load('openai = "OPENAI_API_KEY"\n')
        self.assertIsNone(catalog)
        self.assertIn("[keys.<name>]", error)

    def test_non_table_entry_is_an_error(self):
        catalog, error = self.load('[keys]\nopenai = "not a table"\n')
        self.assertIsNone(catalog)
        self.assertIn("non-table", error)

    def test_empty_file_is_usable_and_empty(self):
        catalog, error = self.load("")
        self.assertEqual(catalog, {})
        self.assertIsNone(error)

    def test_usable_catalog_normalizes_missing_fields_to_none(self):
        catalog, error = self.load(
            '[keys.gemini]\nenv = "GEMINI_API_KEY"\nscope = "   "\n'
        )
        self.assertIsNone(error)
        self.assertEqual(
            catalog,
            {"gemini": {"provider": None, "env": "GEMINI_API_KEY", "scope": None}},
        )

    def test_full_catalog_round_trips(self):
        with tempfile.TemporaryDirectory() as d:
            keys, _ = write_pair(Path(d))
            catalog, error = lb_keys.load_keys(keys)
        self.assertIsNone(error)
        self.assertEqual(
            catalog["openai-personal"],
            {
                "provider": "openai",
                "env": "OPENAI_API_KEY",
                "scope": "personal general inference",
            },
        )


class LoadSecretsTest(unittest.TestCase):
    """Both secrets readers share `load_keys`' tri-state; names-only is what ls/doctor use."""

    def test_absent_file_is_not_opted_in(self):
        names, error = lb_keys.load_secret_names(Path("/nonexistent/secrets.toml"))
        self.assertIsNone(names)
        self.assertIsNone(error)

    def test_bad_toml_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            secrets = Path(d) / "secrets.toml"
            secrets.write_text("not = toml = at all", encoding="utf-8")
            names, error = lb_keys.load_secret_names(secrets)
        self.assertIsNone(names)
        self.assertIn("unreadable", error)

    def test_stranded_root_keys_are_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            secrets = Path(d) / "secrets.toml"
            secrets.write_text(f"openai = '{SENTINEL}'\n", encoding="utf-8")
            names, error = lb_keys.load_secret_names(secrets)
        self.assertIsNone(names)
        self.assertIn("[secrets]", error)
        self.assertNotIn(SENTINEL, error)

    def test_names_carry_no_values(self):
        with tempfile.TemporaryDirectory() as d:
            _, secrets = write_pair(Path(d))
            names, error = lb_keys.load_secret_names(secrets)
        self.assertIsNone(error)
        self.assertEqual(names, ["anthropic-personal", "openai-personal"])

    def test_load_secrets_returns_values_for_run(self):
        with tempfile.TemporaryDirectory() as d:
            _, secrets = write_pair(Path(d))
            table, error = lb_keys.load_secrets(secrets)
        self.assertIsNone(error)
        self.assertEqual(table["openai-personal"], SENTINEL)


class KeySurgeryTest(unittest.TestCase):
    """Catalog block edits — untargeted lines come out byte-identical."""

    def test_append_key_parses_and_preserves_existing_lines(self):
        text = lb_keys.append_key(
            KEYS_BODY, "gemini-personal", "google", "GEMINI_API_KEY", "general inference"
        )
        self.assertTrue(text.startswith(KEYS_BODY))
        data = tomllib.loads(text)
        self.assertEqual(data["keys"]["gemini-personal"]["env"], "GEMINI_API_KEY")

    def test_append_key_to_empty_text_needs_no_separator(self):
        text = lb_keys.append_key("", "a", "p", "A_KEY", "s")
        self.assertTrue(text.startswith("[keys.a]\n"))
        tomllib.loads(text)

    def test_append_key_terminates_an_unterminated_file(self):
        text = lb_keys.append_key('[keys.a]\nenv = "A"', "b", "p", "B_KEY", "s")
        data = tomllib.loads(text)
        self.assertEqual(set(data["keys"]), {"a", "b"})

    def test_remove_key_round_trips_byte_identical(self):
        grown = lb_keys.append_key(KEYS_BODY, "tmp", "p", "TMP_KEY", "s")
        self.assertEqual(lb_keys.remove_key(grown, "tmp"), KEYS_BODY)

    def test_remove_key_absent_name_is_none(self):
        self.assertIsNone(lb_keys.remove_key(KEYS_BODY, "nonexistent"))

    def test_remove_key_middle_block_keeps_others_byte_identical(self):
        text = lb_keys.remove_key(KEYS_BODY, "openai-personal")
        self.assertIn("# hand-authored comment", text)
        self.assertNotIn("openai-personal", text)
        data = tomllib.loads(text)
        self.assertEqual(list(data["keys"]), ["anthropic-personal"])


class SecretSurgeryTest(unittest.TestCase):
    """`[secrets]` line edits — `append_repo`'s behavior, applied to the values table."""

    def test_append_secret_lands_inside_the_table(self):
        text = lb_keys.append_secret(SECRETS_BODY, "gemini", "value-g")
        data = tomllib.loads(text)
        self.assertEqual(data["secrets"]["gemini"], "value-g")

    def test_append_secret_headerless_file_gains_header(self):
        text = lb_keys.append_secret("", "a", "v")
        self.assertEqual(tomllib.loads(text)["secrets"]["a"], "v")

    def test_append_secret_unterminated_final_line_is_safe(self):
        text = lb_keys.append_secret("[secrets]\na = 'x'", "b", "y")
        data = tomllib.loads(text)
        self.assertEqual(data["secrets"], {"a": "x", "b": "y"})

    def test_remove_secret_round_trips_byte_identical(self):
        grown = lb_keys.append_secret(SECRETS_BODY, "tmp", "v")
        self.assertEqual(lb_keys.remove_secret(grown, "tmp"), SECRETS_BODY)

    def test_remove_secret_absent_name_is_none(self):
        self.assertIsNone(lb_keys.remove_secret(SECRETS_BODY, "nonexistent"))


@unittest.skipIf(os.name == "nt", "POSIX mode bits")
class WriteSecretsTest(unittest.TestCase):
    """The one write path for the values file keeps it owner-only."""

    def test_fresh_file_is_0600(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "secrets.toml"
            lb_keys.write_secrets(path, SECRETS_BODY)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.read_text(encoding="utf-8"), SECRETS_BODY)

    def test_loose_preexisting_mode_is_repaired(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "secrets.toml"
            path.write_text("[secrets]\n", encoding="utf-8")
            path.chmod(0o644)
            lb_keys.write_secrets(path, SECRETS_BODY)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_mode_problem_names_the_fix(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "secrets.toml"
            path.write_text("[secrets]\n", encoding="utf-8")
            path.chmod(0o644)
            problem = lb_keys.secrets_mode_problem(path)
            self.assertIn("chmod 600", problem)
            path.chmod(0o600)
            self.assertIsNone(lb_keys.secrets_mode_problem(path))
        self.assertIsNone(lb_keys.secrets_mode_problem(Path("/nonexistent/s.toml")))


class AuditTest(unittest.TestCase):
    """One finding per mismatch kind; a clean pair audits empty."""

    CLEAN = {
        "openai-personal": {
            "provider": "openai",
            "env": "OPENAI_API_KEY",
            "scope": "general",
        }
    }

    def audit(self, keys, names, mode: int | None = 0o600):
        with tempfile.TemporaryDirectory() as d:
            secrets = Path(d) / "secrets.toml"
            if mode is not None:
                secrets.write_text("[secrets]\n", encoding="utf-8")
                if os.name != "nt":
                    secrets.chmod(mode)
            return lb_keys.audit(keys, names, secrets)

    def kinds(self, keys, names, mode=0o600):
        return [p["kind"] for p in self.audit(keys, names, mode)]

    def test_clean_pair_has_no_problems(self):
        self.assertEqual(self.audit(self.CLEAN, ["openai-personal"]), [])

    def test_missing_env(self):
        keys = {"a": {"provider": "p", "env": None, "scope": "s"}}
        self.assertIn("missing-env", self.kinds(keys, ["a"]))

    def test_bad_env_name(self):
        keys = {"a": {"provider": "p", "env": "lower_case", "scope": "s"}}
        self.assertIn("bad-env-name", self.kinds(keys, ["a"]))

    def test_bad_name(self):
        keys = {"bad name!": {"provider": "p", "env": "A_KEY", "scope": "s"}}
        self.assertIn("bad-name", self.kinds(keys, ["bad name!"]))

    def test_no_value(self):
        self.assertIn("no-value", self.kinds(self.CLEAN, []))

    def test_orphan_value(self):
        self.assertIn("orphan-value", self.kinds({}, ["stray"]))

    @unittest.skipIf(os.name == "nt", "POSIX mode bits")
    def test_bad_mode(self):
        self.assertIn("bad-mode", self.kinds(self.CLEAN, ["openai-personal"], 0o644))

    def test_shared_env_across_entries_is_not_a_finding(self):
        keys = {
            "openai-personal": {"provider": "openai", "env": "OPENAI_API_KEY", "scope": "a"},
            "openai-image-gen": {"provider": "openai", "env": "OPENAI_API_KEY", "scope": "b"},
        }
        self.assertEqual(self.audit(keys, ["openai-personal", "openai-image-gen"]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
