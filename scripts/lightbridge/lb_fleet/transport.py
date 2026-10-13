"""Bounded SSH execution and unreachable-node diagnostics."""

from __future__ import annotations

import subprocess


SSH_OPTS = ("-o", "BatchMode=yes", "-o", "ConnectTimeout=8")


SSH_OFFLINE = 255  # ssh's own exit code when it never reached a shell


SESSION_TIMEOUT = 1800  # seconds for the whole ssh session


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


# ssh exits 255 whenever it never reached a shell, and "the node is down" is only one
# reason. Its own stderr says which; each pattern maps to a stable `kind` (for --json)
# and to where the fault lies. First match wins.
UNREACHABLE = (
    (
        "dns",
        "Could not resolve hostname",
        "name lookup failed on this machine — the node may well be up; check DNS/Tailscale "
        "here (an agent sandbox can block it too)",
    ),
    (
        "auth",
        "Permission denied",
        "the node refused this machine's ssh key — it is up; check its authorized_keys",
    ),
    (
        "host-key",
        "Host key verification failed",
        "host key mismatch — check known_hosts before trusting the node",
    ),
    (
        "refused",
        "Connection refused",
        "reachable, but nothing accepts ssh — the node is up, its sshd is not",
    ),
    (
        "timeout",
        "timed out",
        "offline — connection timed out; the node is off, asleep, or off the network",
    ),
    (
        "no-route",
        "No route to host",
        "offline — no route to the node; it is off or off the network",
    ),
)


def classify_unreachable(stderr: str) -> tuple[str, str]:
    """(kind, explanation) for an ssh exit 255, read from ssh's own stderr.

    The explanation ends with ssh's last stderr line, so nothing is lost when no
    pattern matches (kind `unknown`).
    """
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    kind, why = next(
        ((kind, why) for kind, needle, why in UNREACHABLE if needle in stderr),
        ("unknown", "offline or unreachable — no shell reached"),
    )
    return kind, f"{why} (ssh exit 255{': ' + lines[-1] if lines else ''})"
