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

  function diagramError(wrapper, source, reason) {
    wrapper.dataset.rdState = "failed";
    const panel = document.createElement("details");
    panel.className = "rd-error";
    const summary = document.createElement("summary");
    summary.textContent = "This diagram could not be displayed. Show details and source.";
    const error = document.createElement("pre");
    error.textContent = String(reason).slice(0, 2000);
    const code = document.createElement("pre");
    code.textContent = source;
    panel.append(summary, error, code);
    wrapper.replaceChildren(panel);
  }

  async function renderDiagrams() {
    const diagrams = [...document.querySelectorAll('.rd-diagram[data-rd-state="pending"]')];
    if (!diagrams.length) return;
    // Layout must be measurable even for panels the reader never selects.
    // A single queue also avoids Mermaid's shared-state races.
    await document.fonts.ready;
    const stage = document.createElement("div");
    stage.className = "rd-diagram rd-render-stage";
    stage.setAttribute("aria-hidden", "true");
    stage.inert = true;
    document.body.append(stage);
    try {
      let initializationError;
      try {
        mermaid.initialize({startOnLoad:false, securityLevel:"strict",
          themeCSS:JSON.parse(document.getElementById("rd-mermaid-theme").textContent),
          flowchart:{subGraphTitleMargin:{top:4, bottom:24}},
          suppressErrorRendering:true, fontFamily:"system-ui, sans-serif"});
      } catch (error) { initializationError = error; }
      for (const [index, wrapper] of diagrams.entries()) {
        const source = wrapper.querySelector(".rd-mermaid-source").textContent;
        try {
          if (initializationError) throw initializationError;
          let ancestor = wrapper;
          while (ancestor && ancestor.getBoundingClientRect().width === 0) ancestor = ancestor.parentElement;
          stage.style.width = `${Math.max(240, ancestor?.getBoundingClientRect().width || 800)}px`;
          const {svg: output} = await mermaid.render(`rd-mermaid-${index + 1}`, source, stage);
          // Mermaid has strictly sanitized this SVG. Author HTML stays forbidden.
          stage.innerHTML = output;
          const svg = stage.querySelector("svg");
          const box = svg?.viewBox.baseVal;
          if (!box || ![box.x, box.y, box.width, box.height].every(Number.isFinite)
              || box.width <= 0 || box.height <= 0) throw new Error("Diagram layout has invalid dimensions.");
          svg.classList.add("mermaid-js");
          svg.style.width = "100%";
          svg.style.maxWidth = `${box.width}px`;
          svg.style.height = "auto";
          // The viewer is the vendored diagram-zoom core (assets/vendor/diagram-zoom.js).
          const control = button("Enlarge diagram", () => window.DiagramZoom.enlarge(svg, {opener: control}));
          wrapper.replaceChildren(svg, control);
          wrapper.dataset.rdState = "rendered";
        } catch (error) {
          diagramError(wrapper, source, error);
        } finally {
          stage.replaceChildren();
        }
      }
    } finally {
      stage.remove();
    }
  }

  function init() {
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
    void renderDiagrams().catch(error => {
      document.querySelectorAll('.rd-diagram[data-rd-state="pending"]').forEach(wrapper => {
        diagramError(wrapper, wrapper.querySelector(".rd-mermaid-source").textContent, error);
      });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
