#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Deliver a skill-health alert to a configured Telegram forum topic."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_ENV = "SKILL_HEALTH_TELEGRAM_CONFIG"
OPENCLAW_ENV = "SKILL_HEALTH_OPENCLAW_BIN"
DEFAULT_CONFIG = "~/.config/skill-health/telegram.toml"
DEFAULT_OPENCLAW = "/opt/homebrew/bin/openclaw"
MAX_MESSAGE_CHARS = 3800  # Telegram's limit is 4096; leave delivery headroom.
MAX_DETAIL_CHARS = 700


@dataclass(frozen=True)
class TelegramConfig:
    chat_id: str
    thread_id: str
    account: str = "default"
    silent: bool = True


def load_config(path: Path) -> TelegramConfig:
    """Load the machine-local Telegram destination."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"config not found: {path}") from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"could not read config {path}: {exc}") from exc

    chat_id = str(data.get("chat_id", "")).strip()
    thread_id = str(data.get("thread_id", "")).strip()
    account = str(data.get("account", "default")).strip()
    silent = data.get("silent", True)
    if not chat_id:
        raise ValueError(f"chat_id is required in {path}")
    if not thread_id:
        raise ValueError(f"thread_id is required in {path}")
    if not account:
        raise ValueError(f"account must not be empty in {path}")
    if not isinstance(silent, bool):
        raise ValueError(f"silent must be true or false in {path}")
    return TelegramConfig(chat_id, thread_id, account, silent)


def parse_alert(raw: str) -> dict[str, Any]:
    """Validate the stdin envelope before formatting or delivery."""
    try:
        alert = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"stdin is not valid JSON: {exc}") from exc
    if not isinstance(alert, dict):
        raise ValueError("stdin JSON must be an object")
    if alert.get("type") != "skill_health":
        raise ValueError(f"expected alert type 'skill_health', got {alert.get('type')!r}")
    if not isinstance(alert.get("checks", []), list):
        raise ValueError("checks must be an array")
    return alert


def ellipsize(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def render_message(alert: dict[str, Any]) -> str:
    """Render one bounded, plain-text Telegram message."""
    severity = str(alert.get("severity") or "warning")
    summary = str(alert.get("message") or "skill-health found a red check")
    host = str(alert.get("host") or "unknown-host")
    metadata = alert.get("metadata") if isinstance(alert.get("metadata"), dict) else {}
    report_path = str(metadata.get("report_path") or "")
    red_checks = [
        check
        for check in alert.get("checks", [])
        if isinstance(check, dict) and check.get("status") == "red"
    ]

    lines = [f"⚠️ Skill health [{severity}]", "", summary, f"Host: {host}"]
    if red_checks:
        lines.extend(["", "Failed checks:"])
    for check in red_checks:
        name = str(check.get("name") or "unknown")
        what = str(check.get("what") or "").strip()
        label = f"• {name}" + (f" — {what}" if what else "")
        lines.append(label)
        detail = ellipsize(str(check.get("detail") or "").strip(), MAX_DETAIL_CHARS)
        if detail:
            lines.extend(f"  {line}" for line in detail.splitlines())

    footer = f"Report: {report_path}" if report_path else ""
    body = "\n".join(lines)
    if footer:
        budget = MAX_MESSAGE_CHARS - len(footer) - 2
        return f"{ellipsize(body, budget)}\n\n{footer}"
    return ellipsize(body, MAX_MESSAGE_CHARS)


def build_command(
    config: TelegramConfig,
    message: str,
    openclaw_bin: str,
    *,
    dry_run: bool,
) -> list[str]:
    command = [
        openclaw_bin,
        "message",
        "send",
        "--account",
        config.account,
        "--channel",
        "telegram",
        "--target",
        config.chat_id,
        "--thread-id",
        config.thread_id,
        "--message",
        message,
        "--json",
    ]
    if config.silent:
        command.append("--silent")
    if dry_run:
        command.append("--dry-run")
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.environ.get(CONFIG_ENV) or DEFAULT_CONFIG).expanduser(),
        help=f"destination TOML (default: {DEFAULT_CONFIG}; env {CONFIG_ENV})",
    )
    parser.add_argument(
        "--openclaw",
        default=os.environ.get(OPENCLAW_ENV) or DEFAULT_OPENCLAW,
        help=f"OpenClaw executable (default: {DEFAULT_OPENCLAW}; env {OPENCLAW_ENV})",
    )
    parser.add_argument("--dry-run", action="store_true", help="print delivery payload without sending")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config.expanduser())
        alert = parse_alert(sys.stdin.read())
        openclaw_bin = shutil.which(args.openclaw) or args.openclaw
        command = build_command(
            config,
            render_message(alert),
            openclaw_bin,
            dry_run=args.dry_run,
        )
        proc = subprocess.run(command, timeout=60)
    except ValueError as exc:
        print(f"skill-health Telegram notifier: {exc}", file=sys.stderr)
        return 78
    except subprocess.TimeoutExpired:
        print("skill-health Telegram notifier: delivery timed out after 60s", file=sys.stderr)
        return 70
    except OSError as exc:
        print(f"skill-health Telegram notifier: could not run OpenClaw: {exc}", file=sys.stderr)
        return 69
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
