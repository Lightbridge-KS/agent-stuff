/** Real Chromium acceptance: run explicitly with pnpm test:diagrams [output-dir]. */
import assert from "node:assert/strict";
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { chromium } from "playwright";
import { compile } from "../build.mjs";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const output = path.resolve(process.argv[2] || "diagram-evidence");
await mkdir(output, { recursive: true });
const work = await mkdtemp(path.join(os.tmpdir(), "diagram-live-"));
let rendered;
const server = createServer(async (req, res) => {
  const file = req.url === "/" ? "index.html" : req.url.slice(1);
  if (
    ![
      "index.html",
      "viewer.js",
      "viewer.css",
      "theme.css",
      "document.json",
      "artifact.json",
    ].includes(file)
  ) {
    res.writeHead(404).end();
    return;
  }
  try {
    res.setHeader(
      "Content-Type",
      file.endsWith(".json")
        ? "application/json"
        : file.endsWith(".js")
          ? "text/javascript"
          : file.endsWith(".css")
            ? "text/css"
            : "text/html",
    );
    res.end(await readFile(path.join(rendered, file)));
  } catch {
    res.writeHead(404).end();
  }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const browser = await chromium.launch();
const context = await browser.newContext();
const page = await context.newPage();
const errors = [],
  results = [];
page.on("pageerror", (error) => errors.push(error.message));
page.setDefaultTimeout(10000);
const base = `http://127.0.0.1:${server.address().port}`;
async function open() {
  await page.goto(base);
  await page.locator("#status").filter({ hasText: "Ready ·" }).waitFor();
  const frame = page.frames().find((f) => f !== page.mainFrame());
  await frame.locator(".ed-diagram-root").first().waitFor();
  await settle(frame);
  return frame;
}
async function settle(frame) {
  // Wait for ResizeObserver + coalesced measurement + real label measurement.
  await frame.evaluate(async () => {
    await document.fonts.ready;
    for (let i = 0; i < 6; i++) await new Promise(requestAnimationFrame);
  });
}
async function geometry(frame, expected) {
  const findings = await frame.evaluate(() => {
    const issues = [];
    let count = 0;
    const hit = (a, b, r) =>
      Math.abs(a.x - b.x) < 0.1
        ? a.x > r.left + 0.5 &&
          a.x < r.right - 0.5 &&
          Math.max(a.y, b.y) > r.top + 0.5 &&
          Math.min(a.y, b.y) < r.bottom - 0.5
        : a.y > r.top + 0.5 &&
          a.y < r.bottom - 0.5 &&
          Math.max(a.x, b.x) > r.left + 0.5 &&
          Math.min(a.x, b.x) < r.right - 0.5;
    for (const root of document.querySelectorAll(".ed-diagram-root")) {
      const canvas = root
        .querySelector(".ed-diagram-canvas")
        .getBoundingClientRect();
      const nodes = [
        ...root.querySelectorAll(".ed-diagram-node, .ed-diagram-boundary"),
      ];
      const routed = [];
      for (const edge of root.querySelectorAll("path[data-ed-from]")) {
        count++;
        const from = nodes.find(
            (n) => n.dataset.edName === edge.dataset.edFrom,
          ),
          to = nodes.find((n) => n.dataset.edName === edge.dataset.edTo);
        const nums = edge
          .getAttribute("d")
          .match(/-?[\d.]+/g)
          .map(Number);
        const points = [];
        for (let i = 0; i < nums.length; i += 2)
          points.push({ x: nums[i] + canvas.x, y: nums[i + 1] + canvas.y });
        routed.push(points);
        for (const [node, p] of [
          [from, points[0]],
          [to, points.at(-1)],
        ]) {
          const r = node.getBoundingClientRect();
          const dx = Math.max(r.left - p.x, 0, p.x - r.right),
            dy = Math.max(r.top - p.y, 0, p.y - r.bottom);
          if (Math.abs(Math.hypot(dx, dy) - 4) > 0.6)
            issues.push(
              `Wrong endpoint clearance ${edge.dataset.edFrom}->${edge.dataset.edTo}`,
            );
        }
        for (const n of nodes) {
          if (n !== from && n !== to && (n.contains(from) || n.contains(to)))
            continue;
          const r = n.getBoundingClientRect();
          if (!r.width || !r.height) continue;
          for (let i = 1; i < points.length; i++)
            if (hit(points[i - 1], points[i], r))
              issues.push(`Path crosses ${n.textContent.trim().slice(0, 30)}`);
        }
      }
      // Independently inspect crossings and overlapping lanes, including bends.
      for (let first = 0; first < routed.length; first++)
        for (let second = first + 1; second < routed.length; second++) {
          const one = routed[first],
            two = routed[second];
          for (let i = 1; i < one.length; i++)
            for (let j = 1; j < two.length; j++) {
              const a = one[i - 1],
                b = one[i],
                c = two[j - 1],
                d = two[j];
              const av = Math.abs(a.x - b.x) < 0.1,
                cv = Math.abs(c.x - d.x) < 0.1;
              if (av === cv) {
                const same = av
                  ? Math.abs(a.x - c.x) < 0.5
                  : Math.abs(a.y - c.y) < 0.5;
                const overlap = av
                  ? Math.min(Math.max(a.y, b.y), Math.max(c.y, d.y)) -
                    Math.max(Math.min(a.y, b.y), Math.min(c.y, d.y))
                  : Math.min(Math.max(a.x, b.x), Math.max(c.x, d.x)) -
                    Math.max(Math.min(a.x, b.x), Math.min(c.x, d.x));
                if (same && overlap > 0.5)
                  issues.push("Overlapping connector lanes");
              } else {
                const [v, w, h, k] = av ? [a, b, c, d] : [c, d, a, b];
                if (
                  v.x >= Math.min(h.x, k.x) - 0.1 &&
                  v.x <= Math.max(h.x, k.x) + 0.1 &&
                  h.y >= Math.min(v.y, w.y) - 0.1 &&
                  h.y <= Math.max(v.y, w.y) + 0.1
                ) {
                  const shared =
                    [one[0], one.at(-1)].some(
                      (p) => Math.hypot(p.x - v.x, p.y - h.y) < 0.5,
                    ) &&
                    [two[0], two.at(-1)].some(
                      (p) => Math.hypot(p.x - v.x, p.y - h.y) < 0.5,
                    );
                  if (!shared) issues.push("Connector crossing");
                }
              }
            }
        }
      const labels = [
        ...root.querySelectorAll(".ed-diagram-edge-label"),
      ].filter((el) => getComputedStyle(el).visibility === "visible");
      for (const [i, label] of labels.entries()) {
        const r = label.getBoundingClientRect();
        for (const other of [...nodes, ...labels.slice(0, i)]) {
          const s = other.getBoundingClientRect();
          if (
            r.left < s.right - 0.5 &&
            r.right > s.left + 0.5 &&
            r.top < s.bottom - 0.5 &&
            r.bottom > s.top + 0.5
          )
            issues.push("Label overlaps content");
        }
      }
    }
    if (document.documentElement.scrollWidth > innerWidth + 1)
      issues.push("Horizontal overflow");
    return {
      count,
      issues,
      diagnostics: [...document.querySelectorAll(".ed-diagram-diagnostic")].map(
        (el) => el.textContent,
      ),
    };
  });
  assert.deepEqual(findings.issues, []);
  assert.equal(findings.count, expected);
  return findings;
}
try {
  for (const [name, count] of [
    ["Concepts", 0],
    ["Spectrum", 0],
    ["Contract", 2],
    ["Distance", 3],
    ["Workflow", 3],
    ["Architecture", 5],
    ["Lifecycle", 2],
  ]) {
    if (
      process.env.DIAGRAM_CASES &&
      !process.env.DIAGRAM_CASES.split(",").includes(name)
    )
      continue;
    const source = path.join(work, name);
    await mkdir(source);
    await cp(
      path.join(root, "fixtures/diagrams/examples.tsx"),
      path.join(source, "examples.tsx"),
    );
    await cp(
      path.join(root, "fixtures/diagrams/lifecycle.tsx"),
      path.join(source, "lifecycle.tsx"),
    );
    await cp(
      path.join(root, "fixtures/diagrams/recipes.css"),
      path.join(source, "recipes.css"),
    );
    await writeFile(
      path.join(source, "document.tsx"),
      name === "Lifecycle"
        ? 'export {default} from "./lifecycle";'
        : `export {${name} as default} from "./examples";`,
    );
    await writeFile(
      path.join(source, "artifact.json"),
      JSON.stringify({
        schema_version: 1,
        title: `${name} fixture`,
        summary: "Synthetic diagram acceptance fixture.",
        entry: "document.tsx",
        layout: "workspace",
        assets: [],
        data_sources: [
          {
            id: "synthetic",
            kind: "illustrative",
            description: "Synthetic fixture",
          },
        ],
        interactions: [],
      }),
    );
    rendered = path.join(work, `${name}-rendered`);
    await compile(source, rendered);
    for (const width of [390, 768, 1280])
      for (const theme of ["dark", "light"]) {
        await page.setViewportSize({ width, height: 900 });
        const frame = await open();
        await page.locator("#theme").selectOption(theme);
        await settle(frame);
        const findings = await geometry(frame, count);
        assert.deepEqual(findings.diagnostics, [], `${name}/${width}/${theme}`);
        const axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze();
        assert.deepEqual(
          axe.violations,
          [],
          `${name}/${width}/${theme} accessibility`,
        );
        await page.screenshot({
          path: path.join(output, `${name}-${width}-${theme}.png`),
          fullPage: true,
        });
        results.push({ name, width, theme, status: "passed" });
        console.log(`${name} ${width} ${theme}: passed`);
      }
    await page.setViewportSize({ width: 1280, height: 900 });
    const frame = await open();
    await page.setViewportSize({ width: 390, height: 900 });
    assert(
      await frame.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
      `${name}: transient resize overflow`,
    );
    await settle(frame);
    await geometry(frame, count);
    await page.setViewportSize({ width: 1280, height: 900 });
    await settle(frame);
    await frame.locator(".document").evaluate((el) => {
      el.style.width = "350px";
      el.style.maxWidth = "100%";
    });
    await settle(frame);
    assert.deepEqual((await geometry(frame, count)).diagnostics, []);
    results.push({ name, containerWidth: 350, status: "passed" });
    if (name === "Lifecycle") {
      await frame.locator("#note").fill("preserved");
      await frame.locator("#expand").click();
      await settle(frame);
      await geometry(frame, 2);
      await frame.locator("#note").focus();
      await page.setViewportSize({ width: 768, height: 900 });
      await settle(frame);
      assert.equal(await frame.locator("#note").inputValue(), "preserved");
      assert(
        await frame
          .locator("#note")
          .evaluate((el) => el === document.activeElement),
      );
      const first = frame.locator(".ed-diagram-root").first();
      for (const [mode, text] of [
        ["duplicate", "Duplicate endpoint"],
        ["missing", "Cannot resolve"],
        ["removed", "Cannot resolve"],
        ["self", "Self-loop"],
        ["hidden", null],
      ]) {
        await frame.locator("#mode").selectOption(mode);
        await settle(frame);
        assert.equal(await first.locator("path[data-ed-from]").count(), 0);
        if (text) assert((await first.textContent()).includes(text));
        else
          assert.equal(
            await first.locator(".ed-diagram-diagnostic").count(),
            0,
          );
      }
      await frame.locator("#mode").selectOption("label");
      await settle(frame);
      assert((await first.textContent()).includes("does not fit"));
      await frame.locator("#mode").selectOption("normal");
      await settle(frame);
      await geometry(frame, 2);
      const summary = first.locator("summary");
      await summary.focus();
      await page.keyboard.press("Enter");
      assert(await first.locator("details").evaluate((el) => el.open));
      // Observer quiescence: a settled diagram must not mutate its own output forever.
      assert.equal(
        await first.evaluate(async (el) => {
          let n = 0;
          const observer = new MutationObserver(() => n++);
          observer.observe(el, {
            subtree: true,
            attributes: true,
            childList: true,
          });
          await new Promise((resolve) => setTimeout(resolve, 250));
          observer.disconnect();
          return n;
        }),
        0,
      );
      results.push({
        name,
        scenario:
          "dynamic, focus, scope, failure, hidden, keyboard, quiescence",
        status: "passed",
      });
    }
  }
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "results.json"),
    JSON.stringify(
      { status: "passed", browser: browser.version(), results },
      null,
      2,
    ),
  );
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
  await rm(work, { recursive: true, force: true });
}
