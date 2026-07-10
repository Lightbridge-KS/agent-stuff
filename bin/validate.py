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
  * every subagent (`plugins/<domain>/agents/<name>.md`) has frontmatter whose
    `name` matches the filename stem, a non-empty `description`, a known `model`
    value if pinned, no collision with Claude Code built-in agents or with any
    skill's `<domain>/<name>` key, and a unique name across domains (the
    installer flattens all subagents into one directory),
  * every `scripts/<tool>/` has a `README.md`,
  * every `hooks/<hook>/` has a `README.md` and a well-formed `hook.toml`,
  * no skill/subagent markdown contains committed tool-call artifacts (stray `</invoke>` etc.).

This is the machine-checkable half of the contract; human rules live in CLAUDE.md.

    uv run bin/validate.py

Exits non-zero (and prints every problem it found) if anything is malformed.
"""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_ROOT = REPO_ROOT / "plugins"
SCRIPTS_ROOT = REPO_ROOT / "scripts"
HOOKS_ROOT = REPO_ROOT / "hooks"
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"

# Fragments of agent tool-call syntax that occasionally leak into committed files;
# kept narrow so skills may still use ordinary XML-ish tags in examples.
TOOL_CALL_ARTIFACTS = (
    "</content>",
    "</invoke>",
    "<function_calls>",
    "</function_calls>",
    "<function_results>",
)

# Claude Code's built-in subagent types (lowercased): a custom subagent shadowing
# one of these would silently win or lose depending on scope — forbid outright.
CLAUDE_BUILTIN_AGENTS = {
    "claude",
    "claude-code-guide",
    "explore",
    "general-purpose",
    "plan",
    "statusline-setup",
}

# Legal at user level but SILENTLY IGNORED when the same file ships through the
# plugin-marketplace channel — warn so a dual-channel divergence stays visible.
PLUGIN_IGNORED_AGENT_FIELDS = ("hooks", "mcpServers", "permissionMode")

SUBAGENT_MODEL_ALIASES = {"opus", "sonnet", "haiku", "fable", "inherit"}


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

    for md in sorted(path.parent.rglob("*.md")):
        body = md.read_text(encoding="utf-8")
        for tag in TOOL_CALL_ARTIFACTS:
            if tag in body:
                errors.append(
                    f"{md.relative_to(REPO_ROOT)}: contains tool-call artifact '{tag}'"
                )

    return errors


def validate_subagent(path: Path) -> list[str]:
    """Return error strings (empty == valid) for one subagent .md, plus stderr warnings."""
    rel = path.relative_to(REPO_ROOT)
    stem = path.stem
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
    else:
        if name != stem:
            errors.append(f"{rel}: name '{name}' must match filename stem '{stem}'")
        if name.lower() in CLAUDE_BUILTIN_AGENTS:
            errors.append(f"{rel}: name '{name}' collides with a Claude Code built-in agent")

    if not non_empty_str(data.get("description")):
        errors.append(f"{rel}: missing description")

    model = data.get("model")
    if model is not None and not (
        isinstance(model, str)
        and (model in SUBAGENT_MODEL_ALIASES or model.startswith("claude-"))
    ):
        errors.append(
            f"{rel}: model '{model}' is not a known alias "
            f"({', '.join(sorted(SUBAGENT_MODEL_ALIASES))}) or a claude-* model id"
        )

    for field in PLUGIN_IGNORED_AGENT_FIELDS:
        if field in data:
            print(
                f"warning: {rel}: '{field}' is silently ignored when this agent "
                "ships via the plugin marketplace (works only user-level)",
                file=sys.stderr,
            )

    metadata = data.get("metadata")
    version = metadata.get("version") if isinstance(metadata, dict) else None
    if not version:
        print(f"warning: {rel}: no metadata.version (recommended)", file=sys.stderr)

    body = path.read_text(encoding="utf-8")
    for tag in TOOL_CALL_ARTIFACTS:
        if tag in body:
            errors.append(f"{rel}: contains tool-call artifact '{tag}'")

    return errors


def validate_subagent_names(agent_files: list[Path], skill_files: list[Path]) -> list[str]:
    """Cross-file checks: unique subagent names, no `<domain>/<name>` clash with skills."""
    errors: list[str] = []

    by_stem: dict[str, list[Path]] = {}
    for path in agent_files:
        by_stem.setdefault(path.stem, []).append(path)
    for stem, paths in sorted(by_stem.items()):
        if len(paths) > 1:
            rels = ", ".join(str(p.relative_to(REPO_ROOT)) for p in paths)
            errors.append(
                f"subagent name '{stem}' is defined more than once ({rels}); "
                "the installer flattens all subagents into one directory"
            )

    skill_keys = {
        f"{p.parent.parent.parent.name}/{p.parent.name}" for p in skill_files
    }
    for path in agent_files:
        key = f"{path.parent.parent.name}/{path.stem}"
        if key in skill_keys:
            errors.append(
                f"{path.relative_to(REPO_ROOT)}: '{key}' collides with a skill of "
                "the same name in the same domain (shared install address space)"
            )

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


def validate_hook_toml(hook_dir: Path) -> list[str]:
    """Validate one hook's `hook.toml` descriptor (the agent-neutral registration source)."""
    rel = (hook_dir / "hook.toml").relative_to(REPO_ROOT)
    descriptor_path = hook_dir / "hook.toml"
    if not descriptor_path.is_file():
        return []  # presence is enforced by validate_content_dir; nothing to parse here

    try:
        data = tomllib.loads(descriptor_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return [f"{rel}: invalid TOML: {exc}"]

    errors: list[str] = []
    if not non_empty_str(data.get("event")):
        errors.append(f"{rel}: missing event")
    if not non_empty_str(data.get("command")):
        errors.append(f"{rel}: missing command")
    elif not (hook_dir / data["command"]).is_file():
        errors.append(f"{rel}: command '{data['command']}' is not a file in {hook_dir.name}/")
    elif not os.access(hook_dir / data["command"], os.X_OK):
        # Agents execute the registered command directly via /bin/sh; without +x the
        # shebang never engages and every session start fails with "Permission denied".
        errors.append(
            f"{rel}: command '{data['command']}' is not executable — chmod +x it"
        )

    for key in ("matcher", "statusMessage"):
        if key in data and not isinstance(data[key], str):
            errors.append(f"{rel}: {key} must be a string")

    return errors


def main() -> int:
    skill_files = sorted(PLUGINS_ROOT.glob("*/skills/*/SKILL.md"))
    if not skill_files:
        print("No plugins/*/skills/*/SKILL.md files found.", file=sys.stderr)
        return 1

    agent_files = sorted(PLUGINS_ROOT.glob("*/agents/*.md"))

    errors = [err for path in skill_files for err in validate_skill(path)]
    errors += [err for path in agent_files for err in validate_subagent(path)]
    errors += validate_subagent_names(agent_files, skill_files)
    errors += validate_manifests()
    errors += validate_content_dir(SCRIPTS_ROOT, ["README.md"])
    errors += validate_content_dir(HOOKS_ROOT, ["README.md", "hook.toml"])
    if HOOKS_ROOT.is_dir():
        for hook_dir in sorted(HOOKS_ROOT.iterdir()):
            if hook_dir.is_dir() and not hook_dir.name.startswith((".", "_")):
                errors += validate_hook_toml(hook_dir)

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    print(
        f"validated {len(skill_files)} skills, {len(agent_files)} subagents, "
        "plugin manifests, and scripts/hooks contracts"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
