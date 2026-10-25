import assert from "node:assert/strict";
import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { compile } from "../build.mjs";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

test("fixed source builds five times identically, with static portable metadata", async () => {
  const folder = await mkdtemp(
    path.join(os.tmpdir(), "explorable-build-test-"),
  );
  try {
    const hashes = [];
    for (let i = 0; i < 5; i++) {
      const out = path.join(folder, String(i));
      hashes.push(
        (await compile(path.join(root, "templates/mdx"), out)).rendered_hash,
      );
      const meta = JSON.parse(
        await readFile(path.join(out, "artifact.json"), "utf8"),
      );
      assert.equal(meta.browser_status, "not_run");
    }
    assert.equal(new Set(hashes).size, 1);
  } finally {
    await rm(folder, { recursive: true, force: true });
  }
});
test("TSX fixtures and handoff compile with precompiled validation, no unsafe-eval", async () => {
  const folder = await mkdtemp(
    path.join(os.tmpdir(), "explorable-formats-test-"),
  );
  try {
    for (const format of ["tsx", "dataset"])
      await compile(
        path.join(root, "templates", format),
        path.join(folder, format),
      );
    const source = path.join(folder, "source");
    await cp(path.join(root, "templates/mdx"), source, { recursive: true });
    const descriptor = JSON.parse(
      await readFile(path.join(source, "artifact.json"), "utf8"),
    );
    descriptor.handoff = { schema: "snapshot.schema.json" };
    await writeFile(
      path.join(source, "artifact.json"),
      JSON.stringify(descriptor),
    );
    await writeFile(
      path.join(source, "snapshot.schema.json"),
      JSON.stringify({
        type: "object",
        additionalProperties: false,
        required: ["arrival", "service", "jobs"],
        properties: {
          arrival: { type: "number", minimum: 0, maximum: 20 },
          service: { type: "number", minimum: 1, maximum: 20 },
          jobs: { type: ["number", "null"], minimum: 0, maximum: 1000 },
        },
      }),
    );
    const out = path.join(folder, "handoff");
    await compile(source, out);
    const html = await readFile(path.join(out, "index.html"), "utf8");
    assert(!html.includes("unsafe-eval"));
    const payload = JSON.parse(
      await readFile(path.join(out, "document.json"), "utf8"),
    );
    assert(payload.schema);
    assert(payload.html.includes("connect-src 'none'"));
  } finally {
    await rm(folder, { recursive: true, force: true });
  }
});
test("compiler refuses host and remote imports, computed import, and surrounding config", async () => {
  const folder = await mkdtemp(
    path.join(os.tmpdir(), "explorable-boundary-test-"),
  );
  try {
    const source = path.join(folder, "source");
    await cp(path.join(root, "templates/tsx"), source, { recursive: true });
    const cases = [
      "import fs from 'node:fs'; export default function Doc(){return <p>{String(fs)}</p>}",
      "export default function Doc(){const moduleName='react';void import(moduleName);return <p>bad</p>}",
      "import remote from 'https://example.com/x.js';export default function Doc(){return <p>{remote}</p>}",
      "import outside from '../../package.json';export default function Doc(){return <p>{String(outside)}</p>}",
    ];
    for (let i = 0; i < cases.length; i++) {
      await writeFile(path.join(source, "document.tsx"), cases[i]);
      await assert.rejects(() => compile(source, path.join(folder, `bad${i}`)));
    }
    await writeFile(
      path.join(source, "document.tsx"),
      "export default function Doc(){return <p>fixed build</p>}",
    );
    await writeFile(
      path.join(source, "vite.config.ts"),
      'throw new Error("Do not execute artifact config")',
    );
    await compile(source, path.join(folder, "config-ignored"));
  } finally {
    await rm(folder, { recursive: true, force: true });
  }
});
test("queue model agrees with independent edge expectations", async () => {
  const source = await readFile(
    path.join(root, "templates/mdx/model.ts"),
    "utf8",
  );
  const js = ts.transpile(source, { module: ts.ModuleKind.ESNext });
  const { queue } = await import(
    `data:text/javascript,${encodeURIComponent(js)}`
  );
  assert.deepEqual(queue(0, 8), { utilization: 0, jobs: 0 });
  assert.deepEqual(queue(4, 8), { utilization: 0.5, jobs: 1 });
  assert.deepEqual(queue(6, 8), { utilization: 0.75, jobs: 3 });
  assert.equal(queue(8, 8).jobs, null);
  assert.equal(queue(20, 8).jobs, null);
});

test("declared SVG and CSS imports build as local bundled assets", async () => {
  const folder = await mkdtemp(
    path.join(os.tmpdir(), "explorable-assets-test-"),
  );
  try {
    const source = path.join(folder, "source");
    await cp(path.join(root, "templates/tsx"), source, { recursive: true });
    const descriptor = JSON.parse(
      await readFile(path.join(source, "artifact.json"), "utf8"),
    );
    descriptor.assets = ["diagram.svg"];
    await writeFile(
      path.join(source, "artifact.json"),
      JSON.stringify(descriptor),
    );
    await writeFile(
      path.join(source, "diagram.svg"),
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><circle cx="10" cy="10" r="5"/></svg>',
    );
    await writeFile(
      path.join(source, "styles.css"),
      ".caption { color: var(--muted); }",
    );
    await writeFile(
      path.join(source, "document.tsx"),
      'import diagram from "./diagram.svg"; import "./styles.css"; export default function Doc(){return <><img src={diagram} alt="Illustrative circle"/><p className="caption">Local asset</p></>}',
    );
    const output = path.join(folder, "out");
    await compile(source, output);
    const payload = JSON.parse(
      await readFile(path.join(output, "document.json"), "utf8"),
    );
    assert(payload.html.includes("data:image/svg+xml"));
    assert(payload.html.includes(".caption"));
  } finally {
    await rm(folder, { recursive: true, force: true });
  }
});
