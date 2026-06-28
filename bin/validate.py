#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Validate the repo contract: skills, plugin/marketplace manifests, scripts, hooks.

Source of truth for skills is `plugins/<domain>/skills/<name>/SKILL.md`. A folder
under a plugin's `skills/` is a skill iff it contains `SKILL.md`, whose YAML
frontmatter must hold a non-empty `name` (matching the folder) and `description`.
On top of that, this validator checks:

  * `.claude-plugin/marketplace.json` is well-formed,
  * every `plugins[].source` resolves to a dir with `.claude-plugin/plugin.json`,
  * each `plugin.json` is valid JSON whose `name` matches its marketplace entry,
  * every `scripts/<tool>/` has a `README.md`,
  * every `hooks/<hook>/` has a `README.md` and a `hook.json.snippet`.

This is the machine-checkable half of the contract; human rules live in CLAUDE.md.

    uv run bin/validate.py

Exits non-zero (and prints every problem it found) if anything is malformed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_ROOT = REPO_ROOT / "plugins"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
HOOKS_ROOT = REPO_ROOT / "hooks"
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def parse_frontmatter(text: str) -> dict:
    """Extract and parse the leading `---`-delimited YAML block. Raises on malformed input."""
    if not text.startswith("---\n"):
        raise ValueError("missing YAML frontmatter")

    close = text.find("\n---", 4)
    if close == -1:
        raise ValueError("unterminated YAML frontmatter")

    data = yaml.safe_load(text[4:close]) or {}
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a mapping")
    return data


def non_empty_str(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_skill(path: Path) -> list[str]:
    """Return a list of error strings (empty == valid) for one SKILL.md, plus stderr warnings."""
    rel = path.relative_to(REPO_ROOT)
    folder = path.parent.name
    errors: list[str] = []

    try:
        data = parse_frontmatter(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"{rel}: invalid YAML: {exc}"]
    except ValueError as exc:
        return [f"{rel}: {exc}"]

    name = data.get("name")
    if not non_empty_str(name):
        errors.append(f"{rel}: missing name")
    elif name != folder:
        errors.append(f"{rel}: name '{name}' must match folder name '{folder}'")

    if not non_empty_str(data.get("description")):
        errors.append(f"{rel}: missing description")

    # metadata.version is recommended but not required — warn only.
    metadata = data.get("metadata")
    version = metadata.get("version") if isinstance(metadata, dict) else None
    if not version:
        print(f"warning: {rel}: no metadata.version (recommended)", file=sys.stderr)

    return errors


def validate_manifests() -> list[str]:
    """Validate marketplace.json and every referenced plugin.json."""
    rel_market = MARKETPLACE.relative_to(REPO_ROOT)
    if not MARKETPLACE.is_file():
        return [f"{rel_market}: missing"]

    try:
        market = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{rel_market}: invalid JSON: {exc}"]

    errors: list[str] = []
    if not non_empty_str(market.get("name")):
        errors.append(f"{rel_market}: missing name")

    plugins = market.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        return errors + [f"{rel_market}: plugins must be a non-empty list"]

    for entry in plugins:
        name = entry.get("name") if isinstance(entry, dict) else None
        source = entry.get("source") if isinstance(entry, dict) else None
        if not non_empty_str(name):
            errors.append(f"{rel_market}: a plugin entry is missing name")
            continue
        if not non_empty_str(source):
            errors.append(f"{rel_market}: plugin '{name}' is missing a string source")
            continue

        plugin_dir = (REPO_ROOT / source).resolve()
        manifest = plugin_dir / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            errors.append(f"{rel_market}: plugin '{name}' source has no .claude-plugin/plugin.json")
            continue

        rel_manifest = manifest.relative_to(REPO_ROOT)
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{rel_manifest}: invalid JSON: {exc}")
            continue
        if data.get("name") != name:
            errors.append(
                f"{rel_manifest}: name '{data.get('name')}' must match marketplace entry '{name}'"
            )

    return errors


def validate_content_dir(root: Path, required: list[str]) -> list[str]:
    """Each immediate subfolder of `root` must contain every file in `required`."""
    if not root.is_dir():
        return []
    errors: list[str] = []
    for item in sorted(root.iterdir()):
        if not item.is_dir() or item.name.startswith((".", "_")):
            continue
        for fname in required:
            if not (item / fname).is_file():
                rel = item.relative_to(REPO_ROOT)
                errors.append(f"{rel}: missing {fname}")
    return errors


def main() -> int:
    skill_files = sorted(PLUGINS_ROOT.glob("*/skills/*/SKILL.md"))
    if not skill_files:
        print("No plugins/*/skills/*/SKILL.md files found.", file=sys.stderr)
        return 1

    errors = [err for path in skill_files for err in validate_skill(path)]
    errors += validate_manifests()
    errors += validate_content_dir(SCRIPTS_ROOT, ["README.md"])
    errors += validate_content_dir(HOOKS_ROOT, ["README.md", "hook.json.snippet"])

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(
        f"validated {len(skill_files)} skills, plugin manifests, "
        "and scripts/hooks contracts"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
