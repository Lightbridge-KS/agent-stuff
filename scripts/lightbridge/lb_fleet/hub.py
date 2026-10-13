"""Hub inventory selection, local Git observations and atomic receipts."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from lb_resolve import fleet_receipts_dir


FLEET_HEADER = """\
# ~/.lightbridge/fleet.toml — the hub's node inventory. Lives ONLY on the hub (this
# machine); a node never carries this file, which is what keeps a node from being able
# to address any other machine. `lb fleet status` reads it, `lb fleet sync NODE` acts on
# it; receipts land beside it in fleet/<node>.json. Spec: the fleet-sync skill, ADR 0004.
"""


SEED_BLOCK = """\
[hub]
root = "~/my_config"          # where the hub's own clones live (distance is computed here)

# One [repos.<name>] per repo every node mirrors at <root>/<name>. `apply` is the node's
# own idempotent install, run only when the repo moved (or with --reinstall); `verify`
# runs after a successful apply; `requires` names gitignored per-box files whose absence
# refuses the repo instead of running a doomed apply.
[repos.agent-instruction]
requires = [".device"]        # `cp .device.example .device` on the node, then edit
apply    = "make install"
verify   = "make check"

[repos.agent-stuff]
apply    = "uv run bin/install.py --all --force --prune"     # reconcile registries to profiles.toml
verify   = "uv run bin/validate.py && uv run bin/install.py --check"

[repos.agent-stuff-private]
apply    = "uv run ../agent-stuff/bin/install.py --root . --all --force --prune"

# One [nodes.<name>] per node — rename this example to your device. `ssh` is the alias
# in ~/.ssh/config; `repos` is the apply ORDER (agent-stuff before agent-stuff-private —
# the private install runs agent-stuff's installer).
[nodes.example-node]
ssh   = "example-node"
root  = "~/my_config"         # expanded on the node; defaults to [hub] root
repos = ["agent-instruction", "agent-stuff", "agent-stuff-private"]
"""


def repo_specs(fleet: dict, node: str, only: list[str] | None = None) -> list[dict]:
    """The node's repos as the node script wants them, in apply order.

    `only` narrows to a subset (validated by the caller); order stays the inventory's.
    """
    specs = []
    for name in fleet["nodes"][node]["repos"]:
        if only and name not in only:
            continue
        repo = fleet["repos"][name]
        specs.append({"name": name, **repo})
    return specs


def _git(repo_dir: Path, *args: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_dir), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except FileNotFoundError:
        return 127, "git: not found"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def hub_repo_dir(hub_root: str, name: str) -> Path:
    return Path(hub_root).expanduser() / name


def hub_fetch(repo_dir: Path) -> str | None:
    """Refresh the hub clone's `origin/main`; the error text, or None."""
    if not (repo_dir / ".git").exists():
        return f"hub clone missing: {repo_dir}"
    rc, out = _git(repo_dir, "fetch", "--quiet", "origin", "main")
    return None if rc == 0 else f"fetch failed ({out or rc})"


def distance(repo_dir: Path, node_head: str | None) -> dict:
    """How far `node_head` sits from the hub clone's `origin/main`.

    `{"origin_main": sha|None, "behind": int|None, "ahead": bool|None, "error": str|None}`.
    A node HEAD the hub clone does not know is reported as `ahead` (unknown commit): a
    replica of origin/main can only hold commits the hub has, so an unknown one means the
    node committed locally.
    """
    result: dict = {"origin_main": None, "behind": None, "ahead": None, "error": None}
    if not (repo_dir / ".git").exists():
        result["error"] = f"hub clone missing: {repo_dir}"
        return result
    rc, origin_main = _git(repo_dir, "rev-parse", "--verify", "--quiet", "origin/main")
    if rc != 0 or not origin_main:
        result["error"] = "no origin/main in the hub clone"
        return result
    result["origin_main"] = origin_main.strip()
    if not node_head:
        return result
    rc, _ = _git(repo_dir, "cat-file", "-e", f"{node_head}^{{commit}}")
    if rc != 0:
        result["ahead"] = (
            True  # unknown commit — the node has something the hub never saw
        )
        return result
    rc, _ = _git(
        repo_dir, "merge-base", "--is-ancestor", node_head, result["origin_main"]
    )
    result["ahead"] = rc != 0
    rc, count = _git(
        repo_dir, "rev-list", "--count", f"{node_head}..{result['origin_main']}"
    )
    result["behind"] = int(count) if rc == 0 and count.isdigit() else None
    return result


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def short(sha: str | None) -> str:
    return sha[:7] if sha else "-"


def receipt_path(fleet_path: Path, node: str) -> Path:
    return fleet_receipts_dir(fleet_path) / f"{node}.json"


def write_receipt(fleet_path: Path, node: str, data: dict) -> Path:
    """Atomically replace the node's receipt (tmp file + `os.replace`)."""
    path = receipt_path(fleet_path, node)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{node}.", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path
