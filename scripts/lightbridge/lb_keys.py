"""The personal LLM API key documents — `~/.lightbridge/keys.toml` + `secrets.toml`.

Two layers, deliberately split (ADR 0003):

* **keys.toml** — the agent-readable catalog: one `[keys.<name>]` table per key with
  `provider`, `env` (the variable `key run` injects), and `scope` (what the key is FOR).
  Names follow the per-scope convention (`openai-personal`, `openai-image-gen`), so many
  keys per provider is the normal shape, not an anomaly.
* **secrets.toml** — the values, a flat `[secrets]` name → value table. Mode 0600,
  deny-listed in the agent harness, and **never printed by any verb**: the one consumer
  of `load_secrets` is `cmd_key_run`, which injects into a child process env and execs.
  There is no `lb key get` — the absence is the contract.

CLI-side only: no hook reads keys, so nothing here joins `lb_resolve`'s frozen importer
API (the constants below are this module's, not `lb_resolve`'s). Write helpers are built
on `lb_tomledit`'s span primitives, so comments, ordering, and quoting style survive —
lines a function does not target come out byte-identical.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

from lb_tomledit import section_span, terminate, toml_str

DEFAULT_KEYS = "~/.lightbridge/keys.toml"
DEFAULT_SECRETS = "~/.lightbridge/secrets.toml"

KEYS_HEADER = """\
# ~/.lightbridge/keys.toml — catalog of personal LLM API keys: WHAT exists and WHERE it
# goes, never the values (those live in secrets.toml, which agents must not read).
# One [keys.<name>] table per key; name by scope, not provider — openai-personal,
# openai-image-gen, anthropic-personal, llama-cloud. Many keys per provider is normal.
#   provider = "openai"          # who issued it
#   env      = "OPENAI_API_KEY"  # the env var `lb key run` injects
#   scope    = "..."             # one line: what this key is FOR
# Managed by `lightbridge key add|rm|ls`; audited by `key doctor`. Spec: the llm-keys skill.
"""

SECRETS_HEADER = """\
# ~/.lightbridge/secrets.toml — SECRET VALUES for the keys catalogued in keys.toml.
# NEVER read, cat, print, or commit this file. No lb verb ever prints a value; the only
# consumer is `lightbridge key run`, which injects values into a child process's
# environment. File mode stays 0600 (`key doctor` checks). Managed by `key add|rm`.
[secrets]
"""

KEY_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")  # a bare TOML key (REPO_NAME's shape)
ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")  # a conventional environment variable name

# The one reason string for a secrets file this *environment* refuses to touch (an
# agent-sandbox deny — the guardrail working, not rot). Callers compare against it to
# tell the denied state from a genuinely unreadable file.
SECRETS_DENIED = (
    "access denied by this environment — an agent-sandbox deny on secrets.toml is the "
    "guardrail working; the human can run this outside the sandbox"
)


def load_keys(keys: Path) -> tuple[dict[str, dict] | None, str | None]:
    """Read the key catalog, `~/.lightbridge/keys.toml`.

    Returns (catalog, error) — the tri-state every user-level reader shares:

    * `(None, None)` — the file is absent. This machine has not opted in; callers stay
      silent.
    * `(None, reason)` — the file exists but is unusable: bad TOML, a `keys` value that
      is not a table of tables, or root-level keys with no `[keys.*]` header (the
      hand-authoring mistake — the names are visible in the file and must not be
      reported as "no keys catalogued").
    * `({name: {provider, env, scope}}, None)` — usable; `{}` when nothing is
      catalogued yet. Each field is a stripped string or None when absent/blank —
      normalization only; a missing `env` is `key doctor`'s finding, not a load error.
    """
    try:
        if not keys.is_file():
            return None, None
        data = tomllib.loads(keys.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as exc:
        # OSError covers a sandbox that refuses even stat() — refuse, never traceback.
        return None, f"unreadable ({exc})"

    table = data.get("keys")
    if not isinstance(table, dict):
        stranded = [key for key, value in data.items() if not isinstance(value, dict)]
        if stranded:
            names = ", ".join(sorted(stranded)[:3]) + ("…" if len(stranded) > 3 else "")
            return None, (
                f"missing [keys.<name>] tables (found {len(stranded)} root-level "
                f"key(s): {names} — each key must be its own [keys.<name>] table)"
            )
        return {}, None
    bad = sorted(name for name, entry in table.items() if not isinstance(entry, dict))
    if bad:
        names = ", ".join(bad[:3]) + ("…" if len(bad) > 3 else "")
        return None, (
            f"[keys] holds non-table entrie(s): {names} — each key must be a "
            f"[keys.<name>] table"
        )

    def _field(entry: dict, key: str) -> str | None:
        value = entry.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    return {
        name: {
            "provider": _field(entry, "provider"),
            "env": _field(entry, "env"),
            "scope": _field(entry, "scope"),
        }
        for name, entry in table.items()
    }, None


def _load_secrets_table(secrets: Path) -> tuple[dict[str, str] | None, str | None]:
    """The `[secrets]` table, same tri-state as `load_keys` (`load_registry`'s shape).

    Error strings never embed file content — tomllib errors carry line/col, not values.
    """
    try:
        if not secrets.is_file():
            return None, None
        data = tomllib.loads(secrets.read_text(encoding="utf-8"))
    except PermissionError:
        # A sandbox deny blocks even stat(); that state is expected, not rot.
        return None, SECRETS_DENIED
    except (tomllib.TOMLDecodeError, OSError) as exc:
        # tomllib errors carry line/col positions, never file content — safe to surface.
        return None, f"unreadable ({exc})"

    table = data.get("secrets")
    if not isinstance(table, dict):
        stranded = [key for key, value in data.items() if not isinstance(value, dict)]
        if stranded:
            return None, (
                f"missing a [secrets] table (found {len(stranded)} root-level key(s) "
                f"— indent them under a [secrets] header)"
            )
        return {}, None
    return {k: v for k, v in table.items() if isinstance(v, str) and v.strip()}, None


def load_secret_names(secrets: Path) -> tuple[list[str] | None, str | None]:
    """The *names* holding a stored value — what `ls` and `doctor` consume, so values
    never enter their code paths."""
    table, error = _load_secrets_table(secrets)
    return (None if table is None else sorted(table)), error


def load_secrets(secrets: Path) -> tuple[dict[str, str] | None, str | None]:
    """Name → value. **The one caller is `cmd_key_run`** — values go straight into a
    child process env, never into any rendering."""
    return _load_secrets_table(secrets)


# ── line surgery ────────────────────────────────────────────────────────────


def render_key(name: str, provider: str, env: str, scope: str) -> str:
    """One `[keys.<name>]` block."""
    return (
        f"[keys.{name}]\n"
        f"provider = {toml_str(provider)}\n"
        f"env = {toml_str(env)}\n"
        f"scope = {toml_str(scope)}\n"
    )


def append_key(text: str, name: str, provider: str, env: str, scope: str) -> str:
    """`text` with the key's block appended at EOF — never inside an existing block."""
    text = terminate(text)
    separator = "" if text.endswith("\n\n") or not text else "\n"
    return text + separator + render_key(name, provider, env, scope)


def remove_key(text: str, name: str) -> str | None:
    """`text` without `name`'s `[keys.<name>]` block, absorbing the blank separator
    line above it; None when the header is absent."""
    span = section_span(text, f"keys.{name}")
    if span is None:
        return None
    lines = text.splitlines(keepends=True)
    start, end = span
    if start > 0 and lines[start - 1].strip() == "":
        start -= 1
    while end > span[0] + 1 and lines[end - 1].strip() == "":
        end -= 1
    return "".join(lines[:start] + lines[end:])


def append_secret(text: str, name: str, value: str) -> str:
    """`text` with `name = 'value'` appended inside `[secrets]` — `append_repo`'s
    targeted line edit, applied to the secrets table."""
    line = f"{name} = {toml_str(value)}\n"
    text = terminate(text)
    span = section_span(text, "secrets")
    if span is None:
        return text + "\n[secrets]\n" + line
    lines = text.splitlines(keepends=True)
    end = span[1]
    while end > span[0] + 1 and lines[end - 1].strip() == "":
        end -= 1
    lines.insert(end, line)
    return "".join(lines)


def remove_secret(text: str, name: str) -> str | None:
    """`text` without `name`'s line in `[secrets]`; None when the line can't be found
    (hand-written key shape this tool doesn't manage — edit the file directly)."""
    span = section_span(text, "secrets")
    if span is None:
        return None
    lines = text.splitlines(keepends=True)
    pattern = re.compile(rf'\s*(?:{re.escape(name)}|"{re.escape(name)}")\s*=')
    for i in range(span[0] + 1, span[1]):
        if pattern.match(lines[i]):
            del lines[i]
            return "".join(lines)
    return None


# ── the secure write ────────────────────────────────────────────────────────


def write_secrets(path: Path, text: str) -> None:
    """Write secrets.toml owner-only — the one write path for the values file.

    `os.open` with mode 0600 covers creation; `fchmod` repairs a pre-existing loose
    mode on the same descriptor (no window between check and write). Windows has no
    POSIX mode bits — the plain write is all there is.
    """
    if os.name == "nt":
        path.write_text(text, encoding="utf-8")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1  # fdopen owns it now
            handle.write(text)
    finally:
        if fd != -1:
            os.close(fd)


def secrets_mode_problem(path: Path) -> str | None:
    """A one-line finding when the values file is group/other-readable; None when the
    mode is tight, the file is absent, or mode bits are meaningless (Windows)."""
    try:
        if os.name == "nt" or not path.is_file():
            return None
        mode = path.stat().st_mode & 0o777
    except OSError:
        return None  # can't stat (e.g. a sandbox deny) → can't audit the mode
    if mode & 0o077 == 0:
        return None
    return f"mode {mode:03o} — group/other readable; run: chmod 600 {path}"


# ── doctor ──────────────────────────────────────────────────────────────────


def audit(
    keys: dict[str, dict], secret_names: list[str] | None, secrets_path: Path
) -> list[dict]:
    """Every catalog/values mismatch worth fixing — `{kind, subject, detail}` each.

    `secret_names=None` means value presence is *unknown* (the secrets file is denied
    or unreadable in this environment) — the value-presence checks are skipped rather
    than reported wrong. An absent secrets file is knowledge, not ignorance: callers
    pass `[]` for it, so every catalogued key is rightly flagged valueless.

    Two catalog entries sharing one `env` is deliberately NOT a finding: per-scope
    keys for one provider legitimately share a variable; only selecting both in a
    single `key run` collides, and that refusal lives there.
    """
    problems: list[dict] = []
    presence_known = secret_names is not None
    stored = set(secret_names or [])
    for name, entry in sorted(keys.items()):
        if not KEY_NAME.match(name):
            problems.append(
                {
                    "kind": "bad-name",
                    "subject": name,
                    "detail": "not a bare-key name (letters, digits, '-', '_') — "
                    "rename the [keys.<name>] table in the file",
                }
            )
        if entry.get("env") is None:
            problems.append(
                {
                    "kind": "missing-env",
                    "subject": name,
                    "detail": "no usable `env` — `key run` cannot inject; add "
                    'env = "PROVIDER_API_KEY" to its table',
                }
            )
        elif not ENV_NAME.match(entry["env"]):
            problems.append(
                {
                    "kind": "bad-env-name",
                    "subject": name,
                    "detail": f"env {entry['env']!r} is not an environment variable "
                    "name ([A-Z_][A-Z0-9_]*)",
                }
            )
        if presence_known and name not in stored:
            problems.append(
                {
                    "kind": "no-value",
                    "subject": name,
                    "detail": "catalogued but no stored value — `key rm` then "
                    "`key add` to store one",
                }
            )
    for name in sorted(stored - set(keys)):
        problems.append(
            {
                "kind": "orphan-value",
                "subject": name,
                "detail": "stored value with no catalog entry — `key rm` removes it, "
                "or catalogue it in keys.toml",
            }
        )
    mode_problem = secrets_mode_problem(secrets_path)
    if mode_problem is not None:
        problems.append(
            {"kind": "bad-mode", "subject": str(secrets_path), "detail": mode_problem}
        )
    return problems
