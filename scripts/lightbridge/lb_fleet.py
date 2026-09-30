"""The fleet document + the hub-side mechanics of `lb fleet` (ADR 0004).

Hub-and-spoke: **GitHub is the source of truth, this machine (the hub) is the only
initiator, nodes are pull-only replicas.** The hub never ships bytes. It renders one
self-contained Python script — the node's spec embedded as JSON — and streams it over
`ssh <alias> python3 -`. The node inspects its clones, pulls `--ff-only` from
`origin/main`, runs each repo's own idempotent install, and prints exactly one JSON
report line. A node that has diverged (not on `main`, dirty, ahead, missing a required
per-box file) is **refused and named, never stashed** — its edits must travel
branch → push → PR.

The inventory, `~/.lightbridge/fleet.toml`, exists **only on the hub**; that absence is
what makes a node structurally unable to address any other machine. Readers
(`load_fleet`, `load_receipt`, `fleet_receipts_dir`, `DEFAULT_FLEET`) live in
`lb_resolve` because the `fleet-inject` SessionStart hook path-loads them; everything
here is CLI-side (plain `import` from the entrypoint).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from lb_resolve import DEFAULT_FLEET, fleet_receipts_dir, load_receipt  # noqa: F401

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
apply    = "uv run bin/install.py --all --force"
verify   = "uv run bin/validate.py"

[repos.agent-stuff-private]
apply    = "uv run ../agent-stuff/bin/install.py --root . --all --force"

# One [nodes.<name>] per node — rename this example to your device. `ssh` is the alias
# in ~/.ssh/config; `repos` is the apply ORDER (agent-stuff before agent-stuff-private —
# the private install runs agent-stuff's installer).
[nodes.example-node]
ssh   = "example-node"
root  = "~/my_config"         # expanded on the node; defaults to [hub] root
repos = ["agent-instruction", "agent-stuff", "agent-stuff-private"]
"""

REPORT_MARK = "LB_FLEET_REPORT"
REGISTRIES = ("~/.claude/skills", "~/.codex/skills")
SSH_OPTS = ("-o", "BatchMode=yes", "-o", "ConnectTimeout=8")
SSH_OFFLINE = 255  # ssh's own exit code when it never reached a shell
APPLY_TIMEOUT = 600  # seconds per apply/verify command on the node
SESSION_TIMEOUT = 1800  # seconds for the whole ssh session

# The node-side program. Deliberately conservative Python (3.8+ syntax, stdlib only) —
# it runs under whatever `python3` a node's login shell finds. Two placeholders are
# substituted by `render_node_script`; everything else is literal.
NODE_SCRIPT = r'''
import json, os, signal, socket, subprocess, sys

CONFIG = json.loads(__CONFIG_JSON__)
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0")


def run(argv, cwd=None, timeout=120):
    """(rc, output). The whole process group dies on timeout (make -> quarto too); rc 124."""
    try:
        proc = subprocess.Popen(
            argv, cwd=cwd, env=ENV, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
        )
    except OSError as exc:
        return 127, str(exc)
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        out, _ = proc.communicate()
        return 124, out.decode("utf-8", "replace") + "\n[killed: timeout after %ss]" % timeout
    return proc.returncode, out.decode("utf-8", "replace")


def git(repo, *args, **kw):
    return run(["git", "-C", repo] + list(args), timeout=kw.get("timeout", 120))


def tail(text, lines=20, chars=2000):
    kept = text.strip().splitlines()[-lines:]
    return "\n".join(kept)[-chars:]


def inspect(repo_dir, spec):
    _, branch = git(repo_dir, "rev-parse", "--abbrev-ref", "HEAD")
    _, head = git(repo_dir, "rev-parse", "HEAD")
    _, porcelain = git(repo_dir, "status", "--porcelain")
    return {
        "branch": branch.strip(),
        "head": head.strip(),
        "dirty": [line for line in porcelain.splitlines() if line.strip()],
        "missing_requires": [
            f for f in spec.get("requires", []) if not os.path.exists(os.path.join(repo_dir, f))
        ],
    }


def main():
    root = os.path.expanduser(CONFIG["root"])
    mode = CONFIG["mode"]
    timeout = CONFIG.get("timeout", 600)
    report = {"host": socket.gethostname(), "mode": mode, "root": root, "repos": {}, "checks": {}}
    plan = []  # (name, dir, spec) that earn an apply, in inventory order

    for spec in CONFIG["repos"]:
        name = spec["name"]
        repo_dir = os.path.join(root, name)
        entry = {
            "status": None, "reason": None, "branch": None, "before": None, "after": None,
            "dirty": [], "missing_requires": [], "ahead": None, "behind": None,
            "pull": None, "apply": None, "verify": None,
        }
        report["repos"][name] = entry
        if not os.path.isdir(os.path.join(repo_dir, ".git")):
            entry["status"], entry["reason"] = "refused", "not-cloned"
            continue
        facts = inspect(repo_dir, spec)
        entry.update(
            branch=facts["branch"], before=facts["head"], after=facts["head"],
            dirty=facts["dirty"], missing_requires=facts["missing_requires"],
        )
        if mode == "status":
            entry["status"] = "observed"
            continue

        # -- gate: refuse anything that is not a clean replica of origin/main --
        if facts["branch"] != "main":
            entry["status"], entry["reason"] = "refused", "not-on-main"
            continue
        if facts["dirty"]:
            entry["status"], entry["reason"] = "refused", "dirty"
            continue
        if facts["missing_requires"]:
            entry["status"], entry["reason"] = "refused", "missing-requires"
            continue
        rc, out = git(repo_dir, "fetch", "--quiet", "origin", "main")
        if rc != 0:
            entry["status"], entry["reason"] = "failed", "fetch"
            entry["pull"] = {"exit": rc, "tail": tail(out)}
            continue
        rc, counts = git(repo_dir, "rev-list", "--left-right", "--count", "HEAD...origin/main")
        try:
            ahead, behind = (int(x) for x in counts.split())
        except ValueError:
            entry["status"], entry["reason"] = "failed", "rev-list"
            entry["pull"] = {"exit": rc, "tail": tail(counts)}
            continue
        entry["ahead"], entry["behind"] = ahead, behind
        if ahead:
            entry["status"], entry["reason"] = "refused", "ahead"
            continue

        # -- pull: fast-forward only; the replica invariant --
        if behind:
            rc, out = git(repo_dir, "merge", "--ff-only", "origin/main")
            entry["pull"] = {"exit": rc, "tail": tail(out)}
            if rc != 0:
                entry["status"], entry["reason"] = "failed", "pull"
                continue
            _, head = git(repo_dir, "rev-parse", "HEAD")
            entry["after"] = head.strip()
            entry["status"] = "applied"  # provisional until apply/verify report
            plan.append((name, repo_dir, spec))
        else:
            entry["status"] = "in-sync"
            if CONFIG.get("reinstall"):
                plan.append((name, repo_dir, spec))

    # -- apply: each repo's own install, in inventory order, only for repos that moved --
    for name, repo_dir, spec in plan:
        entry = report["repos"][name]
        rc, out = run(["sh", "-c", spec["apply"]], cwd=repo_dir, timeout=timeout)
        entry["apply"] = {"exit": rc, "tail": tail(out)}
        if rc != 0:
            entry["status"], entry["reason"] = "failed", "apply"
        else:
            entry["status"] = "applied"

    # -- verify: after a successful apply only --
    for name, repo_dir, spec in plan:
        entry = report["repos"][name]
        if entry["status"] != "applied" or not spec.get("verify"):
            continue
        rc, out = run(["sh", "-c", spec["verify"]], cwd=repo_dir, timeout=timeout)
        entry["verify"] = {"exit": rc, "tail": tail(out)}
        if rc != 0:
            entry["status"], entry["reason"] = "failed", "verify"

    # -- registries: dangling symlinks. A skill archived upstream leaves its link
    #    pointing nowhere after the pull, so `sync` prunes them (a link with no target
    #    carries nothing); `status` only reports. Only symlinks, only in these dirs. --
    broken, pruned = [], []
    for registry in CONFIG.get("registries", []):
        registry = os.path.expanduser(registry)
        if not os.path.isdir(registry):
            continue
        for child in sorted(os.listdir(registry)):
            path = os.path.join(registry, child)
            if os.path.islink(path) and not os.path.exists(path):
                if mode == "sync":
                    try:
                        os.unlink(path)
                        pruned.append(path)
                        continue
                    except OSError:
                        pass
                broken.append(path)
    report["checks"]["broken_symlinks"] = broken
    report["checks"]["pruned_symlinks"] = pruned

    sys.stdout.write("__REPORT_MARK__ " + json.dumps(report) + "\n")
    sys.stdout.flush()


main()
'''


# ── rendering ───────────────────────────────────────────────────────────────


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


def render_node_script(
    mode: str,
    root: str,
    repos: list[dict],
    *,
    reinstall: bool = False,
    timeout: int = APPLY_TIMEOUT,
    registries: tuple[str, ...] = REGISTRIES,
) -> str:
    """The self-contained node program for one session (`mode` is `status` or `sync`)."""
    config = {
        "mode": mode,
        "root": root,
        "repos": repos,
        "reinstall": reinstall,
        "timeout": timeout,
        "registries": list(registries),
    }
    # `repr` of the JSON text is a valid Python string literal — json.loads on the node
    # side turns it back into data. (`true`/`null` would not survive as bare Python.)
    return NODE_SCRIPT.replace("__CONFIG_JSON__", repr(json.dumps(config))).replace(
        "__REPORT_MARK__", REPORT_MARK
    )


# ── transport ───────────────────────────────────────────────────────────────


def ssh_argv(alias: str) -> list[str]:
    return ["ssh", *SSH_OPTS, alias, "python3", "-"]


def run_node(
    alias: str, script: str, runner=subprocess.run, timeout: int = SESSION_TIMEOUT
) -> tuple[int, str, str]:
    """Stream `script` to the node's `python3 -`; (rc, stdout, stderr).

    rc 255 is ssh's own "never reached a shell" (offline / refused / no key) — callers
    read it as offline. 127 when `ssh` itself is missing. `runner` is injectable so
    tests can stand in for the transport without a network.
    """
    try:
        proc = runner(
            ssh_argv(alias),
            input=script,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        return 127, "", "ssh: not found on PATH"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def parse_report(stdout: str) -> dict | None:
    """The one JSON report line the node script prints, or None when it never got there.

    Anything a login shell prints before it (motd, rc noise) is ignored — the marker
    is what identifies the report.
    """
    for line in reversed(stdout.splitlines()):
        if line.startswith(REPORT_MARK + " "):
            try:
                data = json.loads(line[len(REPORT_MARK) + 1 :])
            except json.JSONDecodeError:
                return None
            return data if isinstance(data, dict) and isinstance(data.get("repos"), dict) else None
    return None


# ── hub-side git: where distance is computed ────────────────────────────────


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
        result["ahead"] = True  # unknown commit — the node has something the hub never saw
        return result
    rc, _ = _git(repo_dir, "merge-base", "--is-ancestor", node_head, result["origin_main"])
    result["ahead"] = rc != 0
    rc, count = _git(repo_dir, "rev-list", "--count", f"{node_head}..{result['origin_main']}")
    result["behind"] = int(count) if rc == 0 and count.isdigit() else None
    return result


# ── receipts ────────────────────────────────────────────────────────────────


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
