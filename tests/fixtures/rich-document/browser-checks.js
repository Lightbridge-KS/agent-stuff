// Test-only instrumentation, prepended by test_rich_document_browser.py.
(() => {
  const checks = [];
  const check = (name, pass) => checks.push({name, pass: Boolean(pass)});
  const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
  let active = 0;
  const render = mermaid.render.bind(mermaid);
  mermaid.render = async (...args) => {
    check("renders are serialized", active++ === 0);
    try {
      const tabs = [...document.querySelectorAll('[role="tab"]')];
      // Switch while each render is suspended: layout must not depend on tab state.
      tabs[1].click();
      await frame();
      tabs[0].click();
      if (args[1].includes("FAIL_FOR_TEST")) {
        args[2].append(document.createElement("svg"));
        throw new Error("Injected layout failure without a library name");
      }
      return await render(...args);
    } finally { active--; }
  };

  window.addEventListener("load", async () => {
    const report = document.createElement("pre");
    report.id = "rd-test-result";
    report.textContent = "RUNNING browser regressions";
    document.body.prepend(report);
    const printResult = document.createElement("pre");
    printResult.id = "rd-print-result";
    printResult.textContent = "Print check: activate browser print media to run";
    document.body.prepend(printResult);
    matchMedia("print").addEventListener("change", event => {
      if (!event.matches) return;
      const panels = [...document.querySelectorAll(".tab-pane")];
      const pass = panels.length === 3 && panels.every(p =>
        getComputedStyle(p).display !== "none" && p.getBoundingClientRect().height > 0 && p.querySelector("svg"));
      printResult.dataset.status = pass ? "PASS" : "FAIL";
      printResult.textContent = `${printResult.dataset.status}: all tab diagrams present in print layout`;
    });
    const originalDark = document.body.classList.contains("quarto-dark");
    try {
      const deadline = performance.now() + 15000;
      while (document.querySelector('[data-rd-state="pending"]') && performance.now() < deadline) await frame();
      check("queue completes", !document.querySelector('[data-rd-state="pending"]'));
      check("five diagrams render despite one failure", document.querySelectorAll('[data-rd-state="rendered"]').length === 5);
      check("one local error", document.querySelectorAll('[data-rd-state="failed"]').length === 1);
      const failed = document.querySelector('[data-rd-state="failed"]');
      check("error retains only failed source", failed?.textContent.includes("FAIL_FOR_TEST") && !failed?.textContent.includes("Cylinder"));
      check("error has no SVG or enlarge button", failed && !failed.querySelector("svg,button"));
      check("stage cleaned", !document.querySelector(".rd-render-stage"));
      check("later diagram renders", document.querySelector('#after [data-rd-state="rendered"]'));
      check("ordinary quotes render", document.querySelector("main").textContent.includes("“hello” and ‘goodbye’"));
      const diagrams = [...document.querySelectorAll("svg.mermaid-js")];
      check("finite nonzero geometry", diagrams.every(s => {
        const b = s.viewBox.baseVal;
        return [b.x,b.y,b.width,b.height].every(Number.isFinite) && b.width > 0 && b.height > 0;
      }));
      check("SVG styles retained", diagrams.every(s => s.querySelector("style")));
      const ids = [...document.querySelectorAll("svg [id], svg[id]")].map(n => n.id);
      check("SVG IDs unique", ids.length === new Set(ids).size);
      check("unvisited sequence tab already rendered", document.querySelector('#tabset-1-3 svg'));

      const colors = () => {
        const svg = document.querySelector("#shapes svg, .rd-dialog svg");
        const node = label => [...svg.querySelectorAll(".node")].find(n => n.querySelector(".nodeLabel")?.textContent === label);
        const rectangle = getComputedStyle(node("Rectangle").querySelector("rect"));
        const cylinder = getComputedStyle(node("Cylinder").querySelector("path"));
        check("cylinder matches rectangle", cylinder.fill === rectangle.fill && cylinder.stroke === rectangle.stroke);
        const stadium = node("Stadium");
        check("stadium fill matches", getComputedStyle(stadium.querySelector('path[stroke="none"]')).fill === rectangle.fill);
        const outline = getComputedStyle(stadium.querySelector('path[fill="none"]'));
        check("stadium outline stays unfilled", outline.fill === "none" && outline.stroke === rectangle.stroke);
        for (const label of ["Diamond", "Circle"]) {
          const shape = node(label).querySelector("polygon,path,circle");
          check(label + " theme", getComputedStyle(shape).fill === rectangle.fill);
        }
      };
      const toggle = document.querySelector(".quarto-color-scheme-toggle");
      for (let i = 0; i < 2; i++) {
        colors();
        document.querySelector("#shapes .rd-diagram > button").click();
        colors();
        [...document.querySelectorAll(".rd-dialog button")].find(b => b.textContent === "Close").click();
        await frame();
        toggle.click();
        await frame();
      }
      const tab = document.querySelector('#tabset-1-2-tab');
      tab.click();
      await frame();
      check("hidden subgraph becomes visible", document.querySelector('#tabset-1-2 svg').getBoundingClientRect().height > 0);
      const labelBox = document.querySelector('#tabset-1-2 .cluster-label').getBoundingClientRect();
      const nodeBox = document.querySelector('#tabset-1-2 .node').getBoundingClientRect();
      check("wrapped cluster title clears first node", labelBox.bottom <= nodeBox.top);
      const opener = document.querySelector('#tabset-1-2 .rd-diagram > button');
      const svg = document.querySelector('#tabset-1-2 svg');
      opener.click();
      check("enlargement moves completed SVG", document.querySelector(".rd-dialog svg") === svg);
      const viewport = document.querySelector(".rd-viewport");
      const width = svg.getBoundingClientRect().width;
      viewport.dispatchEvent(new KeyboardEvent("keydown", {key:"+", bubbles:true}));
      check("keyboard zoom", svg.getBoundingClientRect().width > width);
      viewport.dispatchEvent(new KeyboardEvent("keydown", {key:"0", bubbles:true}));
      check("keyboard reset", Math.abs(svg.getBoundingClientRect().width - width) < 1);
      [...document.querySelectorAll(".rd-dialog button")].find(b => b.textContent === "Close").click();
      await frame();
      check("close restores SVG and focus", opener.previousElementSibling === svg && document.activeElement === opener);
      check("tab selection retained", tab.getAttribute("aria-selected") === "true");
    } catch (error) {
      checks.push({name: String(error), pass:false});
    } finally {
      if (document.body.classList.contains("quarto-dark") !== originalDark) document.querySelector(".quarto-color-scheme-toggle").click();
      const result = {status: checks.every(c => c.pass) ? "PASS" : "FAIL", checks};
      report.dataset.status = result.status;
      report.textContent = JSON.stringify(result, null, 2);
    }
  }, {once:true});
})();
