/* ask-form reader preferences: layout and theme belong to the reader, never to the spec.
   Loaded in <head> so <html data-theme data-layout data-side> is set before first paint.
     AskPrefs.get(key)          "layout" → stack|split · "side" → right|left (where the explanation
                                sits in split) · "theme" → system|light|dark
     AskPrefs.set(key, value)   persists and re-applies; fires `askprefs:change` on document,
                              detail {theme, layout, chosen}: which effective value changed,
                              and whether the reader changed a stored choice
     AskPrefs.effectiveTheme()  light|dark after resolving "system"
   Stored as host-only cookies: every run binds a new random port and localStorage is per port,
   while cookies ignore the port, so a choice survives into the next form. Enum values only. */
(() => {
  "use strict";

  const CHOICES = { layout: ["stack", "split"], side: ["right", "left"], theme: ["system", "light", "dark"] };
  const MAX_AGE = 60 * 60 * 24 * 365;
  const system = matchMedia("(prefers-color-scheme: dark)");

  const get = (key) => {
    const m = document.cookie.match(new RegExp(`(?:^|;\\s*)askform_${key}=([^;]*)`));
    const v = m && decodeURIComponent(m[1]);
    return CHOICES[key].includes(v) ? v : CHOICES[key][0];
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
    if (detail.theme || detail.layout || chosen) document.dispatchEvent(new CustomEvent("askprefs:change", { detail }));
  };

  const set = (key, value) => {
    if (!CHOICES[key]?.includes(value)) return;
    document.cookie = `askform_${key}=${value}; Path=/; Max-Age=${MAX_AGE}; SameSite=Strict`;
    apply(true);
  };

  system.addEventListener("change", () => apply());
  apply();
  window.AskPrefs = { get, set, effectiveTheme };
})();
