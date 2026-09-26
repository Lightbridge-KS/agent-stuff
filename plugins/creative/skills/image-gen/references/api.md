# GPT Image 2.5 API facts

Distilled from the [Image generation guide](https://developers.openai.com/api/docs/guides/image-generation), the model pages, and the changelog (fetched 2026-09-26). The CLI (`scripts/imagegen.py`) wraps all of this; this file explains the knobs and their consequences.

## Models

Released 2026-09-08 (dated snapshots `-2026-09-08`); the guide says "for new
integrations, use one of the GPT Image 2.5 models".

| Model | OpenAI's positioning | CLI |
|---|---|---|
| `gpt-image-2.5-sunburst` | "our most capable model for image generation and editing" — "editing precision matters most" | default on every verb |
| `gpt-image-2.5-flare` | "fast, high-quality everyday image generation" | `--model gpt-image-2.5-flare` |
| `gpt-image-2` | previous generation; still served, not deprecated | `--model gpt-image-2` (quality ≤ `high`) |

Both 2.5 models bill at the same token rates as gpt-image-2 and the docs' calculator
uses one token table for them, so at equal quality and size they cost the same; they
differ in latency (Flare) and edit fidelity (Sunburst). The docs do warn that "token
consumption can differ by model" — read `usage` in `--json` to see what a run cost.
`gpt-image-1-mini`, `gpt-image-1.5` and `chatgpt-image-latest` retire 2026-12-01.

## Two APIs, one nuance

- **Image API** (`generate`, `edit` verbs): you pick the image model directly via
  `--model`.
- **Responses API** (`iterate` verb): a mainline *driver* model (default `gpt-6-sol`,
  $2 / $10 per M tokens; lists `image_generation` as a supported tool) carries the
  `image_generation` tool. The CLI **pins the image model on the tool** — omitted, the
  tool falls back to an older GPT Image model, not to 2.5. Turns chain server-side via
  `previous_response_id` (stored in the session sidecar with `driver_model` and
  `image_model`), so each refinement sees the full visual context. The driver
  auto-revises your prompt (`revised_prompt` in `--json` — read it to understand what
  was actually rendered). Driver tokens bill on top of image tokens; `gpt-6-astra`
  (the docs' example driver) costs 5× more for the same job.
- The tool's `action` param: `auto` (model decides generate-vs-edit), `generate`,
  `edit` — exposed as `--action`.

## Size

Same rules for 2 and 2.5: both edges multiples of **16px**, max edge **≤3840px**,
ratio **≤3:1**, total pixels **655,360–8,294,400**. The CLI validates locally (exit 2)
before spending. Square is fastest. Recommended: `1024x1024`, `1536x1024` (landscape),
`1024x1536` (portrait); `auto` (default — model picks from the prompt). Outputs above
2560x1440 are experimental. A larger non-square size can cost *fewer* output tokens
than a smaller square one.

## Quality × cost (per image, output tokens only, $30 / M)

Derived from the guide's cost calculator (base tokens per quality tier, scaled by
size). `xhigh` and `max` exist only on 2.5 — the CLI refuses them on other models
(exit 2). Both models default to `auto` on the API; the CLI defaults to `high` for
predictable spend.

| Quality | 2.5 @ 1024x1024 | 2.5 @ 1536x1024 / 1024x1536 | gpt-image-2 @ 1024x1024 | Use for |
|---|---|---|---|---|
| `low` | ~$0.006 | ~$0.005 | ~$0.006 | fixtures, thumbnails, bulk |
| `medium` | ~$0.013 | ~$0.010 | ~$0.053 | drafts, first looks |
| `high` (CLI default) | ~$0.053 | ~$0.041 | ~$0.211 | most real assets |
| `xhigh` | ~$0.094 | ~$0.074 | — | finals with small text / fine detail |
| `max` | ~$0.211 | ~$0.165 | — | when `xhigh` still misses |

Note the remap: 2.5 `high` costs what gpt-image-2 `medium` did, and 2.5 `max` costs what
gpt-image-2 `high` did. Plus input text tokens ($5 / M) and input *image* tokens ($8 / M,
$2 / M when cached) for edits and reference-heavy prompts. `input_fidelity` is not
exposed: the docs say omit it for gpt-image-2 (always high fidelity) and say nothing
for 2.5. Latency: complex prompts up to ~2 min; `low`, `jpeg`, and Flare are the fast
paths. Streaming `partial_images` (not exposed) costs 100 extra output tokens each.

## Format & background

- Formats: `png` (default), `jpeg` (fastest — prefer when latency matters), `webp`.
- `--compression 0–100` applies to jpeg/webp only.
- `--background transparent`: png/webp only — jpeg has no alpha. `size`, `quality`,
  `background` all accept `auto`.

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
