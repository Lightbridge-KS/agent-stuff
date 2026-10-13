"""Self-contained node program and its rendered configuration/report protocol."""

from __future__ import annotations

import json


REPORT_MARK = "LB_FLEET_REPORT"


REGISTRIES = ("~/.claude/skills", "~/.codex/skills")


APPLY_TIMEOUT = 600  # seconds per apply/verify command on the node


# The node-side program. Deliberately conservative Python (3.8+ syntax, stdlib only) —
# it runs under whatever `python3` a node's login shell finds. Two placeholders are
# substituted by `render_node_script`; everything else is literal.
NODE_SCRIPT = r'''
import json, os, signal, socket, subprocess, sys

CONFIG = json.loads(__CONFIG_JSON__)


def _path_with_user_bins():
    """A non-interactive ssh shell skips the login PATH, so ~/.local/bin (uv on Ubuntu)
    and /usr/local/bin can be missing; prepend them once, without duplicating."""
    extra = [os.path.expanduser("~/.local/bin"), "/usr/local/bin", "/opt/homebrew/bin"]
    current = os.environ.get("PATH", "").split(os.pathsep)
    return os.pathsep.join([p for p in extra if p not in current and os.path.isdir(p)] + current)


ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", PATH=_path_with_user_bins())


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
            return (
                data
                if isinstance(data, dict) and isinstance(data.get("repos"), dict)
                else None
            )
    return None
