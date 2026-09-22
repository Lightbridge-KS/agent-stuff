/* ask-form rich prose: everything that makes agent explanation readable, behind one small surface.
     AskRich.prose(md)      sanitized GFM markdown → node; mermaid fences become diagrams, code gets a
                            language label, Copy and highlighting, `> [!NOTE]` alerts become callouts
     AskRich.diagram(src)   mermaid source → node; Enlarge dialog; re-rendered on light/dark change
   Libraries are vendored under /static/vendor and loaded only when a page needs them.
   Diagram behaviour is copied from rich-document's viewer.js (enlarge dialog, serial render queue). */
(() => {
  "use strict";

  const SANITIZE = { FORBID_TAGS: ["img", "style", "form", "input"], FORBID_ATTR: ["style", "onerror", "onload"] };
  const ALERTS = { NOTE: "Note", TIP: "Tip", IMPORTANT: "Important", WARNING: "Warning", CAUTION: "Caution" };

  const el = (tag, attrs = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children) if (c != null) node.append(c);
    return node;
  };

  const scripts = {};
  const load = (file, global) => (scripts[file] ??= new Promise((resolve, reject) => {
    if (window[global]) return resolve(window[global]);
    const s = el("script", { src: `/static/vendor/${file}` });
    s.onload = () => (window[global] ? resolve(window[global]) : reject(new Error(`${global} missing`)));
    s.onerror = () => reject(new Error(`${file} failed to load`));
    document.head.append(s);
  }));

  // ── code ───────────────────────────────────────────────────────────────────

  // Copies the exact source text; if the clipboard is refused, selects the block for ⌘C instead.
  const copyButton = (text, frame) => {
    const b = el("button", { type: "button", class: "copy", text: "Copy" });
    b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(text); b.textContent = "Copied"; }
      catch {
        const range = document.createRange();
        range.selectNodeContents(frame.querySelector("pre"));
        getSelection().removeAllRanges();
        getSelection().addRange(range);
        b.textContent = "Selected — press ⌘C";
      }
      setTimeout(() => { b.textContent = "Copy"; }, 1600);
    });
    return b;
  };

  const codeFrame = (lang, text) => {
    const frame = el("div", { class: "code" });
    frame.append(el("div", { class: "code-head" }, el("span", { class: "code-lang", text: lang || "text" }), copyButton(text, frame)));
    return frame;
  };

  const enhanceCode = (pre) => {
    const code = pre.querySelector("code");
    const text = (code || pre).textContent.replace(/\n$/, "");
    const lang = (code?.className.match(/language-([\w+#.-]+)/) || [])[1]?.toLowerCase() || "";
    if (lang === "mermaid") return pre.replaceWith(diagram(text));
    const frame = codeFrame(lang, text);
    pre.replaceWith(frame);
    frame.append(pre);
    if (!code || !lang || lang === "text" || lang === "plain") return;
    load("highlight.min.js", "hljs").then((hljs) => {
      if (!hljs.getLanguage(lang)) return;
      hljs.configure({ ignoreUnescapedHTML: true });
      hljs.highlightElement(code);
    }).catch(() => { /* plain code is still readable */ });
  };

  // ── alerts ─────────────────────────────────────────────────────────────────

  const enhanceAlert = (quote) => {
    const first = quote.firstElementChild;
    const m = first?.tagName === "P" && first.textContent.match(/^\s*\[!(\w+)\]/);
    const kind = m && m[1].toUpperCase();
    if (!kind || !ALERTS[kind]) return;
    const lead = first.firstChild;
    if (lead?.nodeType === Node.TEXT_NODE) lead.textContent = lead.textContent.replace(/^\s*\[!\w+\]\s*/, "");
    if (!first.textContent.trim() && !first.children.length) first.remove();
    const box = el("div", { class: `callout callout-${kind.toLowerCase()}`, role: "note" },
      el("div", { class: "callout-title", text: ALERTS[kind] }));
    box.append(...quote.childNodes);
    quote.replaceWith(box);
  };

  // ── prose ──────────────────────────────────────────────────────────────────

  const prose = (src) => {
    const box = el("div", { class: "prose" });
    if (!src) return box;
    try {
      box.innerHTML = window.DOMPurify.sanitize(window.marked.parse(src, { gfm: true, breaks: false }), SANITIZE);
    } catch { box.textContent = src; return box; }
    for (const a of box.querySelectorAll("a")) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
    for (const q of [...box.querySelectorAll("blockquote")]) enhanceAlert(q);
    for (const pre of [...box.querySelectorAll("pre")]) enhanceCode(pre);
    return box;
  };

  // ── diagrams ───────────────────────────────────────────────────────────────

  const dark = matchMedia("(prefers-color-scheme: dark)");
  const diagrams = new Set();
  let queue = Promise.resolve();
  let serial = 0;
  let dialogOpen = false;
  let staleTheme = false;

  const button = (label, action, attrs = {}) => el("button", { type: "button", text: label, onclick: action, ...attrs });

  const diagramError = (wrap, source, reason) => {
    wrap.dataset.state = "failed";
    wrap.replaceChildren(el("details", { class: "diagram-error" },
      el("summary", { text: "This diagram could not be displayed. Show details and source." }),
      el("pre", { text: String(reason?.message || reason).slice(0, 2000) }),
      el("pre", { text: source })));
  };

  const renderOne = async (wrap) => {
    if (!wrap.isConnected) await new Promise(requestAnimationFrame);
    const source = wrap._source;
    const mermaid = await load("mermaid.min.js", "mermaid");
    mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: dark.matches ? "dark" : "default",
      suppressErrorRendering: true, fontFamily: "-apple-system, system-ui, sans-serif" });
    // Measure in an off-screen stage so diagrams in collapsed or hidden panels still lay out.
    let ancestor = wrap;
    while (ancestor && ancestor.getBoundingClientRect().width === 0) ancestor = ancestor.parentElement;
    const stage = el("div", { class: "diagram-stage", "aria-hidden": "true" });
    stage.style.width = `${Math.max(240, ancestor?.getBoundingClientRect().width || 680)}px`;
    document.body.append(stage);
    try {
      const { svg: out } = await mermaid.render(`ask-mermaid-${++serial}`, source, stage);
      // securityLevel "strict" has Mermaid sanitize every label itself. A second DOMPurify pass would
      // strip the HTML inside foreignObject labels (blank nodes), so the output is used as-is, as in
      // rich-document; the CSP still forbids any script that could survive.
      stage.innerHTML = out;
      const svg = stage.querySelector("svg");
      const box = svg?.viewBox.baseVal;
      if (!box || !(box.width > 0 && box.height > 0)) throw new Error("Diagram layout has invalid dimensions.");
      svg.style.width = "100%";
      svg.style.maxWidth = `${box.width}px`;
      svg.style.height = "auto";
      const control = button("Enlarge", () => enlarge(svg, control), { class: "diagram-enlarge", "aria-label": "Enlarge diagram" });
      wrap.replaceChildren(svg, control);
      wrap.dataset.state = "rendered";
    } finally {
      stage.remove();
    }
  };

  const schedule = (wrap) => {
    wrap.dataset.state = "pending";
    queue = queue.then(() => renderOne(wrap)).catch((e) => diagramError(wrap, wrap._source, e));
  };

  const diagram = (source) => {
    const wrap = el("div", { class: "diagram", "data-state": "pending" }, el("pre", { class: "diagram-source", text: source }));
    wrap._source = source;
    diagrams.add(wrap);
    schedule(wrap);
    return wrap;
  };

  const rerenderAll = () => {
    if (dialogOpen) { staleTheme = true; return; }
    for (const w of diagrams) if (w.isConnected && w.dataset.state !== "failed") schedule(w);
  };
  dark.addEventListener("change", rerenderAll);

  function enlarge(svg, opener) {
    dialogOpen = true;
    const dialog = el("dialog", { class: "diagram-dialog", "aria-label": "Enlarged diagram" });
    const viewport = el("div", { class: "diagram-viewport", tabindex: "0", "aria-label": "Diagram canvas. Arrow keys scroll; plus and minus zoom; zero resets." });
    const previous = Object.fromEntries(["style", "width", "height"].map((n) => [n, svg.getAttribute(n)]));
    const box = svg.viewBox.baseVal;
    const naturalWidth = box.width || 900, naturalHeight = box.height || 500;
    const status = el("output", { "aria-live": "polite" });
    let zoom = 1;
    const resize = (v) => {
      zoom = Math.min(4, Math.max(0.25, v));
      svg.style.maxWidth = "none";
      svg.style.width = `${naturalWidth * zoom}px`;
      svg.style.height = `${naturalHeight * zoom}px`;
      status.textContent = `${Math.round(zoom * 100)}%`;
    };
    const reset = () => { resize(Math.min(1, (viewport.clientWidth - 24) / naturalWidth)); viewport.scrollTo(0, 0); };
    const toolbar = el("div", { class: "diagram-toolbar" },
      button("−", () => resize(zoom / 1.25), { "aria-label": "Zoom out" }),
      button("+", () => resize(zoom * 1.25), { "aria-label": "Zoom in" }),
      button("Reset", reset), status, el("span", { class: "grow" }),
      button("Close", () => dialog.close(), { class: "btn quiet" }));
    // Move the SVG rather than cloning it, so Mermaid's scoped styles and marker ids stay unique.
    viewport.append(svg);
    dialog.append(toolbar, viewport);
    document.body.append(dialog);
    dialog.addEventListener("close", () => {
      opener.before(svg);
      for (const [n, v] of Object.entries(previous)) { if (v === null) svg.removeAttribute(n); else svg.setAttribute(n, v); }
      dialog.remove();
      opener.focus();
      dialogOpen = false;
      if (staleTheme) { staleTheme = false; rerenderAll(); }
    }, { once: true });
    viewport.addEventListener("keydown", (e) => {
      if (!["+", "=", "-", "0"].includes(e.key)) return;
      e.preventDefault();
      if (e.key === "0") reset(); else resize(e.key === "-" ? zoom / 1.25 : zoom * 1.25);
    });
    let drag = null;
    viewport.addEventListener("pointerdown", (e) => {
      if (e.pointerType !== "mouse" || e.button !== 0) return;
      drag = { x: e.clientX, y: e.clientY, left: viewport.scrollLeft, top: viewport.scrollTop };
      viewport.setPointerCapture(e.pointerId);
    });
    viewport.addEventListener("pointermove", (e) => { if (drag) viewport.scrollTo(drag.left + drag.x - e.clientX, drag.top + drag.y - e.clientY); });
    viewport.addEventListener("pointerup", () => { drag = null; });
    viewport.addEventListener("pointercancel", () => { drag = null; });
    dialog.addEventListener("keydown", (e) => {
      if (e.key !== "Tab") return;
      const controls = [...dialog.querySelectorAll("button, [tabindex='0']")];
      const first = controls[0], last = controls[controls.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
    dialog.showModal();
    reset();
    viewport.focus();
  }

  window.AskRich = { prose, diagram };
})();
