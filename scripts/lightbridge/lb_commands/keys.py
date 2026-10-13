"""Key command handlers; catalog and secret storage remain owned by lb_keys."""

from __future__ import annotations

import getpass
import json
import os
import subprocess
import sys
from pathlib import Path

from lb_keys import (
    ENV_NAME,
    KEY_NAME,
    KEYS_HEADER,
    SECRETS_DENIED,
    SECRETS_HEADER,
    append_key,
    append_secret,
    load_keys,
    load_secret_names,
    load_secrets,
    remove_key,
    remove_secret,
    write_secrets,
)
from lb_keys import audit as keys_audit
from lb_style import paint, row

# ── keys ────────────────────────────────────────────────────────────────────


def _open_keys(keys_file: str) -> tuple[dict | None, Path, str | None]:
    """The shared key-catalog preamble: expanded path + parsed catalog (or its error)."""
    keys_path = Path(keys_file).expanduser()
    catalog, error = load_keys(keys_path)
    if error is not None:
        print(f"key catalog is unusable: {keys_path}\n{error}", file=sys.stderr)
    return catalog, keys_path, error


def _key_json(keys_path: Path, action: str, name: str, entry: dict | None) -> str:
    """The one JSON shape every key write verb prints — never a value field."""
    return json.dumps(
        {"keys": str(keys_path), "action": action, "name": name, "entry": entry},
        indent=2,
    )


ADD_USAGE = "key add NAME --provider P --env VAR --scope TEXT"


def cmd_key_ls(keys_file: str, secrets_file: str, json_out: bool) -> int:
    catalog, keys_path, error = _open_keys(keys_file)
    if error is not None:
        return 1
    if catalog is None:
        print(f"no key catalog: {keys_path}  (add one: `{ADD_USAGE}`)")
        return 0
    stored, sec_error = load_secret_names(Path(secrets_file).expanduser())
    if sec_error is not None:
        print(
            f"note: secrets file unusable ({sec_error}) — value presence unknown.",
            file=sys.stderr,
        )

    if json_out:
        print(
            json.dumps(
                {
                    "keys": str(keys_path),
                    "entries": {
                        name: {
                            **entry,
                            "has_value": (name in stored)
                            if sec_error is None
                            else None,
                        }
                        for name, entry in catalog.items()
                    },
                },
                indent=2,
            )
        )
        return 0
    if not catalog:
        print(f"{keys_path}: no keys catalogued  (add one: `{ADD_USAGE}`)")
        return 0
    names = sorted(catalog)
    widths = [
        max(len(name) for name in names),
        max(len(catalog[n]["provider"] or "?") for n in names),
        max(len(catalog[n]["env"] or "?") for n in names),
    ]
    for name in names:
        entry = catalog[name]
        missing = ""
        if sec_error is None and (stored is None or name not in stored):
            missing = "   ← NO VALUE"
        print(
            f"{name:<{widths[0]}}  {(entry['provider'] or '?'):<{widths[1]}}  "
            f"{(entry['env'] or '?'):<{widths[2]}}  {entry['scope'] or '?'}{missing}"
        )
    return 0


def cmd_key_add(
    name: str,
    provider: str,
    env: str,
    scope: str,
    keys_file: str,
    secrets_file: str,
    json_out: bool,
) -> int:
    if not KEY_NAME.match(name):
        print(
            f"invalid key name {name!r} — letters, digits, '-', '_' only.",
            file=sys.stderr,
        )
        return 2
    if not ENV_NAME.match(env):
        print(
            f"invalid env var name {env!r} — [A-Z_][A-Z0-9_]* (e.g. OPENAI_API_KEY).",
            file=sys.stderr,
        )
        return 2
    catalog, keys_path, error = _open_keys(keys_file)
    if error is not None:
        return 1
    if catalog is not None and name in catalog:
        print(
            f"{name!r} is already catalogued → ${catalog[name]['env']}\n"
            f"`key rm {name}` first — values are write-only, so re-adding is how you rotate.",
            file=sys.stderr,
        )
        return 1
    secrets_path = Path(secrets_file).expanduser()
    stored, sec_error = load_secret_names(secrets_path)
    if sec_error is not None:
        print(f"secrets file is unusable: {secrets_path}\n{sec_error}", file=sys.stderr)
        return 1
    if stored is not None and name in stored:
        print(
            f"a stored value for {name!r} already exists (no catalog entry — an orphan).\n"
            f"`key rm {name}` removes it, then re-add.",
            file=sys.stderr,
        )
        return 1

    # The value never transits argv or any output — hidden prompt on a TTY, piped
    # stdin otherwise (`pbpaste | lb key add ...`).
    if sys.stdin.isatty():
        value = getpass.getpass(f"value for {name} (hidden): ")
    else:
        value = sys.stdin.read().strip()
    if not value:
        print("empty value — nothing stored.", file=sys.stderr)
        return 1

    # Secrets first: a failed secret write must not leave catalog metadata pointing at
    # nothing (the reverse orphan is harmless and doctor-visible).
    secrets_path.parent.mkdir(parents=True, exist_ok=True)
    secrets_text = (
        secrets_path.read_text(encoding="utf-8")
        if secrets_path.is_file()
        else SECRETS_HEADER
    )
    write_secrets(secrets_path, append_secret(secrets_text, name, value))
    keys_text = (
        keys_path.read_text(encoding="utf-8") if keys_path.is_file() else KEYS_HEADER
    )
    keys_path.parent.mkdir(parents=True, exist_ok=True)
    keys_path.write_text(
        append_key(keys_text, name, provider, env, scope), encoding="utf-8"
    )

    entry = {"provider": provider, "env": env, "scope": scope}
    if json_out:
        print(_key_json(keys_path, "added", name, entry))
        return 0
    print(row("updated", str(keys_path)))
    print(row("added", f"{name}  {provider} → ${env}"))
    print(row("value", f"stored (never printed) — use it: `key run {name} -- CMD`"))
    return 0


RUN_USAGE = "key run NAME[,NAME...] -- CMD..."


def cmd_key_run(
    names_raw: str, cmd: list[str], keys_file: str, secrets_file: str
) -> int:
    """Inject the named values into a child env and exec CMD — the values' only exit
    from the store. Never prints one; the child's own exit code passes through
    untranslated, and a failed exec is 127 (the `env(1)` convention)."""
    names = list(dict.fromkeys(n.strip() for n in names_raw.split(",") if n.strip()))
    if not cmd or not names:
        print(f"usage: {RUN_USAGE}", file=sys.stderr)
        return 2
    catalog, keys_path, error = _open_keys(keys_file)
    if error is not None:
        return 1
    if catalog is None:
        print(f"no key catalog: {keys_path}\nAdd one: `{ADD_USAGE}`.", file=sys.stderr)
        return 1
    unknown = [n for n in names if n not in catalog]
    if unknown:
        print(f"not catalogued: {', '.join(unknown)} — see `key ls`.", file=sys.stderr)
        return 1
    env_owner: dict[str, str] = {}  # env var → the selected name injecting it
    for name in names:
        var = catalog[name]["env"]
        if var is None:
            print(f"{name!r} has no usable `env` — see `key doctor`.", file=sys.stderr)
            return 1
        if var in env_owner:
            print(
                f"{env_owner[var]} and {name} both inject ${var} — pick one per run.",
                file=sys.stderr,
            )
            return 1
        env_owner[var] = name
    secrets_path = Path(secrets_file).expanduser()
    values, sec_error = load_secrets(secrets_path)
    if sec_error == SECRETS_DENIED:
        print(
            f"{secrets_path}: {sec_error}.\n"
            f"Agents: ask the user to approve a sandbox-disabled run — every use of a "
            f"key stays a human-approved act.",
            file=sys.stderr,
        )
        return 1
    if sec_error is not None:
        print(f"secrets file is unusable: {secrets_path}\n{sec_error}", file=sys.stderr)
        return 1
    missing = [n for n in names if n not in (values or {})]
    if missing:
        print(
            f"no stored value for: {', '.join(missing)} — catalogued but valueless.\n"
            f"Rotate one in: `key rm NAME` then `key add NAME ...` (see `key doctor`).",
            file=sys.stderr,
        )
        return 1
    child_env = {**os.environ, **{var: values[name] for var, name in env_owner.items()}}
    if os.name != "nt":
        try:
            os.execvpe(cmd[0], cmd, child_env)  # never returns on success
        except OSError as exc:
            print(f"cannot exec {cmd[0]!r}: {exc}", file=sys.stderr)
            return 127
    proc = subprocess.run(cmd, env=child_env)
    return proc.returncode


def cmd_key_rm(name: str, keys_file: str, secrets_file: str, json_out: bool) -> int:
    catalog, keys_path, error = _open_keys(keys_file)
    if error is not None:
        return 1
    secrets_path = Path(secrets_file).expanduser()
    stored, sec_error = load_secret_names(secrets_path)
    if sec_error is not None:
        print(f"secrets file is unusable: {secrets_path}\n{sec_error}", file=sys.stderr)
        return 1
    in_catalog = catalog is not None and name in catalog
    has_value = stored is not None and name in stored
    if not in_catalog and not has_value:
        print(f"{name!r} is not catalogued — see `key ls`.", file=sys.stderr)
        return 1

    if in_catalog:
        text = remove_key(keys_path.read_text(encoding="utf-8"), name)
        if text is None:
            print(
                f"couldn't find {name!r}'s block in {keys_path} — a shape this tool "
                f"doesn't manage; edit the file directly.",
                file=sys.stderr,
            )
            return 1
        keys_path.write_text(text, encoding="utf-8")
    if has_value:
        text = remove_secret(secrets_path.read_text(encoding="utf-8"), name)
        if text is None:
            print(
                f"couldn't find {name!r}'s line in {secrets_path} — a shape this tool "
                f"doesn't manage; edit the file directly.",
                file=sys.stderr,
            )
            return 1
        write_secrets(secrets_path, text)

    if json_out:
        print(_key_json(keys_path, "removed", name, None))
        return 0
    print(row("updated", str(keys_path)))
    removed = name if in_catalog else f"{name} (orphan value only)"
    print(
        row(
            "removed",
            f"{removed}{' + stored value' if in_catalog and has_value else ''}",
        )
    )
    return 0


def cmd_key_doctor(keys_file: str, secrets_file: str, json_out: bool) -> int:
    """Audit the catalog/values pair. Absent files are the not-opted-in state, not a
    problem — an empty audit of nothing is clean."""
    keys_path = Path(keys_file).expanduser()
    secrets_path = Path(secrets_file).expanduser()
    catalog, keys_error = load_keys(keys_path)
    stored, sec_error = load_secret_names(secrets_path)
    # Absent secrets = knowledge ([] → valueless keys are findings); denied/unreadable
    # = ignorance (None → value-presence checks skipped, see below).
    if stored is None and sec_error is None:
        stored = []
    problems = keys_audit(catalog or {}, stored, secrets_path)
    if sec_error == SECRETS_DENIED:
        # The environment, not the file, is refusing — expected under an agent
        # sandbox; a note, never a problem (doctor must not cry rot in every session).
        print(f"note: {secrets_path}: {sec_error}; values unaudited.", file=sys.stderr)
    elif sec_error is not None:
        problems.insert(
            0,
            {"kind": "bad-secrets", "subject": str(secrets_path), "detail": sec_error},
        )
    if keys_error is not None:
        problems.insert(
            0, {"kind": "bad-keys", "subject": str(keys_path), "detail": keys_error}
        )
    if json_out:
        print(
            json.dumps(
                {
                    "keys": str(keys_path),
                    "secrets": str(secrets_path),
                    "problems": problems,
                },
                indent=2,
            )
        )
    elif not problems:
        print(f"key doctor: {keys_path} — {paint('no problems.', 'ok')}")
    else:
        print(
            f"key doctor: {paint(f'{len(problems)} problem(s)', 'bad')} in {keys_path}:"
        )
        for problem in problems:
            kind = paint(f"[{problem['kind']}]", "warn")
            print(f"- {kind} {problem['subject']}: {problem['detail']}")
    return 1 if problems else 0
