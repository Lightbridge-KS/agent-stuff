#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12"]
# ///
"""Deterministic CLI over Apple Keynote (JXA via osascript) — the shell an agent drives.

Verbs (every one prints ONE JSON object on stdout):

    status                       Keynote running? version, open documents
    themes                       theme names available for `build --theme`
    layouts   DECK               slide-layout names of a deck (theme-dependent — never guess)
    outline   DECK [--slide N]   deck -> JSON: per slide layout, title, body, notes, texts, counts
    set-text  DECK --slide N     edit title / body / notes of one slide, save
    add-slide DECK --layout L    append a slide (title, body, notes, image), save
    build     SPEC.md --out X.key   Markdown -> deck (from --theme or --template), optional --pdf
    export    DECK --to X.pdf    export as pdf | pptx | html (format from the extension)

Slides are 1-based, as Keynote numbers them. A deck already open in Keynote is used in
place and left open; a deck this tool opens is closed again unless --keep-open.

Exit codes: 0 ok · 2 bad request (checked before touching Keynote) · 3 Keynote/Apple
Event error · 4 Apple Events blocked (sandbox or Automation permission) — see the
SKILL.md sandbox contract.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Any, Optional

import typer

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help=__doc__,
)

EXIT_REQUEST = 2
EXIT_KEYNOTE = 3
EXIT_BLOCKED = 4

# Apple Event error numbers that mean "you are not allowed to talk to Keynote".
BLOCKED_CODES = {-10004, -1743, -600}

EXPORT_FORMATS = {
    ".pdf": "PDF",
    ".pptx": "Microsoft PowerPoint",
    ".html": "HTML",
}

# ---------------------------------------------------------------------------
# The JXA program. One string, dispatched by verb, always returns JSON.
# ---------------------------------------------------------------------------
JXA = r"""
function run(argv) {
  const req = JSON.parse(argv[0]);
  const a = req.args || {};
  const K = Application("Keynote");
  try {
    return JSON.stringify(Object.assign({ ok: true }, VERBS[req.verb](K, a)));
  } catch (e) {
    return JSON.stringify({ ok: false, error: String(e.message || e), code: e.errorNumber || null });
  }
}

// ---- helpers --------------------------------------------------------------
function docPath(d) { try { return String(d.file()); } catch (e) { return null; } }

// Reuse a deck already open in Keynote; otherwise open it and remember to close it.
function openDeck(K, path) {
  for (let i = 0; i < K.documents.length; i++) {
    if (docPath(K.documents[i]) === path) return { doc: K.documents[i], opened: false };
  }
  return { doc: K.open(Path(path)), opened: true };
}

function finish(doc, opened, keepOpen) {
  if (opened && !keepOpen) doc.close({ saving: "no" });
}

function layoutNames(doc) { return doc.slideLayouts.name(); }

// Exact name, else case-insensitive substring, else a teaching error.
function layoutByName(doc, name) {
  const names = layoutNames(doc);
  let hit = names.indexOf(name);
  if (hit < 0) hit = names.findIndex(n => n.toLowerCase().includes(name.toLowerCase()));
  if (hit < 0) throw new Error("layout '" + name + "' not in this deck; available: " + names.join(" | "));
  return doc.slideLayouts[hit];
}

function safeText(f) { try { const v = f(); return typeof v === "string" ? v : ""; } catch (e) { return ""; } }

function slideInfo(s, n) {
  const texts = [];
  try {
    s.textItems.objectText().forEach(t => { if (t && t.trim() && texts.indexOf(t) < 0) texts.push(t); });
  } catch (e) {}
  return {
    n: n,
    layout: safeText(() => s.baseLayout.name()),
    skipped: s.skipped(),
    titleShowing: s.titleShowing(),
    bodyShowing: s.bodyShowing(),
    title: safeText(() => s.defaultTitleItem.objectText()),
    body: safeText(() => s.defaultBodyItem.objectText()),
    notes: safeText(() => s.presenterNotes()),
    texts: texts,
    counts: {
      images: s.images.length, tables: s.tables.length, charts: s.charts.length,
      shapes: s.shapes.length, lines: s.lines.length, groups: s.groups.length
    }
  };
}

function slideAt(doc, n) {
  if (n < 1 || n > doc.slides.length) throw new Error("slide " + n + " out of range 1.." + doc.slides.length);
  return doc.slides[n - 1];
}

function applyContent(K, doc, slide, c) {
  if (c.title !== undefined && c.title !== null) slide.defaultTitleItem.objectText = c.title;
  if (c.body !== undefined && c.body !== null) slide.defaultBodyItem.objectText = c.body;
  if (c.notes !== undefined && c.notes !== null) slide.presenterNotes = c.notes;
  if (c.image) {
    // 80% of the slide width, below the title band; then cap the height so it stays on
    // the slide (setting width or height alone keeps the aspect ratio).
    const w = doc.width(), h = doc.height();
    const y = Math.round(h * (c.title ? 0.28 : 0.08));
    slide.images.push(K.Image({ file: Path(c.image), position: { x: Math.round(w * 0.1), y: y }, width: Math.round(w * 0.8) }));
    const img = slide.images[slide.images.length - 1];
    const maxH = Math.round(h * 0.92) - y;
    if (img.height() > maxH) {
      img.height = maxH;
      img.position = { x: Math.round((w - img.width()) / 2), y: y };
    }
  }
}

function appendSlide(K, doc, c) {
  const s = K.Slide({ baseLayout: layoutByName(doc, c.layout) });
  doc.slides.push(s);
  const slide = doc.slides[doc.slides.length - 1];
  applyContent(K, doc, slide, c);
  return doc.slides.length;
}

// Always an in-place save: a "save as" is done by the Python side copying the file
// first, because Keynote's `save in` leaves the document bound to the original file.
function saveDeck(doc) {
  doc.save();
  return docPath(doc);
}

// ---- verbs ----------------------------------------------------------------
const VERBS = {
  status: (K) => {
    const running = K.running();
    const out = { running: running, version: null, documents: [] };
    if (!running) return out;
    out.version = K.version();
    for (let i = 0; i < K.documents.length; i++) {
      out.documents.push({ name: K.documents[i].name(), file: docPath(K.documents[i]) });
    }
    return out;
  },

  themes: (K) => ({ themes: K.themes.name() }),

  layouts: (K, a) => {
    const { doc, opened } = openDeck(K, a.deck);
    const out = { deck: a.deck, theme: doc.documentTheme.name(), width: doc.width(), height: doc.height(), layouts: layoutNames(doc) };
    finish(doc, opened, a.keepOpen);
    return out;
  },

  outline: (K, a) => {
    const { doc, opened } = openDeck(K, a.deck);
    const out = { deck: a.deck, name: doc.name(), theme: doc.documentTheme.name(), width: doc.width(), height: doc.height(), slideCount: doc.slides.length, slides: [] };
    const from = a.slide ? a.slide : 1, to = a.slide ? a.slide : doc.slides.length;
    if (a.slide) slideAt(doc, a.slide);
    for (let n = from; n <= to; n++) out.slides.push(slideInfo(doc.slides[n - 1], n));
    finish(doc, opened, a.keepOpen);
    return out;
  },

  "set-text": (K, a) => {
    const { doc, opened } = openDeck(K, a.deck);
    const slide = slideAt(doc, a.slide);
    applyContent(K, doc, slide, a);
    const saved = saveDeck(doc);
    const out = { saved: saved, slide: slideInfo(slide, a.slide) };
    finish(doc, opened, a.keepOpen);
    return out;
  },

  "add-slide": (K, a) => {
    const { doc, opened } = openDeck(K, a.deck);
    const n = appendSlide(K, doc, a);
    const saved = saveDeck(doc);
    const out = { saved: saved, slideCount: n, slide: slideInfo(doc.slides[n - 1], n) };
    finish(doc, opened, a.keepOpen);
    return out;
  },

  // a.out already exists on disk: either a copy of the template (edited in place, its
  // own slides removed) or absent, in which case a theme-born deck is saved there.
  build: (K, a) => {
    let doc, template = 0;
    if (a.template) {
      doc = K.open(Path(a.out));
      template = doc.slides.length;
    } else {
      doc = K.Document({ documentTheme: K.themes[a.theme], width: a.width, height: a.height });
      K.documents.push(doc);  // the specifier stays usable after push
      // A theme-born deck starts with one slide; the first spec slide takes it over.
    }
    try {
      const names = layoutNames(doc);
      let first = true;
      a.slides.forEach(c => {
        if (!template && first) {
          first = false;
          const s = doc.slides[0];
          s.baseLayout = layoutByName(doc, c.layout);
          applyContent(K, doc, s, c);
        } else {
          appendSlide(K, doc, c);
        }
      });
      for (let i = 0; i < template; i++) doc.slides[0].delete();
      if (template) doc.save(); else doc.save({ in: Path(a.out) });
      const out = { saved: a.out, slideCount: doc.slides.length, theme: doc.documentTheme.name(), layouts: names };
      if (a.pdf) { doc.export({ to: Path(a.pdf), as: "PDF" }); out.pdf = a.pdf; }
      if (!a.keepOpen) doc.close({ saving: "no" });
      return out;
    } catch (e) {
      try { doc.close({ saving: "no" }); } catch (x) {}
      throw e;
    }
  },

  export: (K, a) => {
    const { doc, opened } = openDeck(K, a.deck);
    const props = {};
    if (a.allStages) props.allStages = true;
    if (a.skippedSlides) props.skippedSlides = true;
    doc.export({ to: Path(a.to), as: a.format, withProperties: props });
    finish(doc, opened, a.keepOpen);
    return { exported: a.to, format: a.format };
  }
};
"""


# ---------------------------------------------------------------------------
# Runner + output
# ---------------------------------------------------------------------------
def _emit(payload: dict[str, Any], code: int = 0) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False))
    raise typer.Exit(code)


def _fail(message: str, code: int, **extra: Any) -> None:
    _emit({"ok": False, "error": message, **extra}, code)


def _run(verb: str, args: dict[str, Any]) -> None:
    req = json.dumps({"verb": verb, "args": args})
    proc = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", JXA, "--", req],
        capture_output=True,
        text=True,
    )
    raw = proc.stdout.strip()
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        stderr = proc.stderr.strip()
        if "-10004" in stderr or "-1743" in stderr:
            _fail("Apple Events blocked — run outside the Bash sandbox / grant Automation for the runner app",
                  EXIT_BLOCKED, stderr=stderr)
        _fail("osascript returned no JSON", EXIT_KEYNOTE, stdout=raw, stderr=stderr, rc=proc.returncode)
    if result.get("ok"):
        _emit(result)
    code = result.get("code")
    if code in BLOCKED_CODES:
        result["hint"] = "Apple Events blocked — run outside the Bash sandbox / grant Automation for the runner app"
        _emit(result, EXIT_BLOCKED)
    _emit(result, EXIT_KEYNOTE)


def _deck(path: Path) -> str:
    if not path.exists():
        _fail(f"deck not found: {path}", EXIT_REQUEST)
    if path.suffix.lower() != ".key":
        _fail(f"not a Keynote deck (.key): {path}", EXIT_REQUEST)
    return str(path.resolve())


def _outfile(path: Optional[Path], suffix: str) -> Optional[str]:
    if path is None:
        return None
    if path.suffix.lower() != suffix:
        _fail(f"--out must end in {suffix}: {path}", EXIT_REQUEST)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path.resolve())


def _copy_deck(src: str, dst: str) -> str:
    """Save-as, done on disk: copy the deck (a .key may be a file or a package dir)."""
    if Path(src) == Path(dst):
        _fail("--out must differ from the source deck", EXIT_REQUEST)
    if Path(dst).is_dir():
        shutil.rmtree(dst)
    if Path(src).is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)
    return dst


def _working_deck(deck: Path, out: Optional[Path]) -> str:
    """The deck a mutating verb edits in place: the original, or a fresh copy at --out."""
    src = _deck(deck)
    dst = _outfile(out, ".key")
    return _copy_deck(src, dst) if dst else src


# ---------------------------------------------------------------------------
# Markdown deck spec
# ---------------------------------------------------------------------------
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
LAYOUT_RE = re.compile(r"<!--\s*layout:\s*(.+?)\s*-->")


def parse_deck_markdown(text: str, base: Path, title_layout: str, bullets_layout: str) -> list[dict[str, Any]]:
    """Markdown -> slide specs.

    # Title             first H1 = title slide (title_layout); following paragraph = body
    ## Heading          new slide (bullets_layout)
    - item / paragraph  body lines
    ![alt](path)        image on the slide (path relative to the .md file)
    > notes             presenter notes
    <!-- layout: X -->  layout override for the current slide
    """
    slides: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = LAYOUT_RE.search(line)
        if m:
            if cur is not None:
                cur["layout"] = m.group(1)
            continue
        if line.startswith("# "):
            cur = {"layout": title_layout, "title": line[2:].strip(), "body": [], "notes": [], "image": None}
            slides.append(cur)
            continue
        if line.startswith("## "):
            cur = {"layout": bullets_layout, "title": line[3:].strip(), "body": [], "notes": [], "image": None}
            slides.append(cur)
            continue
        if cur is None:
            cur = {"layout": bullets_layout, "title": "", "body": [], "notes": [], "image": None}
            slides.append(cur)
        m = IMAGE_RE.search(line)
        if m:
            img = Path(m.group(1))
            cur["image"] = str((base / img).resolve() if not img.is_absolute() else img)
            continue
        if line.startswith(">"):
            cur["notes"].append(line.lstrip("> ").strip())
            continue
        if line.startswith(("- ", "* ")):
            cur["body"].append(line[2:].strip())
            continue
        cur["body"].append(line.strip())
    for s in slides:
        s["body"] = "\n".join(s["body"])
        s["notes"] = "\n".join(s["notes"])
        if s["image"] and not Path(s["image"]).exists():
            _fail(f"image not found: {s['image']}", EXIT_REQUEST)
    return slides


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
Deck = Annotated[Path, typer.Argument(help="Path to a .key deck")]
KeepOpen = Annotated[bool, typer.Option("--keep-open", help="Leave a deck this tool opened open in Keynote")]


@app.command()
def status() -> None:
    """Is Keynote running? Version and open documents (never launches Keynote)."""
    _run("status", {})


@app.command()
def themes() -> None:
    """Theme names available for `build --theme`."""
    _run("themes", {})


@app.command()
def layouts(deck: Deck, keep_open: KeepOpen = False) -> None:
    """Slide-layout names of a deck (theme-dependent — read before add-slide/build)."""
    _run("layouts", {"deck": _deck(deck), "keepOpen": keep_open})


@app.command()
def outline(
    deck: Deck,
    slide: Annotated[Optional[int], typer.Option("--slide", "-s", min=1, help="Only this slide (1-based)")] = None,
    keep_open: KeepOpen = False,
) -> None:
    """Deck -> JSON: per slide layout, title, body, notes, visible texts, item counts."""
    _run("outline", {"deck": _deck(deck), "slide": slide, "keepOpen": keep_open})


@app.command("set-text")
def set_text(
    deck: Deck,
    slide: Annotated[int, typer.Option("--slide", "-s", min=1, help="Slide number (1-based)")],
    title: Annotated[Optional[str], typer.Option(help="New title text")] = None,
    body: Annotated[Optional[str], typer.Option(help="New body text (\\n for new lines)")] = None,
    notes: Annotated[Optional[str], typer.Option(help="New presenter notes")] = None,
    out: Annotated[Optional[Path], typer.Option(help="Save-as here instead of in place")] = None,
    keep_open: KeepOpen = False,
) -> None:
    """Edit the title, body and/or notes of one slide, then save (in place, or to a copy at --out)."""
    if title is None and body is None and notes is None:
        _fail("nothing to set: pass --title, --body and/or --notes", EXIT_REQUEST)
    _run("set-text", {
        "deck": _working_deck(deck, out), "slide": slide, "title": title,
        "body": body.replace("\\n", "\n") if body else body,
        "notes": notes, "keepOpen": keep_open,
    })


@app.command("add-slide")
def add_slide(
    deck: Deck,
    layout: Annotated[str, typer.Option(help="Slide layout name (see `layouts`)")],
    title: Annotated[Optional[str], typer.Option()] = None,
    body: Annotated[Optional[str], typer.Option(help="Body text (\\n for new lines)")] = None,
    notes: Annotated[Optional[str], typer.Option()] = None,
    image: Annotated[Optional[Path], typer.Option(help="Image file to place on the slide")] = None,
    out: Annotated[Optional[Path], typer.Option(help="Save-as here instead of in place")] = None,
    keep_open: KeepOpen = False,
) -> None:
    """Append a slide with the given layout and content, then save (in place, or to a copy at --out)."""
    if image is not None and not image.exists():
        _fail(f"image not found: {image}", EXIT_REQUEST)
    _run("add-slide", {
        "deck": _working_deck(deck, out), "layout": layout, "title": title,
        "body": body.replace("\\n", "\n") if body else body, "notes": notes,
        "image": str(image.resolve()) if image else None,
        "keepOpen": keep_open,
    })


@app.command()
def build(
    spec: Annotated[Path, typer.Argument(help="Markdown deck spec (see --help for the grammar)")],
    out: Annotated[Path, typer.Option(help="Where to save the .key")],
    theme: Annotated[str, typer.Option(help="Keynote theme (see `themes`)")] = "White",
    template: Annotated[Optional[Path], typer.Option(help="Build inside a copy of this .key instead of a theme (its own slides are removed)")] = None,
    title_layout: Annotated[str, typer.Option(help="Layout for '# ' slides")] = "Title",
    bullets_layout: Annotated[str, typer.Option(help="Layout for '## ' slides")] = "Title & Bullets",
    width: Annotated[int, typer.Option(help="Deck width (theme builds only)")] = 1920,
    height: Annotated[int, typer.Option(help="Deck height (theme builds only)")] = 1080,
    pdf: Annotated[Optional[Path], typer.Option(help="Also export a PDF here")] = None,
    keep_open: KeepOpen = False,
) -> None:
    """Build a deck from a Markdown spec.

    \b
    # Deck title            title slide; next paragraph = subtitle/body
    ## Slide heading        new slide; '- item' and paragraphs = body lines
    ![alt](image.png)       image on the slide (path relative to the spec)
    > speaker notes         presenter notes
    <!-- layout: Blank -->  layout override for the current slide
    """
    if not spec.exists():
        _fail(f"spec not found: {spec}", EXIT_REQUEST)
    slides = parse_deck_markdown(spec.read_text(encoding="utf-8"), spec.parent, title_layout, bullets_layout)
    if not slides:
        _fail("spec has no slides (need at least one '# ' or '## ' heading)", EXIT_REQUEST)
    out_path = _outfile(out, ".key")
    if template:
        _copy_deck(_deck(template), out_path)  # build inside the copy; the template stays untouched
    _run("build", {
        "slides": slides, "out": out_path, "theme": theme, "template": bool(template),
        "width": width, "height": height,
        "pdf": _outfile(pdf, ".pdf"), "keepOpen": keep_open,
    })


@app.command()
def export(
    deck: Deck,
    to: Annotated[Path, typer.Option(help="Output file: .pdf, .pptx or .html")],
    all_stages: Annotated[bool, typer.Option("--all-stages", help="PDF: one page per build stage")] = False,
    skipped_slides: Annotated[bool, typer.Option("--skipped-slides", help="Include skipped slides")] = False,
    keep_open: KeepOpen = False,
) -> None:
    """Export a deck; the format follows the output extension."""
    fmt = EXPORT_FORMATS.get(to.suffix.lower())
    if fmt is None:
        _fail(f"unsupported export extension {to.suffix!r}; use one of {sorted(EXPORT_FORMATS)}", EXIT_REQUEST)
    to.parent.mkdir(parents=True, exist_ok=True)
    _run("export", {
        "deck": _deck(deck), "to": str(to.resolve()), "format": fmt,
        "allStages": all_stages, "skippedSlides": skipped_slides, "keepOpen": keep_open,
    })


if __name__ == "__main__":
    app()
