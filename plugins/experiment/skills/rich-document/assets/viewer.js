// Renderer-owned reading controls. No network calls, timers, or agent actions.
(() => {
  "use strict";
  const button = (label, action) => {
    const element = document.createElement("button");
    element.type = "button";
    element.textContent = label;
    element.addEventListener("click", action);
    return element;
  };

  function enlarge(original, opener) {
    const dialog = document.createElement("dialog");
    dialog.className = "rd-dialog";
    dialog.setAttribute("aria-label", "Enlarged diagram");
    const toolbar = document.createElement("div");
    toolbar.className = "rd-toolbar";
    const title = document.createElement("h2");
    title.textContent = "Diagram";
    toolbar.append(title);
    const viewport = document.createElement("div");
    viewport.className = "rd-viewport";
    viewport.tabIndex = 0;
    viewport.setAttribute("aria-label", "Diagram canvas. Arrow keys scroll; plus and minus zoom; zero resets.");
    // Move the existing SVG so scoped Mermaid styles and marker IDs remain unique.
    const svg = original;
    const previous = Object.fromEntries(["style", "width", "height", "aria-label"].map(name => [name, svg.getAttribute(name)]));
    svg.setAttribute("aria-label", "Enlarged diagram");
    const box = original.viewBox.baseVal;
    const naturalWidth = box.width || 900;
    const naturalHeight = box.height || 500;
    let zoom = 1;
    const status = document.createElement("output");
    status.setAttribute("aria-live", "polite");
    const resize = (value) => {
      zoom = Math.min(4, Math.max(.25, value));
      svg.style.width = `${naturalWidth * zoom}px`;
      svg.style.height = `${naturalHeight * zoom}px`;
      svg.setAttribute("width", String(naturalWidth * zoom));
      svg.setAttribute("height", String(naturalHeight * zoom));
      status.textContent = `${Math.round(zoom * 100)}%`;
    };
    const reset = () => { resize(Math.min(1, (viewport.clientWidth - 24) / naturalWidth)); viewport.scrollTo(0, 0); };
    toolbar.append(button("− Zoom out", () => resize(zoom / 1.25)),
      button("+ Zoom in", () => resize(zoom * 1.25)), button("Reset", reset), status,
      button("Close", () => dialog.close()));
    viewport.append(svg);
    dialog.append(toolbar, viewport);
    document.body.append(dialog);
    dialog.addEventListener("close", () => {
      opener.before(svg);
      for (const [name, value] of Object.entries(previous)) {
        if (value === null) svg.removeAttribute(name); else svg.setAttribute(name, value);
      }
      dialog.remove();
      opener.focus();
    }, {once:true});
    viewport.addEventListener("keydown", event => {
      if (["+", "=", "-", "0"].includes(event.key)) {
        event.preventDefault();
        if (event.key === "0") reset(); else resize(event.key === "-" ? zoom / 1.25 : zoom * 1.25);
      }
    });
    let drag = null;
    viewport.addEventListener("pointerdown", event => {
      if (event.pointerType !== "mouse" || event.button !== 0) return;
      drag = {x:event.clientX, y:event.clientY, left:viewport.scrollLeft, top:viewport.scrollTop};
      viewport.setPointerCapture(event.pointerId);
    });
    viewport.addEventListener("pointermove", event => {
      if (drag) viewport.scrollTo(drag.left + drag.x - event.clientX, drag.top + drag.y - event.clientY);
    });
    viewport.addEventListener("pointerup", () => { drag = null; });
    viewport.addEventListener("pointercancel", () => { drag = null; });
    dialog.addEventListener("keydown", event => {
      if (event.key !== "Tab") return;
      const controls = [...dialog.querySelectorAll("button, [tabindex='0']")];
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    });
    dialog.showModal();
    reset();
    viewport.focus();
  }

  function attach() {
    document.querySelectorAll('svg[id^="mermaid-"]').forEach(svg => {
      if (svg.closest(".rd-diagram, .rd-dialog")) return;
      const wrapper = document.createElement("div");
      wrapper.className = "rd-diagram";
      svg.before(wrapper);
      wrapper.append(svg);
      const control = button("Enlarge diagram", () => enlarge(svg, control));
      wrapper.append(control);
    });
  }
  function init() {
    attach();
    // Mermaid rendering is asynchronous and can occur when a hidden tab opens.
    new MutationObserver(attach).observe(document.querySelector("main") || document.body, {childList:true, subtree:true});
    document.querySelectorAll(".panel-tabset").forEach(tabset => {
      tabset.addEventListener("shown.bs.tab", attach);
    });
    // Quarto emits clickable disclosure headers as divs; expose keyboard semantics.
    document.querySelectorAll('.callout-header[data-bs-toggle="collapse"]').forEach(header => {
      header.setAttribute("role", "button");
      header.tabIndex = 0;
      header.setAttribute("aria-label", header.querySelector(".callout-title-container")?.textContent.trim() || "Toggle callout");
      header.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault(); header.click();
        }
      });
    });
    const toggle = document.querySelector(".quarto-color-scheme-toggle");
    if (toggle) toggle.setAttribute("aria-label", "Toggle light and dark theme");
    // Surface a runtime diagram failure together with its retained source.
    document.querySelectorAll("pre.mermaid").forEach(pre => {
      const source = pre.textContent;
      pre.dataset.rdSource = source;
    });
    window.addEventListener("unhandledrejection", event => {
      if (!String(event.reason).match(/mermaid|parse error|diagram/i)) return;
      const panel = document.createElement("details");
      panel.className = "rd-error";
      const summary = document.createElement("summary");
      summary.textContent = "A diagram could not be displayed. Show details and source.";
      const error = document.createElement("pre");
      error.textContent = String(event.reason);
      panel.append(summary, error);
      document.querySelectorAll("[data-rd-source]").forEach(node => {
        const code = document.createElement("pre"); code.textContent = node.dataset.rdSource; panel.append(code);
      });
      (document.querySelector("main") || document.body).append(panel);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
