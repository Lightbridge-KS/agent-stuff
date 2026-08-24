# gpt-image-2 API facts

Distilled from the [Image generation guide](https://developers.openai.com/api/docs/guides/image-generation) (fetched 2026-08-24). The CLI (`scripts/imagegen.py`) wraps all of this; this file explains the knobs and their consequences.

## Two APIs, one nuance

- **Image API** (`generate`, `edit` verbs): you pick the image model directly — pinned
  to `gpt-image-2` (`--model` overrides).
- **Responses API** (`iterate` verb): a mainline *driver* model (default `gpt-5.6`)
  carries the `image_generation` tool; the **tool selects its own GPT Image model** —
  no pinning. Turns chain server-side via `previous_response_id` (stored in the session
  sidecar), so each refinement sees the full visual context. The driver auto-revises
  your prompt (`revised_prompt` in `--json` — read it to understand what was actually
  rendered). Driver tokens bill on top of image tokens.
- The tool's `action` param: `auto` (model decides generate-vs-edit), `generate`,
  `edit` — exposed as `--action`.

## Size

`gpt-image-2` accepts any resolution satisfying: both edges multiples of **16px**, max
edge **≤3840px**, ratio **≤3:1**, total pixels **655,360–8,294,400**. The CLI validates
locally (exit 2) before spending. Square is fastest. Popular: `1024x1024`, `1536x1024`
(landscape), `1024x1536` (portrait), `2048x2048`, `3840x2160` (4K), `auto` (default —
model picks from the prompt). Outputs beyond 2560x1440 total are experimental. A larger
non-square size can cost *fewer* output tokens than a smaller square one.

## Quality × cost (per image, output tokens only)

| Quality | 1024x1024 | 1024x1536 / 1536x1024 | Use for |
|---|---|---|---|
| `low` | ~$0.006 | ~$0.005 | drafts, thumbnails, fixtures, bulk |
| `medium` (CLI default) | ~$0.053 | ~$0.041 | most real assets |
| `high` | ~$0.211 | ~$0.165 | finals with small text / fine detail |

Plus input text tokens, and input *image* tokens for edits — gpt-image-2 always
processes image inputs at **high fidelity** (no `input_fidelity` param), so
reference-heavy edits cost more input tokens. Latency: complex prompts up to ~2 min;
`low` and `jpeg` are the fast paths.

## Format & background

- Formats: `png` (default), `jpeg` (fastest — prefer when latency matters), `webp`.
- `--compression 0–100` applies to jpeg/webp only.
- `--background transparent` (preview feature): png/webp only — jpeg has no alpha.
  `size`, `quality`, `background` all accept `auto`.

## Edits endpoint

`edit` sends local file(s) + prompt: multiple `-i` inputs act as references
(compositing); `--mask` is a PNG whose **transparent areas get replaced** (inpainting,
applies to the first input; must match its dimensions). A black/white mask needs its
alpha channel filled from the mask values first.

## Errors

- `moderation_blocked` (may carry `moderation_details`) and
  `image_generation_user_error` → CLI exit 3: **change the prompt/inputs, never retry
  as-is**. The `moderation` API param (`auto`/`low`) exists; the CLI keeps `auto`.
- 429/5xx are retryable; the SDK retries transient failures itself.
- `iterate` returning text-but-no-image (driver asked a question or declined) → exit 3
  with the driver's message; rephrase or force `--action generate`.

## Limitations

Precise text placement can still fail (verify on read-back); character/brand
consistency drifts across generations (repeat the preserve-list, or keep one `iterate`
session); precise layout in structured compositions is best-effort.
