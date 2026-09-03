/* ask-form renderer: a fixed catalog of ten element types, one glass card each, in spec order.
   Agent-supplied strings are inserted as text, or as sanitized markdown (img forbidden). */
(() => {
  "use strict";

  const spec = JSON.parse(document.getElementById("spec").textContent);
  const token = new URLSearchParams(location.search).get("t") || "";
  const $ = (sel, root = document) => root.querySelector(sel);

  // answers: id -> value (only present when the question counts as answered)
  const answers = new Map();
  const other = new Set();
  const notes = new Map();     // id -> note text (optional, per question)
  let comments = "";           // optional, form-level
  const cards = new Map();   // id -> card element
  const elements = spec.questions.filter((e) => e.type !== "section" && e.type !== "context");
  const requiredIds = elements.filter((e) => e.required).map((e) => e.id);
  let finished = false;

  // ── helpers ────────────────────────────────────────────────────────────────

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

  const markdown = (src) => {
    const box = el("div", { class: "prose" });
    if (!src) return box;
    try {
      const html = window.marked.parse(src, { gfm: true, breaks: false });
      box.innerHTML = window.DOMPurify.sanitize(html, { FORBID_TAGS: ["img", "style", "form", "input"], FORBID_ATTR: ["style", "onerror", "onload"] });
      for (const a of box.querySelectorAll("a")) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
    } catch { box.textContent = src; }
    return box;
  };

  const setAnswer = (id, value) => {
    if (value === undefined) answers.delete(id); else answers.set(id, value);
    const card = cards.get(id);
    if (card) { card.classList.toggle("answered", value !== undefined); card.classList.remove("missing"); }
    refreshFooter();
  };

  // ── components: each returns a body node and wires setAnswer ──────────────

  const optionRow = (q, opt, type, onChange) => {
    const input = el("input", { type, name: q.id, value: opt.value, onchange: onChange });
    return el("label", { class: "option" },
      input,
      el("div", {}, el("div", { class: "opt-label", text: opt.label }, opt.recommended ? recBadge() : null), opt.description ? el("div", { class: "opt-desc", text: opt.description }) : null),
    );
  };

  const recBadge = (text = "Recommended") => el("span", { class: "rec", text });

  const otherRow = (q, type, onChange) => {
    const input = el("input", { type, name: q.id, value: "__other__", onchange: onChange });
    const text = el("input", { class: "control other-input", type: "text", placeholder: "Type your own answer", hidden: true, oninput: onChange });
    text.addEventListener("focus", () => { if (!input.checked) { input.checked = true; onChange(); } });
    const row = el("label", { class: "option" }, input, el("div", {}, el("div", { class: "opt-label", text: "Other" })), text);
    row._text = text; row._input = input;
    return row;
  };

  const renderSingle = (q) => {
    const group = el("fieldset", { class: "options", role: "radiogroup", "aria-label": q.label });
    let otherEl = null;
    const update = () => {
      const checked = group.querySelector("input:checked");
      if (otherEl) otherEl._text.hidden = !(otherEl._input.checked);
      if (!checked) return setAnswer(q.id, undefined);
      if (checked.value === "__other__") {
        const t = otherEl._text.value.trim();
        other.add(q.id);
        return setAnswer(q.id, t ? t : undefined);
      }
      other.delete(q.id);
      setAnswer(q.id, checked.value);
    };
    for (const opt of q.options) group.append(optionRow(q, opt, "radio", update));
    if (q.allow_other !== false) { otherEl = otherRow(q, "radio", update); group.append(otherEl); }
    return group;
  };

  const renderMulti = (q) => {
    const group = el("fieldset", { class: "options", "aria-label": q.label });
    const hint = el("p", { class: "hint" });
    const lo = q.min ?? 0, hi = q.max ?? Infinity;
    const bounds = [];
    if (q.min) bounds.push(`at least ${q.min}`);
    if (q.max) bounds.push(`at most ${q.max}`);
    hint.textContent = bounds.length ? `Choose ${bounds.join(", ")}.` : "";
    let otherEl = null;
    const update = () => {
      const picked = [...group.querySelectorAll("input:checked")].map((i) => i.value);
      const vals = picked.filter((v) => v !== "__other__");
      if (otherEl) otherEl._text.hidden = !otherEl._input.checked;
      if (picked.includes("__other__")) {
        const t = otherEl._text.value.trim();
        if (t) vals.push(t);
        other.add(q.id);
      } else other.delete(q.id);
      const ok = vals.length >= lo && vals.length <= hi && vals.length > 0;
      hint.classList.toggle("warn", picked.length > 0 && !ok);
      setAnswer(q.id, ok ? vals : undefined);
    };
    for (const opt of q.options) group.append(optionRow(q, opt, "checkbox", update));
    if (q.allow_other !== false) { otherEl = otherRow(q, "checkbox", update); group.append(otherEl); }
    return el("div", {}, group, hint);
  };

  const renderScale = (q) => {
    const value = el("div", { class: "scale-value unset", text: "—", "aria-live": "polite" });
    const range = el("input", { type: "range", min: q.min, max: q.max, step: q.step ?? 1, value: q.min, "aria-label": q.label });
    const labels = q.labels || {};
    const ends = el("div", { class: "scale-ends" },
      el("span", { text: labels[String(q.min)] ? `${q.min} ${labels[String(q.min)]}` : String(q.min) }),
      el("span", { text: labels[String(q.max)] ? `${labels[String(q.max)]} ${q.max}` : String(q.max) }),
    );
    const update = () => {
      const v = Number(range.value);
      const lbl = labels[String(v)];
      value.textContent = lbl ? `${v}  ${lbl}` : String(v);
      value.classList.remove("unset");
      setAnswer(q.id, v);
    };
    range.addEventListener("input", update);
    range.addEventListener("change", update);
    const recLine = q.recommended != null ? el("p", { class: "hint rec-line" }, recBadge(`Recommended: ${q.recommended}${labels[String(q.recommended)] ? ` ${labels[String(q.recommended)]}` : ""}`)) : null;
    return el("div", { class: "scale" }, value, range, ends, recLine, el("p", { class: "hint", text: "Drag the slider or use the arrow keys." }));
  };

  const renderNumber = (q) => {
    const input = el("input", { class: "control", type: "number", min: q.min, max: q.max, step: q.step ?? "any", placeholder: q.placeholder, "aria-label": q.label });
    const hint = el("p", { class: "hint" });
    input.addEventListener("input", () => {
      const raw = input.value.trim();
      if (raw === "") { hint.textContent = ""; return setAnswer(q.id, undefined); }
      const v = Number(raw);
      const ok = Number.isFinite(v) && (q.min == null || v >= q.min) && (q.max == null || v <= q.max);
      hint.textContent = ok ? "" : `Enter a number${q.min != null ? ` from ${q.min}` : ""}${q.max != null ? ` to ${q.max}` : ""}.`;
      hint.classList.toggle("warn", !ok);
      setAnswer(q.id, ok ? v : undefined);
    });
    const recLine = q.recommended != null ? el("p", { class: "hint rec-line" }, recBadge(`Recommended: ${q.recommended}${q.unit ? ` ${q.unit}` : ""}`)) : null;
    return el("div", {}, el("div", { class: "number-row" }, input, q.unit ? el("span", { class: "unit", text: q.unit }) : null), recLine, hint);
  };

  const renderText = (q, long) => {
    const input = long
      ? el("textarea", { class: "control", placeholder: q.placeholder, "aria-label": q.label, rows: 4 })
      : el("input", { class: "control", type: "text", placeholder: q.placeholder, maxlength: q.max_length, "aria-label": q.label });
    const hint = el("p", { class: "hint" });
    input.addEventListener("input", () => {
      const v = input.value;
      if (!long && q.max_length) hint.textContent = `${v.length} / ${q.max_length}`;
      if (long) { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight + 2, 480)}px`; }
      setAnswer(q.id, v.trim() ? v : undefined);
    });
    return el("div", {}, input, hint);
  };

  const renderRanking = (q) => {
    let order = q.options.map((o) => o.value);
    const byValue = Object.fromEntries(q.options.map((o) => [o.value, o]));
    const list = el("ol", { class: "rank", "aria-label": q.label });
    const confirm = el("button", { type: "button", class: "btn quiet rank-confirm", text: "Keep this order" });
    let touched = false;
    const commit = () => { touched = true; confirm.hidden = true; setAnswer(q.id, [...order]); };
    const draw = () => {
      list.replaceChildren();
      order.forEach((v, i) => {
        const o = byValue[v];
        const up = el("button", { type: "button", "aria-label": `Move ${o.label} up`, text: "▲", disabled: i === 0, onclick: () => { [order[i - 1], order[i]] = [order[i], order[i - 1]]; commit(); draw(); } });
        const down = el("button", { type: "button", "aria-label": `Move ${o.label} down`, text: "▼", disabled: i === order.length - 1, onclick: () => { [order[i + 1], order[i]] = [order[i], order[i + 1]]; commit(); draw(); } });
        list.append(el("li", { class: "rank-row" },
          el("span", { class: "pos", text: String(i + 1) }),
          el("div", {}, el("div", { class: "opt-label", text: o.label }), o.description ? el("div", { class: "opt-desc", text: o.description }) : null),
          el("div", { class: "moves" }, up, down),
        ));
      });
    };
    confirm.addEventListener("click", commit);
    draw();
    return el("div", {}, list, el("p", { class: "hint", text: "Move items with the arrows, or keep the order shown." }), touched ? null : confirm);
  };

  const renderMatrix = (q) => {
    const picks = {};
    const table = el("table", { class: "matrix" });
    table.append(el("thead", {}, el("tr", {}, el("th", { text: "" }), ...q.columns.map((c) => el("th", { text: c.label })))));
    const body = el("tbody");
    const hint = el("p", { class: "hint" });
    const update = () => {
      const n = Object.keys(picks).length;
      hint.textContent = n && n < q.rows.length ? `${n} of ${q.rows.length} rows answered` : "";
      setAnswer(q.id, n === q.rows.length ? { ...picks } : undefined);
    };
    for (const r of q.rows) {
      const tr = el("tr", {}, el("td", { text: r.label }));
      for (const c of q.columns) {
        const input = el("input", { type: "radio", name: `${q.id}:${r.value}`, value: c.value, "aria-label": `${r.label}: ${c.label}`, onchange: () => { picks[r.value] = c.value; update(); } });
        tr.append(el("td", {}, el("label", {}, input)));
      }
      body.append(tr);
    }
    table.append(body);
    return el("div", {}, el("div", { class: "matrix-wrap" }, table), hint);
  };

  const renderReview = (q) => {
    const decisions = q.decisions || ["approve", "revise", "reject"];
    const withComment = q.comment !== false;
    const state = {};
    const wrap = el("div", { class: "review" });
    const hint = el("p", { class: "hint" });
    const update = () => {
      const done = Object.keys(state).length;
      hint.textContent = done && done < q.items.length ? `${done} of ${q.items.length} decided` : "";
      const complete = done === q.items.length;
      setAnswer(q.id, complete ? Object.fromEntries(Object.entries(state).map(([k, v]) => [k, { decision: v.decision, comment: v.comment || "" }])) : undefined);
    };
    for (const item of q.items) {
      const seg = el("div", { class: "seg", role: "group", "aria-label": item.label });
      const comment = el("textarea", { class: "control", placeholder: "Add a comment (optional)", hidden: true, rows: 2, "aria-label": `Comment on ${item.label}` });
      comment.addEventListener("input", () => { if (state[item.id]) { state[item.id].comment = comment.value.trim(); update(); } });
      for (const d of decisions) {
        const b = el("button", { type: "button", text: d, "aria-pressed": "false", "data-tone": d, "data-rec": item.recommended === d ? "true" : undefined, title: item.recommended === d ? "Recommended" : undefined });
        b.addEventListener("click", () => {
          for (const x of seg.children) x.setAttribute("aria-pressed", String(x === b));
          state[item.id] = { decision: d, comment: comment.value.trim() };
          if (withComment) { comment.hidden = false; if (d !== decisions[0]) comment.focus(); }
          update();
        });
        seg.append(b);
      }
      wrap.append(el("div", { class: "review-item" },
        el("div", { class: "opt-label", text: item.label }),
        item.description ? el("div", { class: "opt-desc", text: item.description }) : null,
        seg, withComment ? comment : null,
      ));
    }
    return el("div", {}, wrap, hint);
  };

  let assetIndex = 0;
  const renderContext = (q) => {
    const card = el("section", { class: "card context", "aria-label": q.label || "context" });
    if (q.label) card.append(el("div", { class: "q-help", text: q.label }));
    if (q.format === "markdown") card.append(markdown(q.content));
    else if (q.format === "image") {
      const src = /^https?:\/\//.test(q.src) ? q.src : `/asset/${assetIndex++}?t=${encodeURIComponent(token)}`;
      card.append(el("img", { src, alt: q.label || "image" }));
    } else if (q.format === "mermaid") {
      const box = el("div", { class: "mermaid" });
      const fallback = () => { box.replaceChildren(el("pre", {}, el("code", { text: q.content }))); };
      card.append(box);
      loadMermaid().then(async (m) => {
        try {
          m.initialize({ startOnLoad: false, theme: matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "default", securityLevel: "strict" });
          const { svg } = await m.render(`m${Math.random().toString(36).slice(2)}`, q.content);
          box.innerHTML = window.DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true, svgFilters: true }, ADD_TAGS: ["foreignObject"] });
        } catch { fallback(); }
      }).catch(fallback);
    }
    return card;
  };

  let mermaidPromise = null;
  const loadMermaid = () => {
    if (window.mermaid) return Promise.resolve(window.mermaid);
    if (mermaidPromise) return mermaidPromise;
    mermaidPromise = new Promise((resolve, reject) => {
      const s = el("script", { src: "https://cdnjs.cloudflare.com/ajax/libs/mermaid/11.6.0/mermaid.min.js" });
      s.onload = () => (window.mermaid ? resolve(window.mermaid) : reject(new Error("mermaid missing")));
      s.onerror = () => reject(new Error("mermaid failed to load"));
      document.head.append(s);
    });
    return mermaidPromise;
  };

  const RENDERERS = {
    single_select: renderSingle,
    multi_select: renderMulti,
    scale: renderScale,
    number: renderNumber,
    short_text: (q) => renderText(q, false),
    long_text: (q) => renderText(q, true),
    ranking: renderRanking,
    matrix: renderMatrix,
    review: renderReview,
  };

  const renderQuestion = (q) => {
    const card = el("section", { class: "card", id: `q-${q.id}` });
    const label = el("h2", { class: "q-label", text: q.label }, q.required ? el("span", { class: "req", text: "required" }) : null);
    card.append(label);
    if (q.help) { const h = markdown(q.help); h.classList.add("q-help"); card.append(h); }
    if (q.recommendation) card.append(el("p", { class: "recommendation" }, el("span", { class: "rec-label", text: "Agent recommends" }), el("span", { text: q.recommendation })));
    card.append(el("div", { class: "q-body" }, RENDERERS[q.type](q)));
    card.append(noteBlock(q.id));
    cards.set(q.id, card);
    return card;
  };

  // Optional per-question note, collapsed behind a toggle; `n` opens it while the card has focus.
  const noteBlock = (id) => {
    const area = el("textarea", { class: "control note", placeholder: "Add a note for your agent", rows: 2, hidden: true, "aria-label": "Note" });
    const toggle = el("button", { type: "button", class: "note-toggle", "aria-expanded": "false" },
      el("span", { class: "chev", text: "›" }), el("span", { text: "Add a note" }), el("kbd", { text: "n" }));
    const open = (focus = true) => {
      const show = area.hidden;
      area.hidden = !show;
      toggle.setAttribute("aria-expanded", String(show));
      if (show && focus) area.focus();
    };
    toggle.addEventListener("click", () => open(true));
    area.addEventListener("input", () => {
      const v = area.value.trim();
      if (v) notes.set(id, v); else notes.delete(id);
      toggle.classList.toggle("has-note", Boolean(v));
      toggle.querySelector("span:nth-child(2)").textContent = v ? "Note" : "Add a note";
    });
    const block = el("div", { class: "note-block" }, toggle, area);
    block._open = open;
    return block;
  };

  // Form-level comments card, always last.
  const commentsCard = () => {
    const area = el("textarea", { class: "control", placeholder: "Anything else, about the form as a whole", rows: 3, "aria-label": "Comments" });
    area.addEventListener("input", () => { comments = area.value.trim(); });
    return el("section", { class: "card comments" },
      el("h2", { class: "q-label", text: "Comments" }),
      el("p", { class: "q-help", text: "Optional. Anything that does not fit a question above." }),
      el("div", { class: "q-body" }, area),
    );
  };

  // ── footer / submit ────────────────────────────────────────────────────────

  const footer = $("#footer"), progress = $("#progress"), fill = $("#fill"), submit = $("#submit"), cancel = $("#cancel");

  const missingRequired = () => requiredIds.filter((id) => !answers.has(id));

  const refreshFooter = () => {
    const total = elements.length, done = answers.size, missing = missingRequired().length;
    const parts = [];
    parts.push(el("strong", { text: `${done} of ${total}` }), " answered");
    if (missing) parts.push(`, ${missing} required left`);
    progress.replaceChildren(...parts);
    fill.style.width = total ? `${Math.round((done / total) * 100)}%` : "100%";
    submit.setAttribute("aria-disabled", String(missing > 0));
  };

  const showErrors = (list) => {
    $(".errors")?.remove();
    const box = el("div", { class: "errors", role: "alert" }, el("strong", { text: "The form was not accepted." }), el("ul", {}, ...list.map((m) => el("li", { text: m }))));
    $("#questions").prepend(box);
    box.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  const finish = (title, text, ok = false) => {
    finished = true;
    footer.hidden = true;
    $("#app").replaceChildren(el("section", { class: ok ? "card done ok" : "card done" }, el("h2", { text: title }), el("p", { text })));
  };

  const post = async (path, body) => {
    const r = await fetch(`${path}?t=${encodeURIComponent(token)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    let data = {};
    try { data = await r.json(); } catch { /* empty body */ }
    return { status: r.status, data };
  };

  const doSubmit = async () => {
    if (finished) return;
    const missing = missingRequired();
    if (missing.length) {
      const card = cards.get(missing[0]);
      card.classList.add("missing");
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      card.querySelector("input, textarea, button")?.focus({ preventScroll: true });
      return;
    }
    submit.disabled = true;
    try {
      const { status, data } = await post("/submit", { answers: Object.fromEntries(answers), other: [...other].filter((id) => answers.has(id)), notes: Object.fromEntries(notes), comments });
      if (status === 200) return finish("Answers sent", "You can close this tab. Your agent has them.", true);
      if (status === 409) return finish("Already finished", "This form was closed by another submission.");
      showErrors(data.errors || [data.error || `Server said ${status}.`]);
    } catch (e) {
      showErrors([`Could not reach the form server (${e.message}). It may have timed out; check the terminal.`]);
    } finally { submit.disabled = false; }
  };

  const doCancel = async () => {
    if (finished) return;
    try { await post("/cancel", {}); } catch { /* server gone */ }
    finish("Cancelled", "Nothing was sent. Tell your agent how you would rather answer.");
  };

  // ── boot ───────────────────────────────────────────────────────────────────

  document.title = spec.title;
  $("#title").textContent = spec.title;
  if (spec.intro) $("#intro").replaceChildren(markdown(spec.intro));
  const list = $("#questions");
  for (const q of spec.questions) {
    if (q.type === "section") list.append(el("h2", { class: "section", text: q.label }));
    else if (q.type === "context") list.append(renderContext(q));
    else list.append(renderQuestion(q));
  }
  list.append(commentsCard());
  document.addEventListener("keydown", (e) => {
    if (e.key !== "n" || e.metaKey || e.ctrlKey || e.altKey) return;
    const a = document.activeElement;
    if (a && (a.tagName === "TEXTAREA" || (a.tagName === "INPUT" && !["radio", "checkbox", "range"].includes(a.type)))) return;
    const card = a?.closest?.(".card");
    const block = card?.querySelector(".note-block");
    if (block) { e.preventDefault(); block._open(true); }
  });
  submit.textContent = spec.submit_label || "Send answers";
  submit.addEventListener("click", doSubmit);
  cancel.addEventListener("click", doCancel);
  document.addEventListener("keydown", (e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); doSubmit(); } });
  footer.hidden = false;
  refreshFooter();
})();
