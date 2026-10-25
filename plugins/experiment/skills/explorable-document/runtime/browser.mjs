import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { chromium } from "playwright";

export async function inspect(rendered, source, evidence) {
  const spec = JSON.parse(
    await readFile(path.join(source, "artifact.json"), "utf8"),
  );
  let checks = { scenarios: [] };
  try {
    checks = JSON.parse(
      await readFile(path.join(source, "checks.json"), "utf8"),
    );
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  const server = createServer(async (req, res) => {
    const name = req.url === "/" ? "index.html" : req.url.slice(1);
    if (
      ![
        "index.html",
        "viewer.js",
        "theme.css",
        "viewer.css",
        "document.json",
        "artifact.json",
      ].includes(name)
    ) {
      res.writeHead(404);
      res.end();
      return;
    }
    try {
      res.setHeader(
        "Content-Type",
        name.endsWith(".json")
          ? "application/json"
          : name.endsWith(".js")
            ? "text/javascript"
            : name.endsWith(".css")
              ? "text/css"
              : "text/html",
      );
      res.end(await readFile(path.join(rendered, name)));
    } catch {
      res.writeHead(404);
      res.end();
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  let browser;
  const result = {
    status: "failed",
    browser: "chromium",
    version: "",
    interactions: [],
    viewports: [],
    accessibility: [],
    unexpected_requests: [],
    errors: [],
  };
  try {
    browser = await chromium.launch();
    result.version = browser.version();
    const context = await browser.newContext();
    const page = await context.newPage();
    page.setDefaultTimeout(8000);
    const base = `http://127.0.0.1:${server.address().port}`;
    page.on("request", (req) => {
      if (!req.url().startsWith(`${base}/`) && !req.url().startsWith("data:"))
        result.unexpected_requests.push(req.url());
    });
    page.on("pageerror", (e) => result.errors.push(e.message));
    async function open() {
      await page.goto(base);
      await page.locator("#status").filter({ hasText: "Ready ·" }).waitFor();
    }
    for (const scenario of checks.scenarios) {
      await open();
      const frame = page.frameLocator("#document");
      for (const step of scenario.steps) {
        const locator = frame.locator(step.selector).nth(step.index || 0);
        if (step.action === "click") await locator.click();
        else if (step.action === "fill") await locator.fill(step.value);
        else if (step.action === "select")
          await locator.selectOption(step.value);
        else if (step.action === "press") await locator.press(step.value);
        else if (step.action === "text")
          assert.equal((await locator.textContent()).trim(), step.value);
        else if (step.action === "value")
          assert.equal(await locator.inputValue(), step.value);
        else throw Error(`Unsupported check action ${step.action}`);
      }
      result.interactions.push({ id: scenario.interaction, status: "passed" });
    }
    for (const interaction of spec.interactions)
      assert(
        result.interactions.some((x) => x.id === interaction.id),
        `Missing behavioral evidence for ${interaction.id}: add checks.json scenario.`,
      );
    await open();
    const inner = page.frames().find((f) => f.parentFrame());
    assert.equal(
      await inner.evaluate(() => {
        try {
          void parent.document.body;
          return false;
        } catch {
          return true;
        }
      }),
      true,
    );
    assert.equal(
      await inner.evaluate(() => {
        try {
          localStorage.setItem("probe", "1");
          return false;
        } catch {
          return true;
        }
      }),
      true,
    );
    assert.equal(
      await page.locator("#document").getAttribute("sandbox"),
      "allow-scripts",
    );
    if (!spec.handoff)
      assert.equal(await page.locator("#share").isVisible(), false);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mkdir(evidence, { recursive: true });
    for (const width of [390, 1280])
      for (const theme of ["dark", "light"]) {
        await page.setViewportSize({ width, height: 900 });
        await page.locator("#theme").selectOption(theme);
        await inner.locator(`html[data-theme=${theme}]`).waitFor();
        assert(
          await inner.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth + 1,
          ),
          "Horizontal overflow",
        );
        const scan = await new AxeBuilder({ page }).analyze();
        const violations = scan.violations.filter(
          (v) => v.impact === "serious" || v.impact === "critical",
        );
        result.accessibility.push({
          width,
          theme,
          violations: violations.map((v) => ({ id: v.id, help: v.help })),
        });
        assert.equal(
          violations.length,
          0,
          JSON.stringify(violations.map((v) => v.id)),
        );
        await page.screenshot({
          path: path.join(evidence, `${width}-${theme}.png`),
          fullPage: true,
        });
        result.viewports.push({ width, theme, status: "passed" });
      }
    assert.equal(result.errors.length, 0, JSON.stringify(result.errors));
    assert.equal(
      result.unexpected_requests.length,
      0,
      JSON.stringify(result.unexpected_requests),
    );
    result.status = "passed";
  } catch (error) {
    result.errors.push(String(error));
  } finally {
    await browser?.close();
    await new Promise((resolve) => server.close(resolve));
  }
  // Early interaction failures precede screenshot setup; retain their diagnostics.
  await mkdir(evidence, { recursive: true });
  await writeFile(
    path.join(evidence, "browser.json"),
    JSON.stringify(result, null, 2),
  );
  return result;
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    const result = await inspect(
      ...process.argv.slice(2).map((x) => path.resolve(x)),
    );
    console.log(JSON.stringify(result));
    if (result.status !== "passed") process.exitCode = 6;
  } catch (error) {
    console.error(String(error));
    process.exitCode = 6;
  }
}
