"""Move/rename repair — `lb mv OLD NEW`.

Spec: `docs/lightbridge/lightbridge-mv.md` — mode detection, uniform prefix semantics,
collision rules, and the guard all live there.

**Plan / apply are separate.** `plan_mv` reads the world and decides everything without
touching it, so the same plan drives `--dry-run`, the confirmation display, `--json`, and
the execution. `apply_mv` performs exactly what the plan describes and nothing else. The
CLI handler owns only the guard, the display, and the exit code — which is what makes the
destructive path testable without a TTY.
"""

from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path

from lb_registry import load_registry, rename_registry_paths
from lb_resolve import CONFIG_NAME, project_key
from lb_tomledit import norm, rewrite_path, set_root


def _merge_conflicts(src: Path, dst: Path) -> list[str]:
    """Relative file paths that exist on both sides of a state merge (should be none —
    state filenames are timestamped)."""
    conflicts = []
    for item in sorted(src.rglob("*")):
        if item.is_file() and (dst / item.relative_to(src)).exists():
            conflicts.append(str(item.relative_to(src)))
    return conflicts


def _merge_move(src: Path, dst: Path) -> None:
    """Move `src`'s contents into the existing `dst` tree, then drop the empty `src`.

    Conflict-free by contract: `plan_mv` refuses the whole operation when
    `_merge_conflicts` finds anything.
    """
    for item in sorted(src.iterdir()):
        target = dst / item.name
        if item.is_dir() and target.is_dir():
            _merge_move(item, target)
        else:
            shutil.move(str(item), str(target))
    src.rmdir()


def plan_mv(old_raw: str, new_raw: str, state_dir: Path, registry: Path) -> dict:
    """The full mv plan — mode, blast radius, collisions — without changing anything.

    Powers `--dry-run`, the confirmation display, `--json`, and `apply_mv`.
    Blocking problems land in `plan["errors"]`; an empty list means safe to apply.
    """
    old = norm(old_raw)
    new = norm(new_raw)
    plan: dict = {
        "old": str(old),
        "new": str(new),
        "mode": None,
        "projects": [],
        "repos": {},
        "claude": [],
        "errors": [],
    }

    if str(old) == str(new):
        plan["errors"].append("OLD and NEW are the same path — nothing to do.")
        return plan
    old_exists, new_exists = old.exists(), new.exists()
    case_rename = old_exists and new_exists and old.samefile(new)
    if case_rename or (old_exists and not new_exists):
        plan["mode"] = "move"
        if not old.is_dir():
            plan["errors"].append(f"OLD is not a directory: {old}")
            return plan
    elif not old_exists and new_exists:
        plan["mode"] = "repair"
    elif old_exists:
        plan["errors"].append(
            f"both paths exist and are different directories:\n  OLD {old}\n  NEW {new}\n"
            "No heuristics — resolve by hand, then re-run."
        )
        return plan
    else:
        plan["errors"].append(
            f"neither path exists:\n  OLD {old}\n  NEW {new}\nCheck for a typo."
        )
        return plan

    claude_projects = Path("~/.claude/projects").expanduser()
    for config in sorted(state_dir.glob(f"*/{CONFIG_NAME}")):
        try:
            data = tomllib.loads(config.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError):
            continue  # doctor's problem (`unreadable`), not mv's
        root = data.get("root")
        if not isinstance(root, str) or not root.strip():
            continue  # doctor's `missing-root` — nothing to match on
        root_path = norm(root)
        if not root_path.is_relative_to(old):
            continue
        rel = root_path.relative_to(old)
        new_root = new if rel == Path(".") else new / rel
        old_key, new_key = config.parent.name, project_key(new_root)
        entry = {
            "old_key": old_key,
            "new_key": new_key,
            "old_root": str(root_path),
            "new_root": str(new_root),
            "collision": None,
        }
        target = state_dir / new_key
        # On a case-insensitive FS a case-only rename makes target *be* the old dir —
        # that's a plain rename, not a collision.
        same_dir = target.exists() and target.samefile(config.parent)
        if new_key != old_key and target.exists() and not same_dir:
            if (target / CONFIG_NAME).is_file():
                entry["collision"] = "config"
                plan["errors"].append(
                    f"{target / CONFIG_NAME} already exists — two configs claim "
                    f"{new_root}.\nDiff it against {config}, delete one, then re-run."
                )
            else:
                entry["collision"] = "state"
                conflicts = _merge_conflicts(config.parent, target)
                if conflicts:
                    plan["errors"].append(
                        f"state merge {old_key} → {new_key} would overwrite: "
                        f"{', '.join(conflicts)}\nResolve by hand, then re-run."
                    )
        if (claude_projects / old_key).is_dir():
            plan["claude"].append({"old_key": old_key, "new_key": new_key})
        plan["projects"].append(entry)

    repos, _error = load_registry(registry)
    for name, raw in sorted((repos or {}).items()):
        new_raw_value = rewrite_path(raw, old, new)
        if new_raw_value is not None and new_raw_value != raw:
            plan["repos"][name] = {"old": raw, "new": new_raw_value}

    if not plan["projects"] and not plan["repos"]:
        done = state_dir / project_key(new) / CONFIG_NAME
        if plan["mode"] == "repair" and done.is_file():
            try:
                data = tomllib.loads(done.read_text(encoding="utf-8"))
            except (tomllib.TOMLDecodeError, OSError):
                data = {}
            root = data.get("root")
            if isinstance(root, str) and norm(root) == new:
                plan["mode"] = "noop"  # verified complete — the idempotent re-run
                return plan
        plan["errors"].append(
            f"nothing in lightbridge references {old} — no project config, no registry "
            "entry.\nA typo? For an untracked repo, plain `mv` is all you need."
        )
    return plan


def apply_mv(plan: dict, state: Path, registry: Path) -> None:
    """Execute exactly what `plan` describes: the filesystem move, then the bookkeeping.

    Caller guarantees `plan["errors"]` is empty and the mode is `move` or `repair` (a
    `noop` plan has nothing to do). Never writes outside `~/.lightbridge` except the
    requested move itself; other harnesses' path-keyed state is reported by the caller
    from `plan["claude"]`, never touched.
    """
    if plan["mode"] == "move":
        old_path, new_path = Path(plan["old"]), Path(plan["new"])
        new_path.parent.mkdir(parents=True, exist_ok=True)
        if new_path.exists() and old_path.samefile(new_path):
            os.rename(old_path, new_path)  # case-only rename (case-insensitive APFS)
        else:
            shutil.move(str(old_path), str(new_path))

    for project in plan["projects"]:
        old_dir, new_dir = state / project["old_key"], state / project["new_key"]
        if project["old_key"] != project["new_key"]:
            if new_dir.exists() and new_dir.samefile(old_dir):
                os.rename(old_dir, new_dir)  # case-only re-key on a case-insensitive FS
            elif new_dir.exists():
                shutil.move(str(old_dir / CONFIG_NAME), str(new_dir / CONFIG_NAME))
                _merge_move(old_dir, new_dir)
            else:
                old_dir.rename(new_dir)
        config = new_dir / CONFIG_NAME
        config.write_text(
            set_root(config.read_text(encoding="utf-8"), Path(project["new_root"])),
            encoding="utf-8",
        )

    if plan["repos"] and registry.is_file():
        text, _changed = rename_registry_paths(
            registry.read_text(encoding="utf-8"), Path(plan["old"]), Path(plan["new"])
        )
        registry.write_text(text, encoding="utf-8")
