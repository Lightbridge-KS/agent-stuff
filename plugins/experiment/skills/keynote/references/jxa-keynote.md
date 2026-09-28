# Keynote JXA — verified reference

Every snippet here ran on Keynote 14.5 / macOS 15.7 (2026-09-29). Ground truth is the
app's own dictionary, not this file: `sdef /Applications/Keynote.app > keynote.sdef`
(80 KB of XML) — re-dump it when a snippet stops working.

## Running JXA

```bash
osascript -l JavaScript -e 'function run(argv){ ... return JSON.stringify(out) }' -- '{"json":"args"}'
```

- `run(argv)` receives the `--` arguments; the return value is printed to stdout.
- Apple Events are blocked in the Claude Code Bash sandbox (`-10004`); see SKILL.md.
- Noise on stderr (`hiservices-xpcservice … Connection invalid`) is harmless.
- One osascript at a time per deck: concurrent opens of the same file race.

## Objects

```javascript
const K = Application("Keynote");
K.running(); K.version(); K.themes.name(); K.documents.name();

// A document is born from a theme. The specifier stays usable after push.
const doc = K.Document({ documentTheme: K.themes["White"], width: 1920, height: 1080 });
K.documents.push(doc);                       // 1 slide exists already
const doc2 = K.open(Path("/abs/deck.key"));  // Path() is mandatory for every file arg
String(doc2.file());                         // POSIX path; throws on an unsaved doc
```

### Layouts, not masters

The upstream "master slide" API is **dead**: `doc.masterSlides.name()`, `masterSlides[i].name()`
and `slide.baseSlide.name()` all throw `-1700 Can't convert types`. The dictionary class is
`slide layout` with `base layout` on each slide:

```javascript
doc.slideLayouts.name();                     // ["Title", "Title & Bullets", ..., "Blank"] — theme-dependent
const s = K.Slide({ baseLayout: doc.slideLayouts["Title & Bullets"] });
doc.slides.push(s);
const slide = doc.slides[doc.slides.length - 1];   // re-fetch by index after push
slide.baseLayout.name();
slide.baseLayout = doc.slideLayouts["Blank"];      // re-layout an existing slide
```

### Slide content

```javascript
slide.defaultTitleItem.objectText = "Title";        // "" (not a throw) on layouts without one
slide.defaultBodyItem.objectText = ["a", "b"].join("\n");
slide.titleShowing(); slide.bodyShowing();          // false → the placeholder is hidden
slide.presenterNotes = "notes"; slide.presenterNotes();
slide.skipped(); slide.slideNumber();

slide.textItems.push(K.TextItem({ objectText: "caption", position: { x: 200, y: 900 }, width: 800, height: 80 }));
slide.textItems.objectText();   // includes empty hidden placeholders and the title twice — filter

slide.images.push(K.Image({ file: Path("/abs/fig.png"), position: { x: 200, y: 200 }, width: 800 }));
slide.images[0].height();       // scaled proportionally (800 → 500 for a 320×200 png)

slide.images.length; slide.tables.length; slide.charts.length; slide.shapes.length; slide.lines.length; slide.groups.length;
```

Text styling lives on the rich text: `item.objectText.size = 64; .font = "Helvetica Neue"; .color = [65535, 0, 0]` (16-bit RGB).

### Tables

```javascript
slide.tables.push(K.Table({ position: { x: 100, y: 200 }, width: 900, height: 500, rowCount: 4, columnCount: 3, headerRowCount: 1 }));
const t = slide.tables[0];
t.rows[r].cells[c].value = "text";     // one Apple Event per cell — slow past ~100 cells
```

### Charts — AppleScript bridge

`add chart` takes list descriptors JXA cannot serialize (`parameter missing`). Prepare in
JS, execute in AppleScript, then position from JXA:

```javascript
const app = Application.currentApplication(); app.includeStandardAdditions = true;
const n = doc.slides.length;   // target slide number, 1-based in AppleScript
app.runScript(`tell application "Keynote" to tell document "${doc.name()}" to tell slide ${n} ¬
  to add chart row names {"Q1","Q2"} column names {"Sales","Cost"} data {{50,30},{65,40}} ¬
  type vertical_bar_2d group by chart row`);
slide.charts[0].position = { x: 200, y: 150 }; slide.charts[0].width = 1500;
```

Types: `vertical_bar_2d horizontal_bar_2d pie_2d line_2d scatter_2d bubble_2d` (3D variants exist, less stable).

## Save, export, close

```javascript
doc.save();                                   // in place
doc.save({ in: Path("/abs/copy.key") });      // writes a copy BUT the document stays bound
                                              // to the original (file() unchanged) — copy on
                                              // disk first and edit the copy instead
doc.export({ to: Path("/abs/out.pdf"), as: "PDF", withProperties: { allStages: true, skippedSlides: false } });
doc.export({ to: Path("/abs/out.pptx"), as: "Microsoft PowerPoint" });
// as: "PDF" | "Microsoft PowerPoint" | "HTML" | "QuickTime movie" | "slide images" | "Keynote 09"
// export options: exportStyle, allStages, skippedSlides, borders, slideNumbers, date,
//   includeComments, PDFImageQuality, imageFormat, movieFormat/codec/framerate, password
doc.close({ saving: "no" });                  // always close what you opened; a never-saved
                                              // theme-born deck otherwise autosaves to iCloud
```

## Transitions

```javascript
slide.transitionProperties = { transitionEffect: "dissolve", transitionDuration: 1.5, transitionDelay: 0, automaticTransition: false };
// "magic move": duplicate the slide (slide.duplicate()), mutate objects on the copy, set the effect on the original
```

## Errors seen

| Code | Meaning | Seen when |
|---|---|---|
| -10004 | privilege violation | Apple Events blocked by the Bash sandbox |
| -1743 | not permitted | Automation consent denied for the runner app (Terminal/Claude) |
| -1700 | can't convert types | any `masterSlides` / `baseSlide` access |
| -10002 | invalid key form | `slide.move({ to: doc.slides.beginning })` — moving slides unresolved |
| -1728 | object not found | bad index or layout name |
| -1708 | event not handled | command the app doesn't implement |

## Not exposed to scripting

Object builds/animations, inspector settings. Only route: System Events UI scripting
(Accessibility permission, fragile). Prefer a template deck with the effect pre-applied.
