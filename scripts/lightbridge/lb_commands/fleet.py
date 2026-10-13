"""Fleet command orchestration and presentation; transport and node code remain in lb_fleet."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from lb_fleet import (
    FLEET_HEADER,
    SEED_BLOCK,
    SSH_OFFLINE,
    classify_unreachable,
    distance,
    hub_fetch,
    hub_repo_dir,
    now_iso,
    parse_report,
    receipt_path,
    render_node_script,
    repo_specs,
    run_node,
    short,
    write_receipt,
)
from lb_resolve import load_fleet, load_receipt
from lb_style import paint, row

# ── fleet ───────────────────────────────────────────────────────────────────


def _open_fleet(fleet_file: str) -> tuple[dict | None, Path, str | None]:
    """The shared fleet preamble: expanded path + parsed inventory (or its error)."""
    fleet_path = Path(fleet_file).expanduser()
    fleet, error = load_fleet(fleet_path)
    if error is not None:
        print(f"fleet inventory is unusable: {fleet_path}\n{error}", file=sys.stderr)
    return fleet, fleet_path, error


def _require_fleet(fleet_file: str) -> tuple[dict | None, Path]:
    """Inventory or a refusal that teaches — every verb but `init` opens this way."""
    fleet, fleet_path, error = _open_fleet(fleet_file)
    if error is not None:
        return None, fleet_path
    if fleet is None:
        print(
            f"no fleet inventory: {fleet_path}\n"
            f"This machine is not a hub — seed one with `fleet init`.",
            file=sys.stderr,
        )
        return None, fleet_path
    return fleet, fleet_path


def _require_node(fleet: dict, node: str) -> bool:
    if node in fleet["nodes"]:
        return True
    known = ", ".join(fleet["nodes"]) or "(none — add a [nodes.<name>] table)"
    print(f"unknown node: {node}\nKnown: {known}", file=sys.stderr)
    return False


def _tail(text: str, lines: int = 5) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


# What each refusal/failure means and the next move — worded for the node, where the
# fix happens. `n` is the dirty-file or ahead count when one applies.
REFUSALS = {
    "not-cloned": "not cloned at {root}/{name} — clone it on the node first",
    "not-on-main": "on branch {branch} — `git switch main` on the node (push the branch first)",
    "dirty": "dirty: {n} file(s) — on the node, commit on a branch and push (or revert); never stashed here",
    "ahead": "ahead of origin/main by {n} — push the branch and open a PR; the hub pulls after merge",
    "missing-requires": "missing {files} — create the per-box file on the node (e.g. `cp .device.example .device`)",
    "fetch": "git fetch failed on the node — its GitHub key or network; tail in the receipt",
    "rev-list": "could not compare HEAD with origin/main on the node",
    "pull": "fast-forward pull failed — tail in the receipt",
    "apply": "apply exited {code} — tail in the receipt",
    "verify": "verify exited {code} — tail in the receipt",
}


# The receipt step holding a failure's output. The node files fetch and rev-list
# failures under `pull` (one git phase), so a reason is not always its own key.
STEP_OF = {
    "fetch": "pull",
    "rev-list": "pull",
    "pull": "pull",
    "apply": "apply",
    "verify": "verify",
}


def _explain(entry: dict, root: str, name: str) -> str:
    reason = entry.get("reason") or "?"
    template = REFUSALS.get(reason, reason)
    step = entry.get(STEP_OF[reason]) if reason in STEP_OF else None
    return template.format(
        root=root,
        name=name,
        branch=entry.get("branch") or "?",
        n=len(entry.get("dirty") or [])
        if reason == "dirty"
        else entry.get("ahead") or "?",
        files=", ".join(entry.get("missing_requires") or []),
        code=(step or {}).get("exit", "?"),
    )


def _classify(entry: dict, dist: dict) -> str:
    """One word per repo for `status`: in-sync | behind | diverged | not-cloned.

    `diverged` = anything the sync gate would refuse (needs a human on the node).
    """
    if entry.get("reason") == "not-cloned":
        return "not-cloned"
    if (
        entry.get("branch") != "main"
        or entry.get("dirty")
        or entry.get("missing_requires")
        or dist.get("ahead")
    ):
        return "diverged"
    return "behind" if dist.get("behind") else "in-sync"


def _flags(entry: dict, dist: dict) -> list[str]:
    flags = []
    if entry.get("branch") not in (None, "main"):
        flags.append(f"not on main ({entry['branch']})")
    if entry.get("dirty"):
        flags.append(f"DIRTY {len(entry['dirty'])}")
    if dist.get("ahead"):
        flags.append(
            "AHEAD (unknown to hub)" if dist.get("behind") is None else "AHEAD"
        )
    if entry.get("missing_requires"):
        flags.append("missing " + ", ".join(entry["missing_requires"]))
    return flags


def cmd_fleet_init(fleet_file: str, dry_run: bool, json_out: bool) -> int:
    fleet_path = Path(fleet_file).expanduser()
    if fleet_path.is_file():
        print(
            f"fleet inventory already exists: {fleet_path}\n"
            f"`fleet init` never clobbers — edit the file (it is hand-authored by design).",
            file=sys.stderr,
        )
        return 1
    text = FLEET_HEADER + "\n" + SEED_BLOCK
    if dry_run:
        print(text, end="")
        return 0
    fleet_path.parent.mkdir(parents=True, exist_ok=True)
    fleet_path.write_text(text, encoding="utf-8")
    fleet, error = load_fleet(fleet_path)
    if json_out:
        print(
            json.dumps(
                {
                    "fleet": str(fleet_path),
                    "created": True,
                    "nodes": list(fleet["nodes"]) if fleet else [],
                    "repos": list(fleet["repos"]) if fleet else [],
                },
                indent=2,
            )
        )
        return 0
    print(row("created", str(fleet_path)))
    print(
        row(
            "nodes", ", ".join(fleet["nodes"]) if fleet else f"(seed unusable: {error})"
        )
    )
    print(
        row(
            "next",
            "edit the [nodes.*] tables to match ~/.ssh/config, then `fleet status`",
        )
    )
    return 0


def cmd_fleet_status(
    node: str | None,
    fleet_file: str,
    no_fetch: bool,
    json_out: bool,
    runner=subprocess.run,
) -> int:
    """Live: ask each node what it has, compute the distance here, compare to receipts.

    Exit 0 only when every addressed node answered and every repo is in-sync.
    """
    fleet, fleet_path = _require_fleet(fleet_file)
    if fleet is None:
        return 1
    if node is not None and not _require_node(fleet, node):
        return 1
    names = [node] if node else list(fleet["nodes"])
    hub_root = fleet["hub"]["root"]

    fetched: dict[str, str | None] = {}

    def ensure_fetched(repo: str) -> None:
        if repo in fetched:
            return
        fetched[repo] = None if no_fetch else hub_fetch(hub_repo_dir(hub_root, repo))
        if fetched[repo]:
            print(
                f"note: {repo}: {fetched[repo]} — distance may be stale",
                file=sys.stderr,
            )

    nodes_out: dict[str, dict] = {}
    all_clean = True
    for nname in names:
        spec = fleet["nodes"][nname]
        receipt, receipt_error = load_receipt(receipt_path(fleet_path, nname))
        if receipt_error:
            print(f"note: receipt for {nname}: {receipt_error}", file=sys.stderr)
        out: dict = {
            "ssh": spec["ssh"],
            "online": None,
            "host": None,
            "error": None,
            "unreachable": None,
            "last_sync": receipt.get("timestamp") if receipt else None,
            "repos": {},
            "checks": None,
        }
        nodes_out[nname] = out
        print(f"{nname}: asking {spec['ssh']} …", file=sys.stderr)
        rc, stdout, stderr = run_node(
            spec["ssh"],
            render_node_script("status", spec["root"], repo_specs(fleet, nname)),
            runner,
        )
        if rc == SSH_OFFLINE:
            kind, why = classify_unreachable(stderr)
            out.update(online=False, unreachable=kind, error=why)
            all_clean = False
            continue
        if rc == 127:
            out.update(error=stderr.strip())
            all_clean = False
            continue
        report = parse_report(stdout)
        if report is None:
            out.update(
                online=True,
                error=f"no report from node (exit {rc}): {_tail(stderr or stdout)}",
            )
            all_clean = False
            continue
        out.update(online=True, host=report.get("host"), checks=report.get("checks"))
        synced = (receipt or {}).get("repos", {})
        for rname, entry in report["repos"].items():
            ensure_fetched(rname)
            dist = distance(hub_repo_dir(hub_root, rname), entry.get("before"))
            state = _classify(entry, dist)
            if state != "in-sync":
                all_clean = False
            out["repos"][rname] = {
                "state": state,
                "branch": entry.get("branch"),
                "head": entry.get("before"),
                "origin_main": dist["origin_main"],
                "behind": dist["behind"],
                "ahead": dist["ahead"],
                "dirty": entry.get("dirty") or [],
                "missing_requires": entry.get("missing_requires") or [],
                "last_synced": (synced.get(rname) or {}).get("after"),
                "distance_error": dist["error"],
            }

    if json_out:
        print(json.dumps({"fleet": str(fleet_path), "nodes": nodes_out}, indent=2))
        return 0 if all_clean else 1

    for nname, out in nodes_out.items():
        if out["online"] is False or out["error"]:
            # A failed name lookup is this machine's fault — the node may be fine.
            tone = "warn" if out["unreachable"] == "dns" else "bad"
            print(row("node", f"{nname}  {paint(out['error'], tone)}", tone))
            continue
        last = out["last_sync"] or "never"
        print(
            row(
                "node",
                f"{nname}  {paint('online', 'ok')} · {out['host']} · last sync {last}",
            )
        )
        for rname, repo in out["repos"].items():
            if repo["state"] == "not-cloned":
                head = paint("not cloned", "bad")
            elif repo["behind"] is None and repo["ahead"]:
                head = paint("unknown to hub", "bad")
            elif repo["behind"]:
                head = paint(f"behind {repo['behind']}", "warn")
            else:
                head = paint("in-sync", "ok")
            parts = [
                head,
                *(
                    paint(flag, "bad")
                    for flag in _flags(
                        {
                            "branch": repo["branch"],
                            "dirty": repo["dirty"],
                            "missing_requires": repo["missing_requires"],
                        },
                        {"ahead": repo["ahead"], "behind": repo["behind"]},
                    )
                ),
            ]
            if repo["distance_error"]:
                parts.append(paint(f"({repo['distance_error']})", "warn"))
            print(row("repo", f"{rname:<22} {' · '.join(parts)}"))
        broken = (out["checks"] or {}).get("broken_symlinks")
        if broken is not None:
            print(
                row(
                    "checks",
                    paint(f"broken symlinks {len(broken)}", "bad" if broken else "ok"),
                )
            )
    if not all_clean:
        print(
            row(
                "next",
                "fleet sync NODE  — pulls `behind` repos; `diverged` ones are refused until fixed on the node",
            )
        )
    return 0 if all_clean else 1


def cmd_fleet_sync(
    node: str,
    only: list[str],
    dry_run: bool,
    reinstall: bool,
    fleet_file: str,
    json_out: bool,
    runner=subprocess.run,
) -> int:
    """Reconcile one node to origin/main: gate → ff-only pull → apply → verify → receipt.

    Exit 0 when every addressed repo is applied or in-sync and the registries are clean.
    """
    fleet, fleet_path = _require_fleet(fleet_file)
    if fleet is None:
        return 1
    if not _require_node(fleet, node):
        return 1
    spec = fleet["nodes"][node]
    unknown = [r for r in only if r not in spec["repos"]]
    if unknown:
        print(
            f"{node} does not carry: {', '.join(unknown)}\nIts repos: {', '.join(spec['repos'])}",
            file=sys.stderr,
        )
        return 2
    specs = repo_specs(fleet, node, only or None)
    script = render_node_script("sync", spec["root"], specs, reinstall=reinstall)

    if dry_run:
        if json_out:
            print(
                json.dumps(
                    {
                        "node": node,
                        "ssh": spec["ssh"],
                        "root": spec["root"],
                        "reinstall": reinstall,
                        "repos": specs,
                        "dry_run": True,
                    },
                    indent=2,
                )
            )
            return 0
        print(row("node", f"{node}  via ssh {spec['ssh']}  root {spec['root']}"))
        for item in specs:
            verify = f"  ·  verify: {item['verify']}" if item.get("verify") else ""
            requires = (
                f"  ·  requires: {', '.join(item['requires'])}"
                if item.get("requires")
                else ""
            )
            print(
                row(
                    "repo",
                    f"{item['name']:<22} apply: {item['apply']}{verify}{requires}",
                )
            )
        print(row("dry-run", "nothing sent — drop --dry-run to reconcile"))
        return 0

    print(f"{node}: reconciling via {spec['ssh']} …", file=sys.stderr)
    rc, stdout, stderr = run_node(spec["ssh"], script, runner)
    if rc == SSH_OFFLINE:
        _, why = classify_unreachable(stderr)
        print(
            f"{node} not reached via {spec['ssh']}: {why} — nothing changed.",
            file=sys.stderr,
        )
        return 1
    if rc == 127:
        print(stderr.strip(), file=sys.stderr)
        return 1
    report = parse_report(stdout)
    if report is None:
        print(
            f"{node}: no report came back (exit {rc}) — the node script did not finish:\n"
            f"{_tail(stderr or stdout, 10)}",
            file=sys.stderr,
        )
        return 1

    repos = report["repos"]
    broken = (report.get("checks") or {}).get("broken_symlinks") or []
    ok = (
        all(e.get("status") in ("applied", "in-sync") for e in repos.values())
        and not broken
    )
    receipt = {
        "node": node,
        "host": report.get("host"),
        "timestamp": now_iso(),
        "mode": "sync",
        "reinstall": reinstall,
        "ok": ok,
        "repos": repos,
        "checks": report.get("checks") or {},
    }
    path = write_receipt(fleet_path, node, receipt)

    if json_out:
        print(json.dumps({"receipt": str(path), **receipt}, indent=2))
        return 0 if ok else 1

    root = report.get("root") or spec["root"]
    for rname, entry in repos.items():
        status = entry.get("status")
        if status == "applied":
            moved = entry.get("before") != entry.get("after")
            if moved:
                print(
                    row(
                        "applied",
                        f"{rname:<22} {short(entry['before'])} → {short(entry['after'])}  (+{entry.get('behind') or '?'})",
                        "ok",
                    )
                )
            else:
                print(
                    row(
                        "applied",
                        f"{rname:<22} {short(entry['after'])}  (reinstalled, no new commits)",
                        "ok",
                    )
                )
        elif status == "in-sync":
            print(row("in-sync", f"{rname:<22} {short(entry.get('after'))}", "ok"))
        elif status == "refused":
            print(row("REFUSED", f"{rname:<22} {_explain(entry, root, rname)}", "bad"))
        else:
            print(row("FAILED", f"{rname:<22} {_explain(entry, root, rname)}", "bad"))
            step = entry.get(STEP_OF.get(entry.get("reason") or "", ""))
            if isinstance(step, dict) and step.get("tail"):
                print(_tail(step["tail"], 8), file=sys.stderr)
    pruned = (report.get("checks") or {}).get("pruned_symlinks") or []
    if pruned:
        print(
            row(
                "pruned",
                f"{len(pruned)} dangling registry link(s): "
                + ", ".join(os.path.basename(p) for p in pruned[:5]),
            )
        )
    print(
        row(
            "checks",
            paint(f"broken symlinks {len(broken)}", "bad" if broken else "ok")
            + (f" — {', '.join(broken[:3])}" if broken else ""),
        )
    )
    print(row("receipt", str(path)))
    return 0 if ok else 1
