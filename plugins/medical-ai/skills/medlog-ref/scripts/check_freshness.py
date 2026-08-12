#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Check the pinned MedLog spec snapshot against the live upstream spec.

This skill is Reference-kind: it caches facts that go stale silently. MedLog is at
0.0.1 and pre-1.0 schemas move, so the cache needs a doctor.

    uv run scripts/check_freshness.py          # human summary
    uv run scripts/check_freshness.py --json   # machine report

Compares three things against assets/openapi-0.0.1.yaml:

    info.version   the declared spec version
    paths          the five write-once event endpoints
    schema names   the component schema set (BaseEvent, Inputs, Outcome, ...)

Deliberately shallow: it answers "has upstream moved?", not "how exactly". On drift,
re-read https://medlogprotocol.ai/llms.txt and refresh the snapshot and references.

YAML is matched with regexes rather than a parser so the script stays dependency-free
and runs anywhere `uv` does. The three things it extracts are top-level and stable; a
restructure deep enough to defeat the regexes is itself drift worth reporting.

Exit codes: 0 in sync · 1 drift detected · 2 usage, network, or parse failure.
"""

from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parent.parent / "assets" / "openapi-0.0.1.yaml"
LIVE_URL = "https://medlogprotocol.ai/api-reference/openapi.yaml"
TIMEOUT = 15


def parse_spec(text: str) -> dict:
    """Pull version, paths, and component-schema names out of an OpenAPI YAML document."""
    version = ""
    if m := re.search(r"^info:$(.*?)^\S", text + "\n￿", re.S | re.M):
        if v := re.search(r"^\s+version:\s*(\S+)", m.group(1), re.M):
            version = v.group(1).strip("\"'")

    paths = re.findall(r"^  (/\S*):", text, re.M)

    schemas: list[str] = []
    if m := re.search(r"^  schemas:$(.*?)^  \S", text + "\n  ￿", re.S | re.M):
        schemas = re.findall(r"^    (\w+):", m.group(1), re.M)

    return {"version": version, "paths": sorted(paths), "schemas": sorted(schemas)}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "medlog-ref/check_freshness"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # noqa: S310 - fixed https URL
        return resp.read().decode("utf-8")


def diff(pinned: dict, live: dict) -> list[str]:
    """Return one line per divergence; empty means in sync."""
    out = []
    if pinned["version"] != live["version"]:
        out.append(f"version: pinned {pinned['version']!r} -> live {live['version']!r}")
    for key in ("paths", "schemas"):
        added = sorted(set(live[key]) - set(pinned[key]))
        removed = sorted(set(pinned[key]) - set(live[key]))
        if added:
            out.append(f"{key} added: {', '.join(added)}")
        if removed:
            out.append(f"{key} removed: {', '.join(removed)}")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="check_freshness.py",
        description="Check the pinned MedLog spec snapshot against the live upstream spec.",
    )
    ap.add_argument("--json", action="store_true", help="Emit a machine report.")
    ap.add_argument("--url", default=LIVE_URL, help=f"Live spec URL (default: {LIVE_URL})")
    args = ap.parse_args(argv)

    if not SNAPSHOT.is_file():
        print(f"error: snapshot missing at {SNAPSHOT}", file=sys.stderr)
        return 2

    pinned = parse_spec(SNAPSHOT.read_text(encoding="utf-8"))
    if not pinned["paths"]:
        print(f"error: could not parse the snapshot at {SNAPSHOT}", file=sys.stderr)
        return 2

    try:
        live = parse_spec(fetch(args.url))
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as exc:
        # Unreachable or truncated upstream is NOT drift — it says nothing about the
        # spec, so it must never share an exit code with a real schema change.
        # http.client.HTTPException covers IncompleteRead, which a proxy or a dropped
        # chunked response raises and which is not an OSError.
        print(f"error: could not fetch {args.url}: {exc!r}", file=sys.stderr)
        return 2

    if not live["paths"]:
        print(f"error: fetched {args.url} but found no paths — not an OpenAPI document?", file=sys.stderr)
        return 2

    changes = diff(pinned, live)

    if args.json:
        print(json.dumps({
            "in_sync": not changes,
            "pinned": pinned,
            "live": live,
            "changes": changes,
            "url": args.url,
        }, indent=2))
        return 1 if changes else 0

    if not changes:
        print(f"in sync: MedLog spec {pinned['version']} "
              f"({len(pinned['paths'])} endpoints, {len(pinned['schemas'])} schemas)")
        return 0

    print("DRIFT — the pinned snapshot no longer matches upstream:")
    for line in changes:
        print(f"  {line}")
    print("\nRefresh: re-read https://medlogprotocol.ai/llms.txt, update")
    print(f"  {SNAPSHOT.name}, then reconcile references/record-schema.md and")
    print("  references/wire-protocol.md against it.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
