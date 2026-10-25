/** Maintainer live acceptance: explicit browser/receiver tests, never run on PR CI. */
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import path from "node:path";
import { chromium } from "playwright";

const [url, exported, output] = process.argv.slice(2);
const browser = await chromium.launch();
const context = await browser.newContext({ acceptDownloads: true });
const page = await context.newPage();
page.setDefaultTimeout(8000);
const evidence = { checks: [], browser: browser.version() };
let staticServer;
try {
  await page.goto(url);
  await page.locator("#status").filter({ hasText: "Ready ·" }).waitFor();
  const frame = page.frameLocator("#document");
  await frame.getByRole("slider", { name: "Arrival rate" }).fill("6");
  await page.locator("#share").click();
  await page.locator("#review[open]").waitFor();
  assert.deepEqual(JSON.parse(await page.locator("#snapshot").textContent()), {
    arrival: 6,
    service: 8,
    jobs: 3,
  });
  await frame
    .getByRole("slider", { name: "Arrival rate" })
    .fill("7", { force: true });
  await page.locator("#comment").fill("Reviewed six arrivals.");
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    assert(
      await page.evaluate(() =>
        document.querySelector("#review").contains(document.activeElement),
      ),
    );
  }
  await page.route("**/api/submissions", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ message: "Simulated storage failure" }),
    }),
  );
  await page.locator("#submit").click();
  await page.locator("#receipt").filter({ hasText: "Not saved:" }).waitFor();
  assert.equal(await page.locator("#comment").isDisabled(), true);
  await page.unroute("**/api/submissions");
  const requestPromise = page.waitForRequest((request) =>
    request.url().endsWith("/api/submissions"),
  );
  await page.locator("#submit").click();
  const request = await requestPromise;
  await page
    .locator("#receipt")
    .filter({ hasText: "Saved for the agent" })
    .waitFor();
  const sent = request.postDataJSON();
  assert.deepEqual(sent, {
    snapshot: { arrival: 6, service: 8, jobs: 3 },
    comment: "Reviewed six arrivals.",
  });
  const original = await (await request.response()).json();
  const headers = {
    authorization: await request.headerValue("authorization"),
    "idempotency-key": await request.headerValue("idempotency-key"),
    "content-type": "application/json",
    origin: new URL(request.url()).origin,
  };
  const retry = await context.request.post(request.url(), {
    headers,
    data: sent,
  });
  assert.equal(retry.status(), 200);
  assert.equal((await retry.json()).submission_id, original.submission_id);
  const conflicting = await context.request.post(request.url(), {
    headers,
    data: { ...sent, comment: "Changed" },
  });
  assert.equal(conflicting.status(), 409);
  const badSchema = await context.request.post(request.url(), {
    headers: { ...headers, "idempotency-key": "new-request-12345678" },
    data: { snapshot: { arrival: 999 }, comment: "" },
  });
  assert.equal(badSchema.status(), 422);
  evidence.checks.push(
    "frozen review",
    "dialog keyboard containment",
    "failed-save retry",
    "idempotent receipt",
    "conflicting retry rejected",
    "receiver schema rejection",
  );
  await page.keyboard.press("Escape");
  assert.equal(await page.locator("#review").getAttribute("open"), null);
  await page.waitForFunction(
    () => document.querySelector("#share") === document.activeElement,
  );
  await page.locator("#theme").selectOption("light");
  assert.equal(
    await frame.getByRole("slider", { name: "Arrival rate" }).inputValue(),
    "7",
  );
  await frame.getByRole("slider", { name: "Arrival rate" }).focus();
  await page.keyboard.press("ArrowRight");
  assert.equal(
    await frame.getByRole("slider", { name: "Arrival rate" }).inputValue(),
    "8",
  );
  await page.reload();
  await page.locator("#status").filter({ hasText: "Ready ·" }).waitFor();
  assert.equal(
    await frame.getByRole("slider", { name: "Arrival rate" }).inputValue(),
    "4",
  );
  assert.equal(await page.locator("#share").textContent(), "Review snapshot");
  // Global and sibling-frame messages cannot invoke the dedicated channel receiver.
  await page.evaluate(() => {
    window.postMessage(
      {
        version: 1,
        type: "snapshot",
        session: "forged",
        request: "forged",
        value: { arrival: 20 },
      },
      "*",
    );
    const sibling = document.createElement("iframe");
    sibling.srcdoc =
      '<script>parent.postMessage({type:"snapshot",version:1},"*")</script>';
    document.body.append(sibling);
  });
  assert.equal(await page.locator("#review").getAttribute("open"), null);
  const inner = page
    .frames()
    .find((f) => f.parentFrame() && f.url() === "about:srcdoc");
  assert(
    await inner.evaluate(() => {
      try {
        void parent.sessionStorage;
        return false;
      } catch {
        return true;
      }
    }),
  );
  const blocked = await inner.evaluate(async () => {
    try {
      await fetch("/api/submissions", { method: "POST", body: "{}" });
      return false;
    } catch {
      return true;
    }
  });
  assert(blocked);
  evidence.checks.push(
    "theme preserves state",
    "keyboard range",
    "reload resets input and retains viewer capability",
    "wrong-frame messages ignored",
    "parent storage denied",
    "direct frame submission blocked",
  );
  await page.locator("#share").click();
  await page.locator("#review[open]").waitFor();
  await page.locator("#submit").click();
  await page
    .locator("#receipt")
    .filter({ hasText: "Saved for the agent" })
    .waitFor();
  evidence.checks.push("multiple intentional submissions");
  // Portable viewer at a non-root subpath, with no session and no receiver.
  staticServer = createServer(async (req, res) => {
    const name = req.url.startsWith("/bundle/")
      ? req.url.slice("/bundle/".length)
      : "";
    if (
      ![
        "",
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
        name.endsWith(".js")
          ? "text/javascript"
          : name.endsWith(".css")
            ? "text/css"
            : name.endsWith(".json")
              ? "application/json"
              : "text/html",
      );
      res.end(
        await readFile(path.join(exported, "rendered", name || "index.html")),
      );
    } catch {
      res.writeHead(404);
      res.end();
    }
  });
  await new Promise((resolve) => staticServer.listen(0, "127.0.0.1", resolve));
  const portable = await context.newPage();
  await portable.goto(
    `http://127.0.0.1:${staticServer.address().port}/bundle/`,
  );
  await portable.locator("#status").filter({ hasText: "Ready ·" }).waitFor();
  assert.equal(
    await portable.locator("#share").textContent(),
    "Download snapshot",
  );
  await portable.locator("#share").click();
  await portable.locator("#review[open]").waitFor();
  assert.equal(await portable.locator("#submit").isVisible(), false);
  const downloaded = portable.waitForEvent("download");
  await portable.locator("#download").click();
  const download = await downloaded;
  const data = JSON.parse(await readFile(await download.path(), "utf8"));
  assert.equal(data.snapshot.arrival, 4);
  assert.equal(data.comment, "");
  assert.equal(
    await portable.locator("#document").getAttribute("sandbox"),
    "allow-scripts",
  );
  evidence.checks.push(
    "static subpath",
    "static snapshot download",
    "static sandbox retained",
  );
  evidence.status = "passed";
} catch (error) {
  evidence.status = "failed";
  evidence.error = error.stack || String(error);
  process.exitCode = 1;
} finally {
  await browser.close();
  if (staticServer) await new Promise((resolve) => staticServer.close(resolve));
  await mkdir(output, { recursive: true });
  await writeFile(
    path.join(output, "live.json"),
    JSON.stringify(evidence, null, 2),
  );
  console.log(JSON.stringify(evidence));
}
