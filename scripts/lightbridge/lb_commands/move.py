"""Move command confirmation and presentation; planning and mutation remain in lb_mv."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from lb_mv import apply_mv, plan_mv
from lb_resolve import DEFAULT_REGISTRY, default_state_dir
from lb_style import row

# ── mv ──────────────────────────────────────────────────────────────────────


def _default_ask(prompt: str) -> bool:
    """The interactive confirmation — swapped out by tests via `cmd_mv(ask=...)`."""
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except EOFError:
        return False


def _print_mv_plan(plan: dict) -> None:
    """The blast radius, shown before anything changes (and by `--dry-run`)."""
    verb = "move + repair" if plan["mode"] == "move" else "repair (already moved)"
    print(row("plan", f"{verb}: {plan['old']} → {plan['new']}"))
    print(
        row(
            "affects",
            f"{len(plan['projects'])} project(s) · {len(plan['repos'])} registry entry(ies)",
        )
    )
    for project in plan["projects"]:
        merge = (
            "  (merge into existing state)" if project["collision"] == "state" else ""
        )
        print(row("key", f"{project['old_key']}  →  {project['new_key']}{merge}"))
    for name, change in plan["repos"].items():
        print(row("repos", f"{name}: {change['old']} → {change['new']}"))


def cmd_mv(
    old_raw: str,
    new_raw: str,
    *,
    yes: bool,
    dry_run: bool,
    json_out: bool,
    state_dir: Path | None = None,
    registry_file: str = DEFAULT_REGISTRY,
    ask=None,
) -> int:
    state = (state_dir or default_state_dir()).expanduser()
    registry = Path(registry_file).expanduser()
    plan = plan_mv(old_raw, new_raw, state, registry)

    if plan["errors"]:
        print("\n".join(plan["errors"]), file=sys.stderr)
        return 1
    if plan["mode"] == "noop":
        if json_out:
            print(json.dumps({**plan, "applied": False}, indent=2))
        else:
            print(
                row(
                    "unchanged",
                    f"already consistent — {len(plan['settled'])} reference(s) under "
                    f"{plan['new']} are keyed to it",
                )
            )
        return 0
    if not json_out:
        _print_mv_plan(plan)
    if dry_run:
        if json_out:
            print(json.dumps({**plan, "applied": False}, indent=2))
        else:
            print(row("dry-run", "nothing changed"))
        return 0

    # The guard (design Decision 2): a human at a TTY confirms; everything else
    # needs --yes, which is reserved for explicitly human-instructed moves.
    if not yes:
        if ask is None and not sys.stdin.isatty():
            print(
                "refused — this changes the filesystem and needs confirmation, but stdin "
                "is not a TTY.\nRe-run with --yes to apply. Agents: pass --yes only when "
                "the human explicitly instructed this move.",
                file=sys.stderr,
            )
            return 1
        if not (ask or _default_ask)("proceed? [y/N] "):
            print("aborted — nothing changed.", file=sys.stderr)
            return 1

    apply_mv(plan, state, registry)

    for note in plan["claude"]:
        print(
            f"note: ~/.claude/projects/{note['old_key']} exists (Claude Code session "
            f"state; its new key would be {note['new_key']}) — not touched, migrate it "
            "deliberately if wanted.",
            file=sys.stderr,
        )

    if json_out:
        print(json.dumps({**plan, "applied": True}, indent=2))
        return 0
    print(
        row(
            "moved" if plan["mode"] == "move" else "repaired",
            f"{plan['old']} → {plan['new']}",
        )
    )
    print(
        row(
            "rekeyed",
            f"{len(plan['projects'])} project(s) · {len(plan['repos'])} registry entry(ies)",
        )
    )
    return 0
