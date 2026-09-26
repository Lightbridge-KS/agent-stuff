---
summary: Progress tracker for moving the `image-gen` skill (plugins/creative) from gpt-image-2 to
  GPT Image 2.5 — one model everywhere (Sunburst), default quality `high`, driver `gpt-6-sol`,
  tool model pinned in `iterate`, new `xhigh`/`max` tiers gated locally. Milestones with SHAs;
  live-smoke evidence; Deferred; Confirmed contracts.
read_when:
  - changing imagegen.py defaults, the quality ladder, or the cost figures in SKILL.md / api.md
  - deciding whether to split the model default per verb (Flare for generate)
  - a new GPT Image model or quality tier ships and the skill needs re-pointing
---

# image-gen → GPT Image 2.5 — progress

Origin: OpenAI released `gpt-image-2.5-sunburst` and `gpt-image-2.5-flare` on 2026-09-08 and
now says "for new integrations, use one of the GPT Image 2.5 models". The skill's cost
figures were off for 2.5 (the token ladder is remapped), `iterate` never pinned the image
model on the Responses tool, and the driver id `gpt-5.6` had disappeared from the docs.
Seeded from Claude plan `jaunty-toasting-puffin` (2026-09-26).

Decisions (KS, 2026-09-26):

- **One model everywhere → Sunburst.** Same price per token as Flare per the docs calculator;
  Flare is a `--model` hint in the preset table for fixtures, bulk, and slide art. A per-verb
  split (Flare on `generate`) was rejected for simplicity unless a live latency gap shows.
- **Default quality `high`** — the same dollars as the old `medium` default (~$0.05 at 1024²).
- **Driver `gpt-6-sol`** ($2 / $10 per M) — the docs' example driver `gpt-6-astra` costs 5×
  for a job that is only prompt revision plus one tool call.

## Milestones

- [x] `scripts/imagegen.py`: `openai>=3.19`, Sunburst default, `xhigh`/`max` in the enum with a
      local guard (exit 2 on non-2.5 models), `iterate --model` pinned on the tool and recorded
      in the sidecar (old sidecars upgraded in place), driver `gpt-6-sol` — (this PR)
- [x] `tests/test_imagegen.py`: 12 offline tests incl. the guard, tool-model pinning, and the
      old-shape sidecar continuation — (this PR)
- [x] SKILL.md, `references/api.md` (cost ladder from the docs calculator), `references/prompting.md`
      — (this PR)
- [x] `uv run bin/validate.py` + `uv run tests/test_imagegen.py` green — 2026-09-26
- [x] `just test` (whole suite, 22 files) green — 2026-09-26
- [x] Live smoke (user-approved, sandbox-disabled `lb key run openai-image-gen -- …`) — 2026-09-26, see below
- [ ] Landed

## Live smoke

Record: `_playground/2026-09-26_image-gen-2.5-smoke/NOTES.md` (gitignored). Every image
was read back.

| Call | Model | Quality | Size | Output tokens | $ | Wall time | Read-back |
|---|---|---|---|---|---|---|---|
| generate (transparent logo) | sunburst | high | 1024x1024 | 1756 | 0.053 | 33 s | ok |
| generate (same prompt) | flare | high | 1024x1024 | 1756 | 0.053 | 20 s | ok |
| edit (recolor, transparent) | sunburst | high | auto | 2058 (+1074 in) | 0.070 | 32 s | only the asked change |
| iterate t1 → t2 | sunburst via gpt-6-sol | high | 1024x1024 | driver ~100/turn; image tokens not itemized | — | 29 s / 28 s | text exact, chain intact |
| iterate on old-shape sidecar | sunburst via gpt-6-sol | high | 1024x1024 | as above | — | 30 s | chain ok, `image_model` written in place; one unasked color drift (see NOTES) |

Observations: Sunburst and Flare consumed identical tokens (the calculator's number), so the
same-price claim holds; Flare was ~1.7× faster on one sample. Responses `usage` reports only
the driver's tokens, so `iterate` image cost is invisible in `--json`. Transparent `generate`
outputs peak at alpha 254 (edit outputs reach 255); edges are crisp either way.

## Now / Next

- Draft PR open; land after review, then `bin/install.py --claude` re-sync is a no-op (symlink).

## Deferred

- **Per-verb model split** (`generate` → Flare): smoke showed equal cost and Flare ~1.7×
  faster on one-shot generate (20 s vs 33 s, n=1). Kept single-default for simplicity; reopen
  if agent workflows feel latency-bound on `generate`.
- **`partial_images` streaming** — 100 extra output tokens per frame; no agent use case yet.
- **`input_fidelity`** — docs are silent for 2.5; stays unexposed until documented.
- **`--model` short aliases** (`sunburst`, `flare`) — not worth a mapping while there are two.

## Confirmed contracts

- Exit codes unchanged: 0 ok · 2 params (validated before spend, incl. the `xhigh`/`max`
  guard) · 3 moderation/user error · 4 auth/quota/network.
- `iterate` always sends `model` on the `image_generation` tool; the sidecar carries
  `driver_model` and `image_model`, both reused on continuation unless overridden. A
  sidecar's stored `driver_model` is never rewritten mid-chain.
- Size constraints are the same for gpt-image-2 and 2.5 and stay validated locally.
- `--json` payloads now include `model` on every verb.
