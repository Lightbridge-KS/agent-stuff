---
name: image-gen
description: >-
  Generate or edit images with OpenAI gpt-image-2 via the bundled CLI — logos,
  website/presentation assets, infographics, test fixtures, photo-real scenes,
  UI mockups, image editing/compositing. Use when asked to generate, create, or
  edit an image, or when a task needs an image asset produced.
metadata:
  version: "2026-08-24"
---

# Image generation (gpt-image-2)

Drive the bundled deterministic CLI; you supply the reasoning — use-case triage, prompt
crafting, and **visual verification** (Read every output image back before deciding the
next move). Never hand-write OpenAI client code for image tasks.

`<skill_dir>` below = the directory this SKILL.md was read from. Every run needs the
API key injected (see *Key & sandbox*):

```bash
lb key run openai-image-gen -- uv run <skill_dir>/scripts/imagegen.py <verb> ...
```

## Router

```
need an image
 ├─ single asset, likely right in 1–2 shots ─────► generate   (Image API; cheapest)
 ├─ expect visual back-and-forth (logo, hero,
 │  infographic worth refining) ─────────────────► iterate    (Responses API; native multi-turn,
 │                                                             + driver-model tokens per turn)
 └─ transform an EXISTING local file
    (mask, references, compositing, style) ──────► edit       (Image API edits)
```

## Presets by use case

| Use case | Call | Recipe |
|---|---|---|
| Logo | `--size 1024x1024 --background transparent` png, `-n 4` variants | [prompting.md §logo](references/prompting.md) |
| Website hero / banner | `--size 1536x1024` (or wider, ≤3:1) | §photoreal or §marketing |
| Presentation slide art | `--size 1536x1024 --format jpeg` (fastest) | §slides |
| Infographic / diagram | `--size 1024x1536 --quality high` (small text needs it) | §infographic |
| UI mockup | `--size 1024x1536` portrait | §ui-mockup |
| Test fixture / bulk | `--quality low --size 1024x1024` — never more | §none needed |
| Photo-real scene | defaults; say "photorealistic" in the prompt | §photoreal |
| Product cutout / composite | `edit -i ...` (+`--background transparent`) | §product, §multi-image |

## Workflow contract

1. Draft the prompt in order: **scene → subject → key details → constraints** (state the
   intended use: "logo", "pitch-deck slide" — it sets the model's polish mode).
2. Run the verb from the router. Quality defaults to `medium` (~$0.04); pass
   `--quality low` (~$0.005) for drafts/fixtures/bulk, `high` (~$0.17) only for finals
   with small text or fine detail.
3. **Read the output image** (multimodal). Check: matches request? text spelled right?
   layout sane? If not →
4. Refine — one change per turn (`iterate` continues the session; `edit` for local
   files). Always repeat the preserve-list: "change only X, keep everything else the same".
5. Final render: bump quality once, verify once, deliver. Session sidecars and draft
   images are scratch artifacts — playground/temp, never committed.

```bash
# one-shot
lb key run openai-image-gen -- uv run <skill_dir>/scripts/imagegen.py \
  generate "A minimal flat-design fox logo..." -o logo.png \
  --size 1024x1024 --background transparent -n 4

# iterative session (sidecar JSON chains the turns; created on first use)
... imagegen.py iterate "Thicker strokes, warmer orange" -o v2.png --session fox.json

# edit an existing file (mask: transparent areas get replaced)
... imagegen.py edit "Remove the background" -i photo.png -o cutout.png --background transparent
```

`--json` on any verb returns paths, usage tokens, `revised_prompt`, and (iterate) the
`response_id`. Exit codes teach: 0 ok · 2 fix params (validated before spending) ·
3 moderation/user-error — **rewrite, don't retry** · 4 auth/quota/network.

Depth: [references/prompting.md](references/prompting.md) (fundamentals + per-use-case
recipes) · [references/api.md](references/api.md) (sizes, params, sessions, costs, errors).

## Key & sandbox

- Key access **only** via `lb key run openai-image-gen -- ...` (`llm-keys` skill). Never
  read, print, or ask for the key value.
- Expect two sandbox refusals, both by design: `api.openai.com` is not in the network
  allowlist, and `lb key run` is refused under the secrets deny. Each generation is
  therefore a **user-approved, sandbox-disabled invocation** — not an error to debug.
- Cost awareness: `iterate` bills driver-model tokens on top of image tokens, and image
  inputs are always processed at high fidelity (edits with references cost more input
  tokens). Latency: complex prompts can take up to ~2 min.
