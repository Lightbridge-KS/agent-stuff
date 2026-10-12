/* ask-form reader preferences belong to the reader, never to the spec.
   Loaded in <head> so <html data-theme data-layout data-side> is set before first paint.
     AskPrefs.get(key)          "layout" → stack|split · "side" → right|left (where the explanation
                                sits in split) · "theme" → system|light|dark
     AskPrefs.set(key, value)   persists and re-applies; fires `askprefs:change` on document,
                              detail {theme, layout, chosen}: which effective value changed,
                              and whether the reader changed a stored choice
     AskPrefs.effectiveTheme()  light|dark after resolving "system"
     AskPrefs.width()           current layout's {key, value, default, min, max, step}
   Stored as host-only cookies: every run binds a new random port and localStorage is per port,
   while cookies ignore the port, so a choice survives into the next form. Validated preferences only. */
(() => {
  "use strict";

  const CHOICES = { layout: ["stack", "split"], side: ["right", "left"], theme: ["system", "light", "dark"] };
  const WIDTHS = {
    width_stack: { default: 1040, min: 720, max: 1600, step: 40 },
    width_split: { default: 1280, min: 960, max: 1800, step: 40 },
  };
  const MAX_AGE = 60 * 60 * 24 * 365;
  const system = matchMedia("(prefers-color-scheme: dark)");

  const valid = (key, value) => {
    const limits = WIDTHS[key];
    if (!limits) return CHOICES[key]?.includes(value) || false;
    return /^\d+$/.test(String(value)) && Number(value) >= limits.min && Number(value) <= limits.max
      && (Number(value) - limits.min) % limits.step === 0;
  };

  const get = (key) => {
    const m = document.cookie.match(new RegExp(`(?:^|;\\s*)askform_${key}=([^;]*)`));
    let v;
    try { v = m && decodeURIComponent(m[1]); } catch { /* Invalid cookies use the default. */ }
    if (WIDTHS[key]) return valid(key, v) ? Number(v) : WIDTHS[key].default;
    return valid(key, v) ? v : CHOICES[key]?.[0];
  };

  const width = () => {
    const key = `width_${get("layout")}`;
    return { key, value: get(key), ...WIDTHS[key] };
  };

  const effectiveTheme = () => {
    const t = get("theme");
    return t === "system" ? (system.matches ? "dark" : "light") : t;
  };

  // `chosen`: the reader changed a stored choice, even if the effective value stayed the same
  // (Dark picked while the OS is already dark) — the Settings radios still need to follow.
  const apply = (chosen = false) => {
    const root = document.documentElement;
    const theme = effectiveTheme(), layout = get("layout"), side = get("side");
    const detail = { theme: root.dataset.theme !== theme, layout: root.dataset.layout !== layout || root.dataset.side !== side, chosen };
    root.dataset.theme = theme;
    root.dataset.layout = layout;
    root.dataset.side = side;
    root.style.setProperty("--width-stack", `${get("width_stack")}px`);
    root.style.setProperty("--width-split", `${get("width_split")}px`);
    if (detail.theme || detail.layout || chosen) document.dispatchEvent(new CustomEvent("askprefs:change", { detail }));
  };

  const set = (key, value) => {
    if (!valid(key, value)) return;
    document.cookie = `askform_${key}=${value}; Path=/; Max-Age=${MAX_AGE}; SameSite=Strict`;
    apply(true);
  };

  system.addEventListener("change", () => apply());
  apply();
  window.AskPrefs = { get, set, effectiveTheme, width };
})();
