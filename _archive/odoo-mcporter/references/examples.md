# Examples

Use these as patterns. Keep queries narrow and prefer JSON output.

## Basic discovery

```bash
mcporter --version
mcporter config get odoo --json
mcporter list odoo --schema --json
mcporter call odoo.list_models --output json
```

## Search records

```bash
mcporter call odoo.search_records model=res.company limit:5 --output json
```

With ordering:

```bash
mcporter call odoo.search_records model=res.company limit:5 order:"id asc" --output json
```

With a domain filter (quote carefully in `zsh`):

```bash
mcporter call odoo.search_records \
  model=res.partner \
  domain:'[["is_company", "=", true]]' \
  limit:5 \
  --output json
```

## Fetch a single record

```bash
mcporter call odoo.get_record model=res.company record_id:1 --output json
```

## Narrow fields when supported by the tool

Prefer small field selections instead of asking for everything.

```bash
mcporter call odoo.get_record \
  model=res.company \
  record_id:1 \
  fields:'["name", "email", "phone"]' \
  --output json
```

## JSON parsing note

In the current local setup, `mcporter` may append a trailing diagnostic block that starts with `[mcporter] stderr ...` after the JSON payload. If you need strict parsing, strip everything after the first complete JSON document before piping to `jq` or another parser.

## Failure handling

If `mcporter list odoo --schema --json` fails:

1. check that `mcporter` is on `PATH`
2. check that `~/.mcporter/mcporter.json` contains an `mcpServers.odoo` entry
3. check that the backing command still exists (`/Users/<your-username>/.local/bin/uvx` in the current setup)
4. report the exact error instead of guessing
