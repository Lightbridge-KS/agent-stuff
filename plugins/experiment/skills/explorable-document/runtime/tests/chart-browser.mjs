/** Real Chromium acceptance: run explicitly with pnpm test:charts [output-dir]. */
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
const output = path.resolve(process.argv[2] || "chart-evidence");
await mkdir(output, { recursive: true });
const work = await mkdtemp(path.join(os.tmpdir(), "chart-live-"));
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
const context = await browser.newContext({ hasTouch: true });
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
  await frame.locator(".ed-chart-frame").first().waitFor();
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
async function inspectLayout(frame) {
  const issues = await frame.evaluate(() => {
    const issues = [];
    if (document.documentElement.scrollWidth > innerWidth + 1)
      issues.push("Horizontal overflow");
    for (const svg of document.querySelectorAll(".ed-chart-line > svg")) {
      const bounds = svg.getBoundingClientRect();
      const labels = [...svg.querySelectorAll("text")].map((el) => ({
        text: el.textContent,
        r: el.getBoundingClientRect(),
      }));
      for (const label of labels)
        if (
          label.r.left < bounds.left - 0.8 ||
          label.r.right > bounds.right + 0.8 ||
          label.r.bottom > bounds.bottom + 0.8 ||
          label.r.top < bounds.top - 0.8
        )
          issues.push(`Clipped axis label: ${label.text}`);
      for (let i = 0; i < labels.length; i++)
        for (let j = i + 1; j < labels.length; j++) {
          const a = labels[i].r,
            b = labels[j].r;
          if (
            Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1 &&
            Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1
          )
            issues.push(
              `Overlapping axis labels: ${labels[i].text}/${labels[j].text}`,
            );
        }
    }
    return issues;
  });
  assert.deepEqual(issues, []);
}
async function verifyTrend(frame) {
  const chart = frame.locator(".ed-chart-frame").first(),
    selector = chart.locator("select");
  await selector.selectOption("sun");
  assert(
    (await chart.locator(".ed-chart-readout").textContent()).includes(
      "2,750 requests/day",
    ),
  );
  await frame.locator("#series-Errors").click();
  await settle(frame);
  assert.equal(await selector.inputValue(), "sun");
  assert(
    (await chart.locator(".ed-chart-readout").textContent()).includes(
      "Errors: 7 errors/day",
    ),
  );
  await frame.locator("#series-Requests").click();
  await selector.selectOption("mon");
  await settle(frame);
  // Fit values to the actual displayed grid lines, not the renderer's scale helpers.
  const points = await chart.evaluate((el) => {
    const svg = el.querySelector(".ed-chart-line > svg"),
      box = svg.getBoundingClientRect();
    const grid = [...svg.querySelectorAll(".ed-chart-gridline")]
      .map((el) => ({
        x1: Number(el.getAttribute("x1")),
        x2: Number(el.getAttribute("x2")),
        y: Number(el.getAttribute("y1")),
        value: Number(
          el.parentElement
            .querySelector("text")
            .textContent.replaceAll(",", ""),
        ),
      }))
      .sort((a, b) => a.value - b.value);
    const low = grid[0],
      high = grid.at(-1);
    return [...svg.querySelectorAll("g[data-chart-point]")].map((el, index) => {
      const mark = el.firstElementChild.getBoundingClientRect();
      return {
        index,
        x: (mark.left + mark.right) / 2 - box.left,
        y: (mark.top + mark.bottom) / 2 - box.top,
        low,
        high,
      };
    });
  });
  const expected = [1100, 1450, 1320, 1800, 2300, 2050, 2750];
  assert.equal(points.length, 7);
  for (const p of points) {
    assert(
      Math.abs(p.x - (p.low.x1 + (p.index * (p.low.x2 - p.low.x1)) / 6)) < 0.8,
    );
    assert(
      Math.abs(
        p.y -
          (p.low.y -
            ((expected[p.index] - p.low.value) / (p.high.value - p.low.value)) *
              (p.low.y - p.high.y)),
      ) < 0.8,
    );
  }
  const svg = chart.locator(".ed-chart-line > svg"),
    box = await svg.boundingBox();
  const left = Number(await svg.getAttribute("data-chart-left")),
    right = Number(await svg.getAttribute("data-chart-right")),
    top = Number(await svg.getAttribute("data-chart-top"));
  await page.mouse.move(
    box.x + left + ((right - left) * 4) / 6,
    box.y + top + 80,
  );
  await settle(frame);
  assert(
    (await chart.locator(".ed-chart-readout").textContent()).includes(
      "Preview · Fri",
    ),
  );
  assert.equal(await selector.inputValue(), "mon");
  await selector.selectOption("tue");
  assert(
    !(await chart.locator(".ed-chart-readout").textContent()).includes(
      "Preview",
    ),
  );
  await page.mouse.move(
    box.x + left + ((right - left) * 4) / 6 + 1,
    box.y + top + 80,
  );
  await page.mouse.move(1, 1);
  await settle(frame);
  assert(
    (await chart.locator(".ed-chart-readout").textContent()).includes(
      "Selected · Tue",
    ),
  );
  await page.mouse.click(box.x + right, box.y + top + 80);
  await settle(frame);
  assert.equal(await selector.inputValue(), "sun");
  assert(
    await chart.getByRole("button", { name: "Next", exact: true }).isDisabled(),
  );
  await selector.focus();
  await selector.press("t");
  await selector.press("Enter");
  await settle(frame);
  assert.equal(await selector.inputValue(), "tue");
  await selector.focus();
  await page.setViewportSize({ width: 768, height: 900 });
  await settle(frame);
  assert(await selector.evaluate((el) => el === document.activeElement));
  await page.locator("#theme").selectOption("light");
  await settle(frame);
  assert.equal(await selector.inputValue(), "tue");
  await svg.scrollIntoViewIfNeeded();
  const touchBox = await svg.boundingBox();
  await page.touchscreen.tap(
    touchBox.x +
      Number(await svg.getAttribute("data-chart-left")) +
      (Number(await svg.getAttribute("data-chart-right")) -
        Number(await svg.getAttribute("data-chart-left"))) /
        2,
    touchBox.y + Number(await svg.getAttribute("data-chart-top")) + 80,
  );
  await settle(frame);
  assert.equal(await selector.inputValue(), "thu");
  // A real touch pan must cancel the pending tap rather than selecting a category.
  const touch = await context.newCDPSession(page);
  await svg.scrollIntoViewIfNeeded();
  const panBox = await svg.boundingBox();
  const panX =
      panBox.x + Number(await svg.getAttribute("data-chart-left")) + 40,
    panY = panBox.y + Number(await svg.getAttribute("data-chart-top")) + 90;
  await touch.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [{ x: panX, y: panY }],
  });
  await touch.send("Input.dispatchTouchEvent", {
    type: "touchMove",
    touchPoints: [{ x: panX, y: panY - 80 }],
  });
  await touch.send("Input.dispatchTouchEvent", {
    type: "touchEnd",
    touchPoints: [],
  });
  await touch.detach();
  await settle(frame);
  assert.equal(await selector.inputValue(), "thu");
  await chart.locator("summary").click();
  const cells = await chart.locator("tbody tr").allTextContents();
  assert.equal(cells.length, 7);
  assert(cells[6].includes("2750"));
}
try {
  for (const name of ["Trend", "Comparison", "Lifecycle", "Parts"]) {
    if (
      process.env.CHART_CASES &&
      !process.env.CHART_CASES.split(",").includes(name)
    )
      continue;
    const source = path.join(work, name);
    await mkdir(source);
    await cp(
      path.join(root, "fixtures/charts/examples.tsx"),
      path.join(source, "examples.tsx"),
    );
    await cp(
      path.join(root, "fixtures/charts/lifecycle.tsx"),
      path.join(source, "lifecycle.tsx"),
    );
    await writeFile(
      path.join(source, "document.tsx"),
      name === "Lifecycle"
        ? `export {default} from "./lifecycle";`
        : `export {${name} as default} from './examples';`,
    );
    await writeFile(
      path.join(source, "artifact.json"),
      JSON.stringify({
        schema_version: 1,
        title: `${name} chart fixture`,
        summary: "Synthetic chart acceptance fixture.",
        entry: "document.tsx",
        layout: "article",
        assets: [],
        data_sources: [
          {
            id: "synthetic",
            kind: "synthetic",
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
        assert.equal(await frame.locator(".ed-chart-diagnostic").count(), 0);
        await inspectLayout(frame);
        const axe = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
          .analyze();
        assert.deepEqual(axe.violations, [], `${name}/${width}/${theme}`);
        await page.screenshot({
          path: path.join(output, `${name}-${width}-${theme}.png`),
          fullPage: true,
        });
        results.push({ name, width, theme, status: "passed" });
        console.log(`${name} ${width} ${theme}: passed`);
      }
    await page.setViewportSize({ width: 1280, height: 900 });
    let frame = await open();
    await frame.locator(".document").evaluate((el) => {
      el.style.width = "350px";
      el.style.maxWidth = "100%";
    });
    await settle(frame);
    await inspectLayout(frame);
    assert.equal(await frame.locator(".ed-chart-diagnostic").count(), 0);
    results.push({ name, containerWidth: 350, status: "passed" });
    if (name === "Trend") {
      frame = await open();
      await verifyTrend(frame);
      results.push({
        name,
        scenario:
          "series, exact data, keyboard, hover, click, focus, resize and theme",
        status: "passed",
      });
    }
    if (name === "Lifecycle") {
      const charts = frame.locator(".ed-chart-frame"),
        controlled = charts.nth(0),
        independent = charts.nth(1);
      assert.equal(
        (await frame.locator("#selection-note").textContent()).trim(),
        "0 callbacks · mon · none",
      );
      await controlled.locator("select").selectOption("sun");
      assert(
        (await frame.locator("#selection-note").textContent()).includes(
          "1 callbacks · sun · control",
        ),
      );
      assert.equal(await independent.locator("select").inputValue(), "mon");
      await frame.locator("#fixture-mode").selectOption("removed");
      await settle(frame);
      // sun remains present; removal of mon only changes the independent frame.
      assert.equal(await controlled.locator("select").inputValue(), "sun");
      assert.equal(await independent.locator("select").inputValue(), "tue");
      await frame.locator("#fixture-mode").selectOption("normal");
      await frame.locator("#repair").click();
      await frame.locator("#fixture-mode").selectOption("removed");
      await settle(frame);
      assert((await controlled.textContent()).includes("not in this dataset"));
      await frame.locator("#repair").click();
      await settle(frame);
      assert.equal(await controlled.locator(".ed-chart-diagnostic").count(), 0);
      for (const mode of [
        "empty",
        "all-null",
        "one",
        "signed",
        "zero",
        "constant",
        "long",
        "four",
      ]) {
        await frame.locator("#fixture-mode").selectOption("normal");
        await frame.locator("#repair").click();
        await frame.locator("#fixture-mode").selectOption(mode);
        await settle(frame);
        assert.equal(
          await frame.locator(".ed-chart-diagnostic").count(),
          0,
          mode,
        );
        await inspectLayout(frame);
        if (mode === "empty" || mode === "all-null")
          assert.equal(await frame.locator(".ed-chart-line > svg").count(), 0);
        if (mode === "one")
          assert.equal(
            await controlled.locator("g[data-chart-point]").count(),
            2,
          );
      }
      for (const mode of ["duplicate", "nonfinite", "domain"]) {
        await frame.locator("#fixture-mode").selectOption(mode);
        await settle(frame);
        assert((await frame.locator(".ed-chart-diagnostic").count()) > 0, mode);
      }
      await frame.locator("#fixture-mode").selectOption("hidden");
      await settle(frame);
      await frame.locator("#fixture-mode").selectOption("normal");
      await settle(frame);
      assert.equal(await frame.locator(".ed-chart-diagnostic").count(), 0);
      await inspectLayout(frame);
      assert(
        (await frame.locator("#selection-note").textContent()).includes(
          "1 callbacks",
        ),
      );
      assert.equal(
        await controlled.evaluate(async (el) => {
          let mutations = 0;
          const watcher = new MutationObserver(() => mutations++);
          watcher.observe(el, {
            subtree: true,
            attributes: true,
            childList: true,
            characterData: true,
          });
          await new Promise((resolve) => setTimeout(resolve, 250));
          watcher.disconnect();
          return mutations;
        }),
        0,
        "settled charts must not remeasure forever",
      );
      results.push({
        name,
        scenario:
          "controlled scope, callbacks, data replacement, edge states, diagnostics and hidden recovery",
        status: "passed",
      });
    }
    if (name === "Parts") {
      const chart = frame.locator(".ed-chart-frame");
      const geometry = await chart.evaluate((el) => {
        const svg = el.querySelector(".ed-chart-parts > svg");
        return {
          width: svg.getBoundingClientRect().width,
          rects: [...svg.querySelectorAll("rect")].map((r) => ({
            x: Number(r.getAttribute("x")),
            width: Number(r.getAttribute("width")),
          })),
        };
      });
      for (const [index, expected] of [
        [0, [0, 0.17]],
        [1, [0.17, 0.08]],
        [2, [0.25, 0.75]],
      ]) {
        assert(
          Math.abs(geometry.rects[index].x - geometry.width * expected[0]) <
            0.1,
        );
        assert(
          Math.abs(geometry.rects[index].width - geometry.width * expected[1]) <
            0.1,
        );
      }
      const mode = frame.locator("#parts-mode");
      await mode.selectOption("tiny");
      await settle(frame);
      assert.equal(
        await chart.locator('rect[data-chart-segment="zero"]').count(),
        0,
      );
      assert(
        Number(
          await chart
            .locator('rect[data-chart-segment="tiny"]')
            .getAttribute("width"),
        ) < 0.001,
      );
      assert(
        (await chart.locator(".ed-chart-parts-list").textContent()).includes(
          "<0.1%",
        ),
      );
      await mode.selectOption("precision");
      await chart.locator("summary").click();
      assert(
        (await chart.locator("tbody").textContent()).includes(
          "1.23456789012345",
        ),
      );
      for (const state of ["zero", "empty", "long"]) {
        await mode.selectOption(state);
        await settle(frame);
        await inspectLayout(frame);
        assert.equal(await chart.locator(".ed-chart-diagnostic").count(), 0);
        if (state !== "long")
          assert.equal(await chart.locator(".ed-chart-parts > svg").count(), 0);
      }
      for (const state of ["negative", "duplicate"]) {
        await mode.selectOption(state);
        await settle(frame);
        assert.equal(await chart.locator(".ed-chart-diagnostic").count(), 1);
        assert.equal(await chart.locator(".ed-chart-parts > svg").count(), 0);
      }
      await mode.selectOption("counts");
      await settle(frame);
      results.push({
        name,
        scenario:
          "count geometry, tiny/zero/empty values, exact precision and invalid model recovery",
        status: "passed",
      });
    }
    if (name === "Comparison") {
      assert(
        (await frame.locator(".ed-chart-readout").textContent()).includes(
          "No observation",
        ),
      );
      const path = await frame
        .locator('path[data-chart-series="baseline"]')
        .getAttribute("d");
      assert.equal((path.match(/M /g) || []).length, 2);
      assert.equal(
        await frame
          .locator('g[data-chart-point="wed"][data-chart-series="baseline"]')
          .count(),
        0,
      );
      results.push({
        name,
        scenario: "missing observations break paths",
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
