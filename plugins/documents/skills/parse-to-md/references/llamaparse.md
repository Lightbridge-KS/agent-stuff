# LlamaParse (cloud) reference

Highest-quality parsing for complex layouts — **uploads the document to Llama Cloud**;
route here only past the sensitivity gate. Requires the key injected per invocation by
`lb key run llama-cloud-personal -- ...` (`llm-keys` skill — never read, print, or ask
for the value), the `@llamaindex/llama-cloud` npm package (global install works), and
network access to `api.cloud.llamaindex.ai`.

## Bundled CLI — `scripts/llamaparse.cjs`

The deterministic shell for normal jobs. Prefer it over ad-hoc scripts.

```bash
lb key run llama-cloud-personal -- node scripts/llamaparse.cjs health
# {"node":..., "apiKey":true, "package":true}
lb key run llama-cloud-personal -- node scripts/llamaparse.cjs parse "in.pdf" -o out.md
```

Run without `lb key run` and both verbs exit 1 with `no key injected` and the command to
retry — the key is never exported into a shell.

| Flag | Default | Notes |
|---|---|---|
| `--output, -o <path>` | `<input>.llamaparse.<ext>` beside input | |
| `--format markdown\|text\|json` | `markdown` | |
| `--tier <tier>` | `agentic` | see tier table |
| `--version <v>` | `latest` | LlamaParse API version |
| `--prompt <text>` | — | custom extraction prompt (translate, summarize, guide extraction) |
| `--tables-as-markdown <bool>` | `true` | |
| `--annotate-links <bool>` | `true` | |
| `--pretty-json` | off | with `--format json` |
| `--quiet` | off | |

Exit 0 on success with a JSON summary on stdout (`outputPath`, `bytes`, `fileId`, `tier`,
`format`); exit 1 with `ERROR:` on stderr otherwise. Set `LLAMAPARSE_DEBUG=1` for stack
traces. Expect ~1–2 minutes wall clock for a few pages on the agentic tier.

## Tiers

| Tier | When |
|---|---|
| `fast` | speed over fidelity; simple documents |
| `cost_effective` | budget-conscious plain extraction |
| `agentic` | complex layouts, tables, mixed content — **default** |
| `agentic_plus` | highest accuracy, most expensive |

## TypeScript escape hatch

For jobs the CLI can't express — image extraction, per-page metadata, batch
orchestration, custom post-processing — write a one-off script and run it under the same
injection: `lb key run llama-cloud-personal -- npx tsx script.ts`. The script reads the
standard `LLAMA_CLOUD_API_KEY` variable and stays ignorant of the key's name.
Docs: <https://developers.llamaindex.ai/python/cloud/llamaparse/api-v2-guide/>

Core pattern (always two steps — upload for a `file_id`, then parse; never pass raw bytes):

```typescript
import LlamaCloud from "@llamaindex/llama-cloud";
import { readFile } from "fs/promises";
import { basename } from "path";

const client = new LlamaCloud({ apiKey: process.env["LLAMA_CLOUD_API_KEY"] });

const buffer = await readFile(filePath);
const fileObj = await client.files.create({
  file: new File([buffer], basename(filePath)),
  purpose: "parse",
});

const result = await client.parsing.parse({
  tier: "agentic",
  version: "latest",
  file_id: fileObj.id,
  expand: ["markdown_full"],           // REQUIRED — omitting returns minimal data
});
const markdown = result.markdown_full ?? "";   // fields may be undefined on failure
```

Notes for scripts:

- `expand` values: `text_full`, `markdown_full`, `items` (page-level JSON), plus
  `*_content_metadata` variants (per-page detail, image presigned URLs) — request only
  what's needed; metadata variants inflate the payload.
- Advanced options group under `input_options`, `output_options`, `processing_options`
  (e.g. `ocr_parameters: { languages: [...] }`), and `agentic_options.custom_prompt`.
- Downloading extracted images: fetch each `presigned_url` from
  `images_content_metadata` with `Authorization: Bearer <key>`.
