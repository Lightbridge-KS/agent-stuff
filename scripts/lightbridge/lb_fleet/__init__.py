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

from lb_resolve import DEFAULT_FLEET, fleet_receipts_dir, load_receipt

from .node_program import (
    REPORT_MARK,
    REGISTRIES,
    APPLY_TIMEOUT,
    NODE_SCRIPT,
    render_node_script,
    parse_report,
)
from .transport import (
    SSH_OPTS,
    SSH_OFFLINE,
    SESSION_TIMEOUT,
    ssh_argv,
    run_node,
    UNREACHABLE,
    classify_unreachable,
)
from .hub import (
    FLEET_HEADER,
    SEED_BLOCK,
    repo_specs,
    hub_repo_dir,
    hub_fetch,
    distance,
    now_iso,
    short,
    receipt_path,
    write_receipt,
)

__all__ = [
    "DEFAULT_FLEET",
    "fleet_receipts_dir",
    "load_receipt",
    "REPORT_MARK",
    "REGISTRIES",
    "APPLY_TIMEOUT",
    "NODE_SCRIPT",
    "render_node_script",
    "parse_report",
    "SSH_OPTS",
    "SSH_OFFLINE",
    "SESSION_TIMEOUT",
    "ssh_argv",
    "run_node",
    "UNREACHABLE",
    "classify_unreachable",
    "FLEET_HEADER",
    "SEED_BLOCK",
    "repo_specs",
    "hub_repo_dir",
    "hub_fetch",
    "distance",
    "now_iso",
    "short",
    "receipt_path",
    "write_receipt",
]
