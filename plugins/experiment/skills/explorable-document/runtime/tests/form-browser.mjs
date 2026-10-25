/** Real Chromium acceptance: run explicitly with pnpm test:forms [output-dir]. */
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
const output = path.resolve(process.argv[2] || "form-evidence");
await mkdir(output, { recursive: true });
const work = await mkdtemp(path.join(os.tmpdir(), "form-live-"));
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
  await frame.locator(".ed-field").first().waitFor();
  await settle(frame);
  return frame;
}
async function settle(frame) {
  await frame.evaluate(async () => {
    await document.fonts.ready;
    await new Promise(requestAnimationFrame);
  });
}
async function inspectLayout(frame) {
  assert.equal(
    await frame.evaluate(
      () => document.documentElement.scrollWidth > innerWidth + 1,
    ),
    false,
    "horizontal overflow",
  );
}
async function verifyFields(frame) {
  const state = async () =>
    JSON.parse(await frame.locator("#reading").textContent());
  assert.equal(
    await frame.locator("#first-option-0").getAttribute("aria-describedby"),
    "first-help first-option-0-description",
  );
  assert.equal(
    await frame.locator("#first-option-0").evaluate((el) => el.checkValidity()),
    false,
  );
  await frame.getByLabel("Alpha", { exact: true }).first().check();
  await frame.locator("#first-option-0").press("ArrowRight");
  assert.equal((await state()).first, "b");
  assert.equal((await state()).second, "a");
  assert.equal((await state()).callbacks, 2);
  await frame.locator("#choice").selectOption("b");
  await frame.locator("#choice").selectOption("");
  assert.equal((await state()).chosen, null);
  assert.equal(
    await frame.locator('#required-choice option[value=""]').isDisabled(),
    true,
  );
  await frame.locator("#check").focus();
  await frame.locator("#check").press("Space");
  assert.equal((await state()).checked, true);
  await frame.locator("#range").focus();
  await frame.locator("#range").press("ArrowRight");
  assert.equal((await state()).range, 5);
  assert.equal(await frame.locator("#fixed").inputValue(), "b");
  assert.equal(await frame.locator("#fixed").isDisabled(), true);
  await frame.locator("#choice").selectOption("b");
  await frame.locator("#mode").selectOption("disabled");
  assert.equal(await frame.locator("#choice").inputValue(), "b");
  assert.equal(
    await frame.locator('#choice option[value="b"]').isDisabled(),
    true,
  );
  await frame.locator("#mode").selectOption("duplicate");
  assert.equal(await frame.locator(".ed-field-diagnostic").count(), 2);
  await frame.locator("#mode").selectOption("empty");
  assert.equal(
    await frame.locator(".ed-field-diagnostic").count(),
    2,
    "stale values diagnose rather than pick a fallback",
  );
  await frame.locator("#reset").click();
  assert.equal(await frame.locator("#choice").isDisabled(), true);
  await frame.locator("#mode").selectOption("error");
  assert.equal(
    await frame.locator("#first-option-0").getAttribute("aria-invalid"),
    "true",
  );
  await frame.locator("#first-option-0").check();
  assert.equal(
    await frame
      .locator("#first-option-0")
      .evaluate((el) => el.validationMessage),
    "Domain rejection",
  );
  await frame.locator("#mode").selectOption("normal");
  assert.equal(
    await frame.locator("#first-option-0").evaluate((el) => el.checkValidity()),
    true,
  );
  await frame.locator("#reset").click();
  assert.deepEqual(await state(), {
    first: null,
    second: "a",
    chosen: null,
    checked: false,
    range: 4,
    callbacks: 3,
  });
}
async function verifyNumeric(frame) {
  const tp = frame.locator("#tp"),
    fn = frame.locator("#fn"),
    ratio = frame.locator("#ratio");
  assert.equal(await ratio.textContent(), "85.0%");
  assert.equal(
    await frame.locator("#optional").evaluate((el) => el.checkValidity()),
    true,
  );
  await tp.fill("-");
  assert.equal(await tp.inputValue(), "-");
  assert.equal(await ratio.textContent(), "Waiting");
  assert.equal(await tp.getAttribute("aria-invalid"), null);
  assert.equal(await tp.evaluate((el) => el.validity.valid), false);
  const before = await frame.locator("#reset").boundingBox();
  await frame.locator("#reset").click();
  assert.equal(
    await ratio.textContent(),
    "85.0%",
    "blur must not lose the reset click",
  );
  assert(before);
  for (const draft of ["", "1e", "1e-", "2.5", "1000001", "1e309", "12x"]) {
    await tp.fill(draft);
    await tp.blur();
    assert.equal(await tp.inputValue(), draft);
    assert.equal(await ratio.textContent(), "Waiting");
    assert.equal(await tp.getAttribute("aria-invalid"), "true");
    const errorId = await tp.getAttribute("aria-describedby");
    assert(errorId.includes("tp-error"));
    assert.equal(await tp.evaluate((el) => el.checkValidity()), false);
  }
  await tp.fill("0");
  await fn.fill("0");
  assert.equal(await ratio.textContent(), "Undefined");
  await tp.fill("1e3");
  await fn.fill("0");
  assert.equal(await ratio.textContent(), "100.0%");
  await frame.locator("#domain").click();
  assert.equal(await tp.evaluate((el) => el.validationMessage), "Domain error");
  await frame.locator("#domain").click();
  assert.equal(await tp.evaluate((el) => el.validationMessage), "");
  await fn.fill("2.5");
  assert.equal(await fn.getAttribute("aria-invalid"), "true");
  await frame.locator("#reset").click();
  assert.equal(await ratio.textContent(), "85.0%");
  await frame.locator("#optional").fill(".5");
  assert.equal(
    await frame.locator("#optional").evaluate((el) => el.checkValidity()),
    true,
  );
}
async function verifyCode(frame) {
  const first = frame.locator("#first-code-text"),
    second = frame.locator("#second-code-text");
  const selection = async (locator) =>
    locator.evaluate((el) => ({
      start: el.selectionStart,
      end: el.selectionEnd,
      length: el.value.length,
      focused: document.activeElement === el,
    }));
  await frame.locator("#first-code-select").click();
  let selected = await selection(first);
  assert.equal(selected.start, 0);
  assert.equal(selected.end, selected.length);
  assert(selected.focused);
  assert.equal((await selection(second)).end, 0);
  assert(
    (await frame.locator(".ed-code-status").first().textContent()).includes(
      "Text selected",
    ),
  );
  await frame.locator("#draft").fill("42");
  assert.equal(
    await frame
      .locator("#draft")
      .evaluate((el) => document.activeElement === el),
    true,
  );
  assert.equal(
    await frame.locator(".ed-code-status").first().textContent(),
    "",
  );
  assert((await first.inputValue()).includes("42"));
  await frame.locator("#second-code-select").click();
  selected = await selection(second);
  assert.equal(selected.end, selected.length);
  assert(selected.focused);
  assert((await second.inputValue()).includes("<b>literal</b>"));
  assert(!(await second.inputValue()).includes("\r"));
  await frame.locator("#wrap").uncheck();
  assert.equal(await second.getAttribute("wrap"), "off");
  assert.equal(
    await second.evaluate((el) => el.scrollWidth > el.clientWidth),
    true,
  );
  await frame.locator("#mode").selectOption("invalid");
  assert.equal(await first.inputValue(), "");
  assert.equal(await frame.locator("#first-code-select").isDisabled(), true);
  assert(
    (await frame.locator(".ed-code-error").textContent()).includes("cycle"),
  );
  await frame.locator("#mode").selectOption("null");
  assert.equal(await first.inputValue(), "null");
  await frame.locator("#mode").selectOption("empty");
  assert.equal(await second.inputValue(), "");
  assert.equal(await frame.locator("#second-code-select").isDisabled(), true);
  await frame.locator("#mode").selectOption("both");
  assert(
    (await frame.locator(".ed-code-error").textContent()).includes(
      "exactly one",
    ),
  );
  await frame.locator("#mode").selectOption("normal");
  assert.equal(await frame.locator(".ed-code-error").count(), 0);
  assert.equal(
    await frame.evaluate(
      () =>
        document.querySelectorAll(".ed-code-panel script,.ed-code-panel b")
          .length,
    ),
    0,
  );
}
async function verifyExamples(frame) {
  await frame.locator("#provider-option-2").check();
  assert(
    (await frame.locator("#configuration-text").inputValue()).includes(
      "Google",
    ),
  );
  await frame.locator("#reset-settings").click();
  assert(
    (await frame.locator("#configuration-text").inputValue()).includes(
      "OpenAI",
    ),
  );
  await frame.locator("#tp").fill("");
  assert.equal(await frame.locator("#calculated-text").inputValue(), "");
  assert.equal(await frame.locator("#calculated-select").isDisabled(), true);
  await frame.locator("#reset-counts").click();
  assert.equal(await frame.locator("#calculation").textContent(), "85.0%");
  await frame.locator("#python-select").click();
  assert.equal(
    await frame
      .locator("#python-text")
      .evaluate(
        (el) => el.selectionStart === 0 && el.selectionEnd === el.value.length,
      ),
    true,
  );
}
try {
  const cases = (
    process.env.FORM_CASES || "Fields,Numeric,Code,Examples"
  ).split(",");
  for (const name of cases) {
    const source = path.join(work, name);
    await mkdir(source);
    await cp(path.join(root, "fixtures/forms"), source, { recursive: true });
    await writeFile(
      path.join(source, "document.tsx"),
      `export {default} from './${name.toLowerCase()}';`,
    );
    await writeFile(
      path.join(source, "artifact.json"),
      JSON.stringify({
        schema_version: 1,
        title: `${name} acceptance fixture`,
        summary: "Synthetic form/code fixture.",
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
    await inspectLayout(frame);
    results.push({ name, containerWidth: 350, status: "passed" });
    frame = await open();
    if (name === "Fields") await verifyFields(frame);
    if (name === "Numeric") await verifyNumeric(frame);
    if (name === "Code") await verifyCode(frame);
    if (name === "Examples") await verifyExamples(frame);
    results.push({ name, scenario: "behavior", status: "passed" });
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
