import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { cp, mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import mdx from "@mdx-js/rollup";
import Ajv from "ajv";
import standalone from "ajv/dist/standalone/index.js";
import gfm from "remark-gfm";
import ts from "typescript";
import { build } from "vite";

const root = path.dirname(fileURLToPath(import.meta.url));
export async function hashTree(directory) {
  const entries = {};
  async function walk(folder) {
    for (const entry of (await readdir(folder, { withFileTypes: true })).sort(
      (a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0),
    )) {
      const absolute = path.join(folder, entry.name);
      if (entry.isDirectory()) await walk(absolute);
      else
        entries[path.relative(directory, absolute).split(path.sep).join("/")] =
          createHash("sha256")
            .update(await readFile(absolute))
            .digest("hex");
    }
  }
  await walk(directory);
  return createHash("sha256").update(JSON.stringify(entries)).digest("hex");
}
function guard(source, assets) {
  return {
    name: "source-boundary",
    enforce: "pre",
    load(id) {
      const clean = id.split("?")[0];
      if (
        !id.startsWith("\0") &&
        path.isAbsolute(clean) &&
        !clean.startsWith(`${root}/`)
      )
        throw Error("Module leaves fixed compiler/source boundary.");
      return null;
    },
    resolveId(id, importer) {
      if (!importer?.startsWith(`${source}/`)) return null;
      if (
        [
          "react",
          "react/jsx-runtime",
          "react/jsx-dev-runtime",
          "react-dom/client",
        ].includes(id)
      )
        return null;
      if (id === "@explorable/kit") return path.join(root, "kit.tsx");
      if (!id.startsWith("."))
        throw Error(
          `Unapproved import ${id}. Use local source, React, or @explorable/kit.`,
        );
      if (id.includes("?") || id.includes("#"))
        throw Error(`Import queries are unsupported: ${id}`);
      const target = path.resolve(path.dirname(importer), id);
      if (!target.startsWith(`${source}/`))
        throw Error(`Import leaves source: ${id}`);
      if (
        /\.(json|svg|png|jpg|jpeg|webp|gif)$/.test(id) &&
        !assets.includes(path.relative(source, target))
      )
        throw Error(`Declare imported asset: ${id}`);
      return null;
    },
    transform(code, id) {
      if (!id.startsWith(`${source}/`) || id.endsWith(".css")) return null;
      const file = ts.createSourceFile(
        id,
        code,
        ts.ScriptTarget.Latest,
        true,
        ts.ScriptKind.TSX,
      );
      function visit(node) {
        if (
          ts.isCallExpression(node) &&
          node.expression.kind === ts.SyntaxKind.ImportKeyword &&
          !ts.isStringLiteral(node.arguments[0])
        )
          throw Error("Dynamic import must use a literal local module.");
        if (ts.isMetaProperty(node))
          throw Error("import.meta is unsupported in document source.");
        ts.forEachChild(node, visit);
      }
      visit(file);
      return null;
    },
  };
}
export async function compile(sourcePath, output) {
  try {
    if ((await readdir(output)).length)
      throw Error(
        "Output must be new or empty; choose a fresh rebuild directory.",
      );
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  const source = path.join(root, ".work/source");
  await rm(path.join(root, ".work"), { recursive: true, force: true });
  await mkdir(source, { recursive: true });
  async function audit(folder) {
    for (const item of await readdir(folder, { withFileTypes: true })) {
      if (item.name === "_toolchain") continue;
      if (item.isSymbolicLink())
        throw Error("Source symlinks are unsupported.");
      const file = path.join(folder, item.name);
      if (item.isDirectory()) await audit(file);
      else if (item.name.endsWith(".css")) {
        const css = await readFile(file, "utf8");
        if (css.includes("\\") || /@import|url\s*\(/i.test(css))
          throw Error(
            "CSS URLs/imports/escapes are unsupported; import declared assets from TSX.",
          );
      }
    }
  }
  await audit(sourcePath);
  for (const entry of await readdir(sourcePath)) {
    if (entry !== "_toolchain")
      await cp(path.join(sourcePath, entry), path.join(source, entry), {
        recursive: true,
      });
  }
  const descriptor = JSON.parse(
    await readFile(path.join(source, "artifact.json"), "utf8"),
  );
  for (const name of [
    descriptor.entry,
    ...(descriptor.assets || []),
    ...(descriptor.handoff ? [descriptor.handoff.schema] : []),
  ]) {
    if (
      typeof name !== "string" ||
      !/^[A-Za-z0-9_./-]{1,200}$/.test(name) ||
      name.split("/").some((part) => part.startsWith(".")) ||
      !path.resolve(source, name).startsWith(`${source}/`)
    )
      throw Error("Declared path must stay inside source.");
  }
  const config = JSON.parse(
    await readFile(path.join(root, "tsconfig.json"), "utf8"),
  );
  config.compilerOptions.paths = { "@explorable/kit": ["./kit.tsx"] };
  config.include = [
    "kit.tsx",
    "bridge.ts",
    "globals.d.ts",
    ".work/source/**/*.ts",
    ".work/source/**/*.tsx",
  ];
  await writeFile(path.join(root, "check.json"), JSON.stringify(config));
  const checked = spawnSync(
    process.execPath,
    [
      path.join(root, "node_modules/typescript/bin/tsc"),
      "--project",
      path.join(root, "check.json"),
    ],
    { encoding: "utf8", cwd: root },
  );
  if (checked.status !== 0)
    throw Error(`Type check failed:\n${checked.stdout}${checked.stderr}`);
  const entry = path.join(root, ".work/main.tsx");
  await writeFile(
    entry,
    `import React from 'react';import {createRoot} from 'react-dom/client';import Content from './source/${descriptor.entry}';import {connect} from '../bridge';connect(${Boolean(descriptor.handoff)});createRoot(document.getElementById('root')!).render(<article className="document"><Content/></article>);`,
  );
  const common = {
    configFile: false,
    envFile: false,
    envDir: false,
    root,
    logLevel: "error",
    define: { "process.env.NODE_ENV": JSON.stringify("production") },
    build: {
      write: false,
      minify: true,
      assetsInlineLimit: () => true,
      lib: { entry, name: "ExplorableDocument", formats: ["iife"] },
    },
  };
  const result = await build({
    ...common,
    plugins: [
      guard(source, descriptor.assets || []),
      mdx({ remarkPlugins: [gfm] }),
      {
        name: "compiled-source-audit",
        enforce: "post",
        transform: guard(source, []).transform,
      },
    ],
  });
  const bundle = (Array.isArray(result) ? result[0] : result).output;
  const script = bundle.find((item) => item.type === "chunk").code;
  const css = bundle
    .filter((item) => item.type === "asset" && item.fileName.endsWith(".css"))
    .map((item) => item.source)
    .join("\n");
  const style = await readFile(path.join(root, "theme.css"), "utf8");
  const inner = `<!doctype html><html lang="en" data-layout="${descriptor.layout || "article"}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none';"><title>Document</title><style>${(`${style}\n${css}`).replaceAll("</style", "<\\/style")}</style></head><body><main id="root"></main><script>${script.replaceAll("</script", "<\\/script")}</script></body></html>`;
  await mkdir(output, { recursive: true });
  const schema = descriptor.handoff
    ? JSON.parse(
        await readFile(path.join(source, descriptor.handoff.schema), "utf8"),
      )
    : null;
  const ajv = new Ajv({ strict: true, code: { source: true } });
  const validator = schema
    ? standalone(ajv, ajv.compile(schema))
    : "module.exports = () => false;";
  await writeFile(path.join(root, ".work/validator.cjs"), validator);
  const shell = await build({
    ...common,
    resolve: {
      alias: { "./snapshot-validator": path.join(root, ".work/validator.cjs") },
    },
    build: {
      ...common.build,
      commonjsOptions: { include: [/node_modules/, /validator\.cjs/] },
      lib: {
        entry: path.join(root, "viewer.ts"),
        name: "ExplorableViewer",
        formats: ["iife"],
      },
    },
  });
  const shellCode = (Array.isArray(shell) ? shell[0] : shell).output.find(
    (item) => item.type === "chunk",
  ).code;
  await writeFile(path.join(output, "viewer.js"), shellCode);
  for (const name of [
    "index.html",
    "theme.css",
    "viewer.css",
    "THIRD-PARTY-NOTICES.txt",
  ])
    await cp(path.join(root, name), path.join(output, name));
  await writeFile(
    path.join(output, "document.json"),
    JSON.stringify({ descriptor, html: inner, schema }),
  );
  const renderedHash = await hashTree(output);
  const packageInfo = JSON.parse(
    await readFile(path.join(root, "package.json"), "utf8"),
  );
  await writeFile(
    path.join(output, "artifact.json"),
    JSON.stringify({
      id: "rebuilt",
      source_format: path.extname(descriptor.entry).slice(1),
      toolchain_version: packageInfo.version,
      rendered_hash: renderedHash,
      browser_status: "not_run",
    }),
  );
  return {
    rendered_hash: renderedHash,
    typecheck: "passed",
    compile: "passed",
  };
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    const [source, output] = process.argv.slice(2);
    if (!source || !output) throw Error("Usage: node build.mjs SOURCE OUTPUT");
    console.log(
      JSON.stringify(await compile(path.resolve(source), path.resolve(output))),
    );
  } catch (error) {
    console.error(String(error));
    process.exitCode = 3;
  }
}
