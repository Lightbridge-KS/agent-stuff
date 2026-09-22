/* ask-form renderer: a fixed catalog of ten element types, one glass card each, in spec order.
   Agent-supplied strings are inserted as text, or as sanitized rich markdown via rich.js. */
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

  // Rich prose (sanitized GFM, diagrams, code, callouts) lives in rich.js.
  const markdown = (src) => window.AskRich.prose(src);

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

  // Options that carry `detail` get a Compare panel above the choices. It is for reading only:
  // choosing an option shows its detail, switching tabs never chooses.
  const withCompare = (q, group, body) => {
    const detailed = q.options.filter((o) => o.detail);
    if (!detailed.length) return body;
    const compare = window.AskRich.tabs(
      detailed.map((o) => ({ label: o.label, badge: o.recommended ? "Recommended" : null, node: markdown(o.detail) })),
      { columns: detailed.length === 2 });
    const values = detailed.map((o) => o.value);
    group.addEventListener("change", (e) => {
      const i = values.indexOf(e.target.value);
      if (i >= 0 && e.target.checked) compare._select(i);
    });
    return el("div", {}, el("div", { class: "compare" }, el("div", { class: "compare-label", text: "Compare" }), compare), body);
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
    return withCompare(q, group, group);
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
    return withCompare(q, group, el("div", {}, group, hint));
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
        item.detail ? el("details", { class: "item-detail" }, el("summary", { text: "Detail" }), markdown(item.detail)) : null,
        seg, withComment ? comment : null,
      ));
    }
    return el("div", {}, wrap, hint);
  };

  let assetIndex = 0;
  const renderContext = (q) => {
    const card = el("section", { class: "card context", "aria-label": q.label || "context" });
    let body;
    if (q.format === "markdown") body = markdown(q.content);
    else if (q.format === "image") {
      const src = /^https?:\/\//.test(q.src) ? q.src : `/asset/${assetIndex++}?t=${encodeURIComponent(token)}`;
      body = el("img", { src, alt: q.label || "image" });
    } else if (q.format === "mermaid") body = window.AskRich.diagram(q.content);
    else if (q.format === "tabs") body = window.AskRich.tabs(q.panels.map((p) => ({ label: p.label, node: markdown(p.content) })));
    else if (q.format === "diff") body = window.AskRich.diff(q.content);
    if (q.collapsed) card.append(el("details", { class: "context-fold" }, el("summary", { text: q.label || "Background" }), body));
    else card.append(q.label ? el("div", { class: "q-help", text: q.label }) : null, body);
    return card;
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

  // Quote into note: selecting text in any rendered prose offers a Quote button that appends the
  // selection as a `>` quote to the note of the card holding it, else of the next question, else to
  // the form Comments. Pushback can then point at the exact sentence; it travels in meta.notes.
  const quoteTarget = (anchor) => {
    const blocks = [...document.querySelectorAll(".card .note-block")];
    const holder = blocks.find((b) => b.closest(".card").contains(anchor));
    const next = holder || blocks.find((b) => b.compareDocumentPosition(anchor) & Node.DOCUMENT_POSITION_PRECEDING);
    if (next) return { area: next.querySelector("textarea"), open: () => { if (next.querySelector("textarea").hidden) next._open(false); } };
    return { area: $(".comments textarea"), open: () => {} };
  };

  const quoteButton = () => {
    const btn = el("button", { type: "button", class: "quote-btn", text: "Quote", hidden: true, "aria-label": "Quote the selection into a note" });
    let picked = null;
    const hide = () => { btn.hidden = true; picked = null; };
    document.addEventListener("selectionchange", () => {
      const sel = getSelection();
      const anchor = sel.rangeCount && !sel.isCollapsed ? sel.getRangeAt(0).commonAncestorContainer : null;
      const prose = anchor && (anchor.nodeType === Node.ELEMENT_NODE ? anchor : anchor.parentElement).closest(".prose");
      const text = sel.toString().trim();
      if (!prose || !text || finished) return hide();
      const r = sel.getRangeAt(0).getBoundingClientRect();
      picked = { text, anchor: prose };
      btn.style.left = `${Math.max(8, Math.min(r.right + scrollX - 30, document.documentElement.clientWidth - 90))}px`;
      btn.style.top = `${r.bottom + scrollY + 6}px`;
      btn.hidden = false;
    });
    btn.addEventListener("mousedown", (e) => e.preventDefault());  // keep the selection alive
    btn.addEventListener("click", () => {
      if (!picked) return;
      const { area, open } = quoteTarget(picked.anchor);
      const quote = picked.text.split(/\r?\n/).map((l) => `> ${l}`.trimEnd()).join("\n");
      open();
      area.value = `${area.value.trim() ? `${area.value.trimEnd()}\n\n` : ""}${quote}\n\n`;
      area.dispatchEvent(new Event("input", { bubbles: true }));
      area.focus();
      area.setSelectionRange(area.value.length, area.value.length);
      getSelection().removeAllRanges();
      hide();
    });
    return btn;
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

  // ── reader settings ────────────────────────────────────────────────────────
  // Layout and theme are the reader's (prefs.js persists them). The spec's `layout: "split"` is
  // only a hint: a dot on the Settings button and a label on the Split option; it never applies.

  const settingsPanel = () => {
    const hasContext = spec.questions.some((q) => q.type === "context");
    const hinted = hasContext && spec.layout === "split";
    const button = $("#settings"), panel = $("#settings-panel");
    const group = (key, legend, choices) => el("fieldset", { class: "settings-group" },
      el("legend", { text: legend }),
      ...choices.map(([value, label, extra]) => el("label", { class: "settings-choice" },
        el("input", { type: "radio", name: `pref-${key}`, value, checked: window.AskPrefs.get(key) === value,
          onchange: () => window.AskPrefs.set(key, value) }),
        el("span", {}, el("span", { text: label }), extra || null))));
    panel.replaceChildren(
      el("h2", { class: "settings-title", text: "Settings" }),
      hasContext ? group("layout", "Layout", [
        ["stack", "One column"],
        ["split", "Split: context beside questions", hinted ? el("span", { class: "rec", text: "Suggested for this form" }) : null],
      ]) : null,
      hasContext ? el("p", { class: "hint", text: "Split applies in windows at least 1100 px wide." }) : null,
      group("theme", "Theme", [["system", "System"], ["light", "Light"], ["dark", "Dark"]]),
      el("p", { class: "hint", text: "Remembered for your next forms." }),
    );
    const sync = () => {
      button.classList.toggle("hinted", hinted && window.AskPrefs.get("layout") !== "split");
      for (const input of panel.querySelectorAll("input")) input.checked = window.AskPrefs.get(input.name.slice(5)) === input.value;
    };
    document.addEventListener("askprefs:change", sync);
    sync();
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
  // A run of context panes and the questions after it form one segment. In the reader's Split
  // layout (prefs.js → data-layout) the two sit side by side on wide screens; otherwise they stack.
  let segment = null;
  const newSegment = () => {
    const aside = el("div", { class: "seg-aside" }), main = el("div", { class: "seg-main" });
    list.append(el("div", { class: "segment" }, aside, main));
    return { aside, main };
  };
  for (const q of spec.questions) {
    if (q.type === "section") { list.append(el("h2", { class: "section", text: q.label })); segment = null; }
    else if (q.type === "context") {
      if (!segment || segment.main.children.length) segment = newSegment();
      segment.aside.append(renderContext(q));
    } else (segment ??= newSegment()).main.append(renderQuestion(q));
  }
  newSegment().main.append(commentsCard());
  settingsPanel();
  document.body.append(quoteButton());
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
