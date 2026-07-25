"""Audit the projects tree for rot.

Four problem kinds, each with a message that names the repair (design §6-5, "errors that
teach"): `unreadable`, `missing-root`, `stale`, `key-mismatch`, plus `legacy` for a stray
pre-migration per-repo config found under a registered repo.

There is deliberately no `--fix`: the only safely automatable kind is `key-mismatch`, and
`stale` needs the multi-machine `relocate` / `not-on-this-machine` distinction that the
deferred sync design owns. `stale` teaches `lb mv` instead.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from lb_registry import registry_paths
from lb_resolve import CONFIG_NAME, LEGACY_CONFIG_REL, project_key


def doctor(state_dir: Path, registry: Path) -> list[dict]:
    """Audit the projects tree. Each problem: {kind, path, detail}."""
    problems: list[dict] = []

    for config in sorted(state_dir.glob(f"*/{CONFIG_NAME}")):
        try:
            data = tomllib.loads(config.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as exc:
            problems.append(
                {"kind": "unreadable", "path": str(config), "detail": str(exc)}
            )
            continue
        root = data.get("root")
        if not isinstance(root, str) or not root.strip():
            problems.append(
                {
                    "kind": "missing-root",
                    "path": str(config),
                    "detail": "no top-level `root` key — staleness undetectable; add root = \"/abs/path\"",
                }
            )
            continue
        root_path = Path(root).expanduser()
        if not root_path.is_dir():
            problems.append(
                {
                    "kind": "stale",
                    "path": str(config),
                    "detail": f"root {root_path} no longer exists — repo moved or deleted; "
                    f"moved: `mv {root_path} NEW` repairs everything; deleted: remove the folder",
                }
            )
            continue
        if project_key(root_path) != config.parent.name:
            problems.append(
                {
                    "kind": "key-mismatch",
                    "path": str(config),
                    "detail": f"folder key {config.parent.name!r} != key of root "
                    f"({project_key(root_path)!r}) — re-key the folder",
                }
            )

    for repo in registry_paths(registry):
        legacy = repo / LEGACY_CONFIG_REL
        if legacy.is_file():
            problems.append(
                {
                    "kind": "legacy",
                    "path": str(legacy),
                    "detail": "per-repo config is no longer read — migrate to "
                    f"{state_dir / project_key(repo) / CONFIG_NAME} and delete .lightbridge/",
                }
            )

    return problems
