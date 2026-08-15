---
name: odoo-mcporter
description: >-
  Access Odoo through the mcporter CLI (locally configured `odoo` MCP server). Use to
  inspect Odoo models, list the schema, or search/fetch records from the terminal instead
  of native MCP tools — best for read-oriented work and narrow, explicit queries.
metadata:
  version: "2026-08-15"
---

# Odoo via mcporter

Use `mcporter` against the local MCP server name `odoo`.

Treat `~/.mcporter/mcporter.json` as the source of truth for connection details. Do not copy secrets from that file into chat, code, logs, or skill files.

## Quick check

Run these in order:

```bash
mcporter --version
mcporter config get odoo --json
mcporter list odoo --schema --json
```

If `config get` or `list` fails, stop and report the config/transport/auth problem instead of guessing.

## Default operating mode

Assume read-only by default.

The current local setup is expected to run with `ODOO_YOLO=read`, which allows broad reads but blocks writes. Do not run create/update/delete flows unless the user explicitly asks and the environment has been intentionally changed for write access.

## Working rules

- Prefer `--output json` or `--json` for machine-readable results.
- Start narrow: specific model, small limit, explicit fields when possible.
- For unknown models, start with `mcporter call odoo.list_models --output json`.
- Avoid broad dumps such as requesting every field unless the user explicitly needs that.
- Never print tokens or API keys. Redact secrets if config inspection is needed.
- If the model name or field names are uncertain, inspect first and only ask the user after trying safe discovery.
- In the current local setup, `mcporter` may append a trailing `[mcporter] stderr ...` block after the JSON payload because the backing Odoo server logs on stderr. Treat the leading JSON object as the real result and clean trailing text before feeding it to strict JSON parsers.

## Common commands

```bash
mcporter call odoo.list_models --output json
mcporter call odoo.search_records model=res.company limit:5 --output json
mcporter call odoo.get_record model=res.company record_id:1 --output json
```

## Field and query hygiene

- Use `search_records` to find candidate rows first.
- Use `get_record` once you know the record ID you want.
- Keep limits small unless the user explicitly wants a broader pull.
- When filtering with a domain expression or selecting fields, quote arguments carefully for `zsh`.

For more shell-safe examples, read `references/examples.md`.
