#!/usr/bin/env node

const { existsSync } = require("fs");
const { readFile, writeFile } = require("fs/promises");
const os = require("os");
const path = require("path");

const ALLOWED_TIERS = new Set(["fast", "cost_effective", "agentic", "agentic_plus"]);
const ALLOWED_FORMATS = new Set(["markdown", "text", "json"]);
const SKILL_DIR = path.resolve(__dirname, "..");
const NODE_PATH_MODULE_ROOTS = (process.env.NODE_PATH || "")
  .split(path.delimiter)
  .map((entry) => entry.trim())
  .filter(Boolean);
const MODULE_SEARCH_ROOTS = [
  path.join(SKILL_DIR, "node_modules"),
  path.join(process.cwd(), "node_modules"),
  ...NODE_PATH_MODULE_ROOTS,
  "/opt/homebrew/lib/node_modules",
  "/usr/local/lib/node_modules",
];

function usage(exitCode = 0) {
  const stream = exitCode === 0 ? process.stdout : process.stderr;
  stream.write(`LlamaParse CLI

Usage (always via lb key run — it injects the key):
  lb key run llama-cloud-personal -- node scripts/llamaparse.cjs health
  lb key run llama-cloud-personal -- node scripts/llamaparse.cjs parse <input-file> [options]

Parse options:
  --output, -o <path>              Output path. Defaults beside input.
  --format <markdown|text|json>    Output format. Default: markdown.
  --tier <tier>                    fast, cost_effective, agentic, agentic_plus. Default: agentic.
  --version <version>              LlamaParse API version. Default: latest.
  --prompt <text>                  Custom extraction prompt.
  --tables-as-markdown <bool>      Preserve tables as markdown. Default: true.
  --annotate-links <bool>          Annotate links in markdown. Default: true.
  --pretty-json                    Pretty-print JSON output.
  --quiet                          Suppress progress logs.

Key: injected per invocation by lb key run llama-cloud-personal (llm-keys skill).
Never paste or export a key value.

Examples (prefix each with: lb key run llama-cloud-personal --):
  node scripts/llamaparse.cjs parse ~/Downloads/paper.pdf
  node scripts/llamaparse.cjs parse paper.pdf --output paper.md
  node scripts/llamaparse.cjs parse paper.pdf --format text
  node scripts/llamaparse.cjs parse paper.pdf --format json --pretty-json
`);
  process.exit(exitCode);
}

function log(args, message) {
  if (!args.quiet) {
    process.stderr.write(`${message}\n`);
  }
}

function fail(message, error) {
  process.stderr.write(`ERROR: ${message}\n`);
  if (error && process.env.LLAMAPARSE_DEBUG) {
    process.stderr.write(`${error.stack || error}\n`);
  }
  process.exit(1);
}

function parseBool(value, name) {
  if (typeof value === "boolean") return value;
  const normalized = String(value).toLowerCase();
  if (["true", "1", "yes", "y"].includes(normalized)) return true;
  if (["false", "0", "no", "n"].includes(normalized)) return false;
  fail(`${name} must be true or false.`);
}

function loadLlamaCloud() {
  try {
    return require("@llamaindex/llama-cloud").default;
  } catch (firstError) {
    let lastError = firstError;
    for (const moduleRoot of MODULE_SEARCH_ROOTS) {
      const packageDir = path.join(moduleRoot, "@llamaindex", "llama-cloud");
      if (!existsSync(packageDir)) continue;
      try {
        return require(packageDir).default;
      } catch (error) {
        lastError = error;
      }
    }
    fail(
      "Cannot load @llamaindex/llama-cloud. Install it globally with `npm install -g @llamaindex/llama-cloud@latest` or locally in the current project.",
      lastError
    );
  }
}

function parseArgs(argv) {
  const [command, ...rest] = argv;
  if (!command || command === "--help" || command === "-h") usage(0);

  const args = {
    command,
    input: null,
    output: null,
    format: "markdown",
    tier: "agentic",
    version: "latest",
    prompt: null,
    tablesAsMarkdown: true,
    annotateLinks: true,
    prettyJson: false,
    quiet: false,
  };

  if (command === "health") {
    if (rest.includes("--quiet")) args.quiet = true;
    return args;
  }

  if (command !== "parse") {
    fail(`Unknown command: ${command}`);
  }

  while (rest.length) {
    const token = rest.shift();
    if (!token) continue;

    if (!token.startsWith("-") && !args.input) {
      args.input = path.resolve(token.replace(/^~(?=$|\/)/, os.homedir()));
      continue;
    }

    switch (token) {
      case "--output":
      case "-o":
        args.output = path.resolve((rest.shift() || "").replace(/^~(?=$|\/)/, os.homedir()));
        break;
      case "--format":
        args.format = rest.shift();
        break;
      case "--tier":
        args.tier = rest.shift();
        break;
      case "--version":
        args.version = rest.shift();
        break;
      case "--prompt":
        args.prompt = rest.shift();
        break;
      case "--tables-as-markdown":
        args.tablesAsMarkdown = parseBool(rest.shift(), "--tables-as-markdown");
        break;
      case "--annotate-links":
        args.annotateLinks = parseBool(rest.shift(), "--annotate-links");
        break;
      case "--pretty-json":
        args.prettyJson = true;
        break;
      case "--quiet":
        args.quiet = true;
        break;
      case "--help":
      case "-h":
        usage(0);
        break;
      default:
        fail(`Unknown option or extra argument: ${token}`);
    }
  }

  if (!args.input) fail("Missing input file.");
  if (!existsSync(args.input)) fail(`Input file not found: ${args.input}`);
  if (!ALLOWED_FORMATS.has(args.format)) fail(`Unsupported format: ${args.format}`);
  if (!ALLOWED_TIERS.has(args.tier)) fail(`Unsupported tier: ${args.tier}`);

  if (!args.output) {
    const ext = args.format === "markdown" ? "md" : args.format === "text" ? "txt" : "json";
    const parsed = path.parse(args.input);
    args.output = path.join(parsed.dir, `${parsed.name}.llamaparse.${ext}`);
  }

  return args;
}

function mimeTypeFor(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  const map = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".html": "text/html",
    ".htm": "text/html",
    ".txt": "text/plain",
    ".md": "text/markdown",
  };
  return map[ext] || "application/octet-stream";
}

async function health(args) {
  const checks = {
    node: process.version,
    apiKey: Boolean(process.env.LLAMA_CLOUD_API_KEY),
    package: false,
  };

  loadLlamaCloud();
  checks.package = true;

  if (!checks.apiKey) {
    process.stderr.write(
      "ERROR: no key injected. Never paste a key — inject it per invocation:\n" +
        "  lb key run llama-cloud-personal -- node scripts/llamaparse.cjs health\n",
    );
    console.log(JSON.stringify(checks));
    process.exit(1);
  }

  log(args, "LlamaParse CLI health check passed.");
  console.log(JSON.stringify(checks));
}

async function parseFile(args) {
  if (!process.env.LLAMA_CLOUD_API_KEY) {
    fail(
      "no key injected. Never paste a key — inject it per invocation:\n" +
        "  lb key run llama-cloud-personal -- node scripts/llamaparse.cjs parse ...",
    );
  }

  const LlamaCloud = loadLlamaCloud();
  const client = new LlamaCloud({
    apiKey: process.env.LLAMA_CLOUD_API_KEY,
  });

  const buffer = await readFile(args.input);
  const file = new File([buffer], path.basename(args.input), {
    type: mimeTypeFor(args.input),
  });

  log(args, `Uploading ${args.input}...`);
  const fileObj = await client.files.create({
    file,
    purpose: "parse",
  });

  const expandByFormat = {
    markdown: ["markdown_full"],
    text: ["text_full"],
    json: ["items"],
  };

  const parseRequest = {
    tier: args.tier,
    version: args.version,
    file_id: fileObj.id,
    output_options: {
      markdown: {
        tables: { output_tables_as_markdown: args.tablesAsMarkdown },
        annotate_links: args.annotateLinks,
      },
    },
    expand: expandByFormat[args.format],
  };

  if (args.prompt) {
    parseRequest.agentic_options = { custom_prompt: args.prompt };
  }

  log(args, `Parsing uploaded file ${fileObj.id} with tier=${args.tier}, format=${args.format}...`);
  const result = await client.parsing.parse(parseRequest);

  let content;
  if (args.format === "markdown") {
    content = result.markdown_full ?? "";
  } else if (args.format === "text") {
    content = result.text_full ?? "";
  } else {
    content = args.prettyJson ? JSON.stringify(result.items ?? {}, null, 2) : JSON.stringify(result.items ?? {});
  }

  if (!String(content).trim()) {
    fail(`LlamaParse returned empty ${args.format} output.`);
  }

  await writeFile(args.output, content, "utf8");
  log(args, `Wrote ${args.output}`);
  console.log(
    JSON.stringify({
      outputPath: args.output,
      bytes: Buffer.byteLength(content, "utf8"),
      fileId: fileObj.id,
      tier: args.tier,
      format: args.format,
    })
  );
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.command === "health") {
    await health(args);
  } else if (args.command === "parse") {
    await parseFile(args);
  }
}

main().catch((error) => fail(error.message || "Unexpected failure.", error));
