# DCMTK Structured Reporting Tools (`dcmsr`)

DICOM Structured Reporting (SR) is the standard's way of encoding *clinical
content* (findings, measurements, CAD output, radiation-dose summaries,
procedure logs) as a typed, hierarchical document inside a DICOM SOP instance
— not as free-text in a `LongString` element. Every SR is a tree of
**content items**; each item is a `Concept Name -> Value` pair plus a
**Value Type** tag that says how to interpret the value:

| Value Type   | Holds                                                      |
|--------------|------------------------------------------------------------|
| `CONTAINER`  | A grouping node — has children, no value of its own.       |
| `TEXT`       | Free text.                                                 |
| `CODE`       | A coded concept (CodeValue + CodingSchemeDesignator + CodeMeaning, e.g. SNOMED, LOINC, DCM). |
| `NUM`        | A numeric measurement with units (also coded).             |
| `DATETIME` / `DATE` / `TIME` | Temporal value.                            |
| `UIDREF`     | Reference to another DICOM SOP instance by UID.            |
| `PNAME`      | Person name (`VR=PN`).                                     |
| `IMAGE`      | Reference to an image (optionally a frame / segment).      |
| `WAVEFORM`   | Reference to a waveform.                                   |
| `SCOORD` / `SCOORD3D` | Spatial coordinates (2D or 3D).                   |
| `TCOORD`     | Temporal coordinates.                                      |
| `COMPOSITE`  | Reference to any other composite SOP instance.             |

Children are attached to their parent through a **relationship type**:
`CONTAINS`, `HAS PROPERTIES`, `HAS OBS CONTEXT`, `HAS ACQ CONTEXT`,
`HAS CONCEPT MOD`, `INFERRED FROM`, `SELECTED FROM`. Together these turn a
flat list of items into a semantic tree.

Common SR SOP Classes (you will meet these all the time):

| SOP Class                                | UID                                  |
|------------------------------------------|--------------------------------------|
| Basic Text SR                            | `1.2.840.10008.5.1.4.1.1.88.11`      |
| Enhanced SR                              | `1.2.840.10008.5.1.4.1.1.88.22`      |
| Comprehensive SR                         | `1.2.840.10008.5.1.4.1.1.88.33`      |
| Comprehensive 3D SR                      | `1.2.840.10008.5.1.4.1.1.88.34`      |
| Procedure Log                            | `1.2.840.10008.5.1.4.1.1.88.40`      |
| Mammography CAD SR                       | `1.2.840.10008.5.1.4.1.1.88.50`      |
| Key Object Selection Document            | `1.2.840.10008.5.1.4.1.1.88.59`      |
| Chest CAD SR                             | `1.2.840.10008.5.1.4.1.1.88.65`      |
| X-Ray Radiation Dose SR                  | `1.2.840.10008.5.1.4.1.1.88.67`      |
| Radiopharmaceutical Radiation Dose SR    | `1.2.840.10008.5.1.4.1.1.88.68`      |
| Colon CAD SR                             | `1.2.840.10008.5.1.4.1.1.88.69`      |
| Patient Radiation Dose SR                | `1.2.840.10008.5.1.4.1.1.88.73`      |
| Waveform Annotation SR                   | `1.2.840.10008.5.1.4.1.1.88.77`      |

**When to use these tools vs. `dcmdump`.** `dcmdump` shows the raw DICOM
attribute tree — every `(0040,A040) Value Type`, every nested
`ContentSequence`. That's correct but unreadable: you have to mentally
re-thread the parent/child links yourself. The `dcmsr` tools traverse
those sequences for you and reconstruct the **content tree** as it was
authored, printing concept names, codes, and relationship types in a
form that matches David Clunie's *DICOM Structured Reporting* book. Use
`dcmdump` when you suspect encoding bugs at the attribute level; use
`dsrdump` / `dsr2html` when you want to actually *read* the report.

See [common-options.md](common-options.md) for the shared flag families
(`-v`, `-d`, `--read-file` vs `--read-dataset`, `-t*` transfer-syntax
hints, `--write-xfer-*`). The four tools below all support those.

---

## `dsrdump` — text dump of an SR document

Produces a human-readable, indented rendering of the SR content tree on
stdout. This is the fastest "what's in this file?" check.

### Synopsis

```
dsrdump [options] dsrfile-in...
```

`dsrfile-in` is one or more DICOM SR files. Use `-` for stdin. Multiple
inputs are dumped sequentially.

### Essential flags

**Document framing**

| Flag                          | Effect                                                          |
|-------------------------------|-----------------------------------------------------------------|
| `+Pf`, `--print-filename`     | Prefix each document with a header naming the file. Helpful when dumping a whole directory. |
| `-Ph`, `--no-document-header` | Skip the SR-document title block (patient, study, content date, completion flag). Keep only the content tree. |
| `+Pn`, `--number-nested-items`| Print a positional path (e.g. `1.2.3`) in front of each line. Lets you reference items unambiguously. |
| `-Pn`, `--indent-nested-items`| Indent by spaces only (default). |

**What to show on each item**

| Flag                            | Effect                                                       |
|---------------------------------|--------------------------------------------------------------|
| `+Pc`, `--print-all-codes`      | Print the underlying `(CodeValue, CodingScheme)` next to every code, including concept names. Without this, you only see the human-readable `CodeMeaning`. |
| `+Pt`, `--print-template-id`    | Show template identifier in the document/section heading (TID 2000, TID 1500, ...). |
| `+Pu`, `--print-instance-uid`   | Print the SOP Instance UID of referenced objects (IMAGE, COMPOSITE, WAVEFORM items). |
| `-Ps`, `--print-sopclass-short` | Short SOP-class name for referenced images, e.g. `CT image` (default). |
| `+Ps`, `--print-sopclass-long`  | Full SOP-class name (`CT Image Storage`). |
| `+Psu`, `--print-sopclass-uid`  | Print the full SOP Class UID. |
| `+Pl`, `--print-long-values`    | Don't truncate long text/value strings (default truncates). |
| `+Pi`, `--print-invalid-codes`  | Show invalid code triples instead of the placeholder text. Debugging only. |
| `+Pe`, `--indicate-enhanced`    | Mark items that use enhanced-encoding mode for codes. |

**Suppressing structure**

There is no single `--no-relationship-types` flag — DCMTK always prints
the relationship (`CONTAINS`, `HAS CONCEPT MOD`, ...) on each child line.
If you want just the values, post-process with `awk`/`sed`, or pipe
through `rg -v 'CONTAINS|HAS '`.

**Error tolerance** (useful on non-conformant SRs from third-party CAD
vendors)

| Flag                          | Effect                                                       |
|-------------------------------|--------------------------------------------------------------|
| `-Er`, `--unknown-relationship` | Don't fail on unknown/missing relationship types.          |
| `-Ev`, `--invalid-item-value` | Accept value-type / VR / VM violations.                      |
| `-Ec`, `--ignore-constraints` | Skip IOD-level relationship constraints.                     |
| `-Ee`, `--ignore-item-errors` | Warn instead of abort on per-item errors.                    |
| `-Ei`, `--skip-invalid-items` | Drop the offending item *and its sub-tree* from output.      |
| `-Dv`, `--disable-vr-checker` | Don't validate string VRs.                                   |

**Character set**

| Flag                       | Effect                                                          |
|----------------------------|-----------------------------------------------------------------|
| `+U8`, `--convert-to-utf8` | Recode every charset-affected element to UTF-8 before dumping. **Use this for any non-ASCII report** (Thai, Japanese, German umlauts, etc.) — otherwise you'll see mojibake in your terminal. |

**Color**

| Flag                | Effect                                                |
|---------------------|-------------------------------------------------------|
| `+C`, `--print-color` | ANSI escapes for colored output. Nice in a terminal, breaks `less -R` pipelines if you forget. |
| `-C`, `--no-color`  | Plain text (default).                                 |

### Examples

```bash
# Quick look at an SR file
dsrdump input.sr

# Full disclosure: all codes, template IDs, long values, no truncation
dsrdump +Pc +Pt +Pl +Pu input.sr

# Non-ASCII report, colored, content tree only (no header)
dsrdump +U8 +C -Ph input.sr | less -R

# Dump everything in a directory with a filename header per file
dsrdump +Pf *.sr > all-reports.txt

# Tolerate a slightly broken third-party CAD SR
dsrdump -Er -Ev -Ee input.sr
```

### Gotchas

- Reads file format **or** raw dataset by default. If you have a raw
  dataset whose TS guessing fails, force it with `-f -te` (or `-ti`).
- `+Pc` (print all codes) is almost always what you want when you're
  trying to map an SR to its template — the bare `CodeMeaning` strings
  are ambiguous across coding schemes.
- For X-Ray Radiation Dose SR (RDSR), combine `+Pt +Pc` so you can see
  TID 10001/10002/10003 hierarchies and resolve DCM codes.

---

## `dsr2html` — render an SR document as HTML/XHTML

Same content tree as `dsrdump`, but rendered as a proper document with
headings, tables, and (optionally) a stylesheet — suitable for emailing
to a referrer or attaching to a PDF.

### Synopsis

```
dsr2html [options] dsrfile-in [htmlfile-out]
```

`htmlfile-out` defaults to stdout.

### Essential flags

**Output dialect**

| Flag                | Effect                                                      |
|---------------------|-------------------------------------------------------------|
| `+H4`, `--html-4.0` | HTML 4.01 (default). Note: this is HTML 4.01, NOT HTML5 — the man page mentions only HTML 3.2, 4.01, and XHTML 1.1. There is no `--html5` flag in DCMTK 3.7.x. |
| `+H3`, `--html-3.2` | HTML 3.2 (no CSS support).                                  |
| `+X1`, `--xhtml-1.1`| XHTML 1.1.                                                  |
| `+Hd`, `--add-document-type` | Emit the SGML DOCTYPE reference at the top of the file. |

**Stylesheet**

| Flag                                 | Effect                                                  |
|--------------------------------------|---------------------------------------------------------|
| `+Sr URL`, `--css-reference URL`     | Add a `<link rel="stylesheet" href="URL">` to the output. CSS must be reachable wherever the HTML is opened. |
| `+Sf FILE`, `--css-file FILE`        | Inline the contents of FILE inside a `<style>` block. Use this for a self-contained, emailable HTML file. |

DCMTK ships two sample stylesheets: `<datadir>/report.css` (HTML) and
`<datadir>/reportx.css` (XHTML). On macOS Homebrew: typically under
`/opt/homebrew/share/dcmtk/`.

**Document framing**

| Flag                                | Effect                                                       |
|-------------------------------------|--------------------------------------------------------------|
| `+Dt`, `--document-type-title`      | Use the SR document type as `<title>` (default).             |
| `+Dp`, `--patient-info-title`       | Use patient info as `<title>` instead. **Privacy risk** if the HTML escapes the controlled environment. |
| `-Dh`, `--no-document-header`       | Skip the patient/study/document-info block at the top.       |

**Rendering by-reference content**

SR allows one item to reference another item by its position
(`by-reference`). dsr2html can either inline the referenced subtree at
the reference site or just link to it.

| Flag                              | Effect                                                |
|-----------------------------------|-------------------------------------------------------|
| `+Ri`, `--expand-inline`          | Expand short referenced items inline (default).       |
| `-Ri`, `--never-expand-inline`    | Always render references as hyperlinks, never inline. |
| `+Ra`, `--always-expand-inline`   | Inline-expand even long subtrees.                     |
| `+Rd`, `--render-full-data`       | Render full data of content items (don't summarize).  |
| `+Rt`, `--section-title-inline`   | Render section titles inline instead of as separate headings. |
| `+Rh PREFIX`, `--hyperlink-url-prefix PREFIX` | URL prefix for hyperlinks to composite objects (default: `http://localhost/dicom.cgi`). |

**Code rendering**

| Flag                              | Effect                                                |
|-----------------------------------|-------------------------------------------------------|
| `+Ci`, `--render-inline-codes`    | Render codes inline within text (compact).            |
| `+Cn`, `--concept-name-codes`     | Render the code triple next to each concept name.     |
| `+Cu`, `--numeric-unit-codes`     | Render the code for measurement units.                |
| `+Cv`, `--code-value-unit`        | Use code value as unit label (default, e.g. `mm`).    |
| `+Cm`, `--code-meaning-unit`      | Use code meaning as unit label (e.g. `millimeter`).   |
| `+Cc`, `--render-all-codes`       | Shortcut for `+Ci +Cn +Cu`.                           |
| `+Ct`, `--code-details-tooltip`   | Render code triple as a `<abbr>` tooltip on hover (implies `+Cc`). Great UX for reviewers. |

**Charset** (same family as dsrdump)

| Flag                            | Effect                                                |
|---------------------------------|-------------------------------------------------------|
| `+Cr`, `--charset-require`      | Require declared extended charset (default).          |
| `+Ca CHARSET`, `--charset-assume CHARSET` | Assume this charset if none declared. Useful for legacy files missing `(0008,0005)`. |
| `+U8`, `--convert-to-utf8`      | Recode all string elements to UTF-8 before rendering. Almost always recommended. |

### Examples

```bash
# Self-contained HTML page, UTF-8, with embedded stylesheet (emailable)
dsr2html +U8 +Sf /opt/homebrew/share/dcmtk/report.css \
         +Ct input.sr > out.html

# XHTML 1.1 with external stylesheet reference
dsr2html +X1 +Sr ./report.css input.sr > out.xhtml

# Strip the header block, render every code inline, full data
dsr2html -Dh +Cc +Rd input.sr > content-only.html

# Pipe through stdin
dcmconv input.sr - | dsr2html +U8 - report.html
```

### Gotchas

- **No HTML5.** The man page lists only HTML 3.2 / 4.01 / XHTML 1.1.
  Modern browsers render the HTML-4.01 output fine, but don't expect
  `<article>` / `<section>` tags.
- `+Sr` and `+Sf` and `+Rh` perform **no input sanitization** — a
  malicious filename or URL prefix can inject content into the output.
  Don't pass un-trusted strings to these flags.
- `+Dp` (`--patient-info-title`) puts PHI into the `<title>` tag,
  which means PHI in the browser tab and history. Default `+Dt` is the
  safer choice unless you're inside a controlled viewer.
- The HTML hyperlinks for `IMAGE` / `COMPOSITE` items use `+Rh`'s
  prefix — they only work if you have a CGI/web service that resolves
  SOP Instance UIDs at that URL.

---

## `dsr2xml` — convert an SR document to DCMTK's SR-XML representation

Serializes the SR content tree to XML using DCMTK's own schema
(`dsr2xml.xsd`). This is **not** the same XML you get from `dcm2xml` —
`dcm2xml` produces a generic *dataset* XML (every DICOM attribute as
`<element tag="...">`), whereas `dsr2xml` produces a *content-tree* XML
with `<container>`, `<text>`, `<num>`, `<code>` nodes that mirror the SR
semantics. **Only `xml2dsr` (its inverse) can round-trip dsr2xml's
output back to DICOM** — generic DICOM-XML tools cannot.

### Synopsis

```
dsr2xml [options] dsrfile-in [xmlfile-out]
```

`xmlfile-out` defaults to stdout.

### Essential flags

**Encoding strategy**

By default, value-type / relationship / code / template-id information
is encoded as XML *elements*. The `+E*` flags promote them to XML
*attributes* — more compact but harder to extend.

| Flag                          | Effect                                                       |
|-------------------------------|--------------------------------------------------------------|
| `+Ec`, `--attr-code`          | Encode code value, scheme designator, scheme version as attributes. |
| `+Er`, `--attr-relationship`  | Encode relationship type as an attribute on the child node.  |
| `+Ev`, `--attr-value-type`    | Encode value type as an attribute.                           |
| `+Et`, `--attr-template-id`   | Encode template ID as an attribute.                          |
| `+Ea`, `--attr-all`           | Shortcut for `+Ec +Er +Ev +Et`.                              |
| `+Ee`, `--template-envelope`  | Wrap content items inside a `<template>` envelope (requires `+Wt`, implies `+Et`). |

**XML structure**

| Flag                              | Effect                                                |
|-----------------------------------|-------------------------------------------------------|
| `+Xs`, `--add-schema-reference`   | Add `xsi:schemaLocation` pointing at `dsr2xml.xsd`. Cannot be combined with the `+E*` / `+We` shortcuts because they break schema conformance. |
| `+Xn`, `--use-xml-namespace`      | Declare the DCMTK SR XML namespace on the root element. **Recommended whenever you plan to round-trip with `xml2dsr`** — `xml2dsr +Vn` can then verify the namespace. |

**Writing options**

| Flag                          | Effect                                                       |
|-------------------------------|--------------------------------------------------------------|
| `+We`, `--write-empty-tags`   | Emit elements even when their value is empty.                |
| `+Wi`, `--write-item-id`      | Always write the per-item identifier (needed if other items reference this one by-reference). |
| `+Wt`, `--write-template-id`  | Emit template identification information.                    |

**Error tolerance** and **charset** flags are the same family as
`dsrdump` (`-Er`, `-Ev`, `-Ec`, `-Ee`, `-Ei`, `-Dv`, `+Cr`, `+Ca`,
`+U8`). `+U8` is strongly recommended — without it, non-ASCII chars
become numeric entities like `&#27;` which are often invalid XML.

### Examples

```bash
# Default encoding, schema-conformant, with namespace (best for round-trip)
dsr2xml +Xn +Xs +U8 input.sr > out.xml

# Compact attribute-based encoding (smaller but not schema-conformant)
dsr2xml +Ea +U8 input.sr > compact.xml

# Preserve every item ID and template ID for full fidelity
dsr2xml +Xn +Wi +Wt +U8 input.sr > full.xml
```

### Gotchas

- **Not generic DICOM-XML.** Don't feed `dsr2xml` output to `xml2dcm`
  or vice versa. They use different schemas.
- The schema (`<datadir>/dsr2xml.xsd`) does **not** cover every
  combination of flags. The man page is explicit: only the default
  output plus `--use-xml-namespace` is guaranteed schema-valid.
- Only *mandatory and some optional* SR attributes are serialized.
  Vendor private extensions inside the SR may be silently dropped.

---

## `xml2dsr` — convert dsr2xml's XML back to DICOM SR

The inverse of `dsr2xml`. Lets you edit the content tree as XML in any
text editor and re-emit a valid DICOM SR file.

### Synopsis

```
xml2dsr [options] xmlfile-in dsrfile-out
```

Both arguments are mandatory (unlike `dsr2xml`). Use `-` for stdin /
stdout.

### Essential flags

**Input shape**

| Flag                              | Effect                                                |
|-----------------------------------|-------------------------------------------------------|
| `+Ee`, `--template-envelope`      | Expect content items wrapped inside a `<template>` envelope (matches `dsr2xml +Ee`). |

**Validation**

| Flag                                | Effect                                                      |
|-------------------------------------|-------------------------------------------------------------|
| `+Vs`, `--validate-schema`          | Validate the input XML against the bundled `dsr2xml.xsd`. Requires libxml built with XML-Schema support — check `xml2dsr --version`. Cannot be used with `--template-envelope`. |
| `+Vn`, `--check-namespace`          | Verify the root element declares the DCMTK SR XML namespace (`+Xn` from dsr2xml). |

**UID handling**

| Flag                              | Effect                                                |
|-----------------------------------|-------------------------------------------------------|
| `+Ug`, `--generate-new-uids`      | Mint fresh Study / Series / SOP Instance UIDs. Use this whenever you've materially edited the content and want a new, distinct instance. |
| `-Uo`, `--dont-overwrite-uids`    | Keep existing UIDs from the XML (default).            |
| `+Uo`, `--overwrite-uids`         | Overwrite even UIDs that are present in the XML. Only meaningful with `+Ug`. |

**Output transfer syntax**

| Flag                              | Effect                                                |
|-----------------------------------|-------------------------------------------------------|
| `+t=`, `--write-xfer-same`        | Same TS as the original (default; the original TS UID is carried in the XML). |
| `+te`, `--write-xfer-little`      | Explicit-VR little endian.                            |
| `+tb`, `--write-xfer-big`         | Explicit-VR big endian.                               |
| `+ti`, `--write-xfer-implicit`    | Implicit-VR little endian.                            |
| `+td`, `--write-xfer-deflated`    | Deflated explicit-VR LE (needs zlib).                 |
| `+cl LEVEL`, `--compression-level LEVEL` | zlib level 0–9 (default 6) for `+td`.          |

**Output framing**

| Flag                              | Effect                                                |
|-----------------------------------|-------------------------------------------------------|
| `+F`, `--write-file`              | Write Part-10 file format with meta header (default). |
| `-F`, `--write-dataset`           | Raw dataset only.                                     |

Plus the usual `+u`/`-u` new-VR toggles, `+g*` group-length, `+e`/`-e`
sequence length encoding, and `+p` dataset padding. See
[common-options.md](common-options.md).

### Examples

```bash
# Straight round-trip
dsr2xml +Xn +U8 input.sr > edit.xml
# (edit edit.xml in your favorite editor)
xml2dsr +Vn +Vs edit.xml out.sr

# Treat this as a new SR instance (fresh UIDs)
xml2dsr +Ug edit.xml out.sr

# Read from stdin, force explicit-VR LE on output
cat edit.xml | xml2dsr +te - out.sr
```

### Gotchas

- The libxml that `xml2dsr` is linked against has a per-element value
  length cap (10 MB for libxml >= 2.7.3). Avoid storing huge text
  blocks in a single SR `TEXT` item.
- ZIP-compressed XML input is accepted if libxml has zlib support.
  Check `xml2dsr --version`.
- `+Vs` cannot validate XML that uses `--template-envelope` (`+Ee`)
  — the schema doesn't model that variant.
- If your XML lacks `(0008,0005) SpecificCharacterSet` and contains
  non-ASCII, the resulting SR will encode bytes in whatever default
  the dictionary suggests — set the SR character set explicitly in
  the XML before round-tripping non-ASCII reports.

---

## Common SR workflows

### "What's in this SR file?"

```bash
dsrdump input.sr
# or, with all the details:
dsrdump +Pc +Pt +Pu +U8 input.sr | less
```

### "Make a human-readable report for a referrer"

```bash
dsr2html +U8 \
         +Sf /opt/homebrew/share/dcmtk/report.css \
         +Ct \
         input.sr > out.html
```

`+Sf` inlines the CSS so the file is self-contained; `+Ct` renders
code triples as hover tooltips.

### "Round-trip edit the SR text content"

```bash
# 1. Serialize to XML (namespace + schema-friendly)
dsr2xml +Xn +U8 input.sr > edit.xml

# 2. Edit edit.xml — change text values, add/remove items, etc.

# 3. Convert back, optionally minting new UIDs since you changed content
xml2dsr +Vn +Vs +Ug edit.xml out.sr

# 4. Sanity-check the result
dsrdump out.sr
```

### "Compare two SR files semantically"

Raw `diff` on DICOM bytes is useless. Convert both to text first:

```bash
diff <(dsrdump +Pc +Pt a.sr) <(dsrdump +Pc +Pt b.sr)
```

### "Bulk-render a folder of SRs to HTML"

```bash
fd -e sr . inbox/ | while read -r f; do
  out="reports/$(basename "${f%.sr}").html"
  dsr2html +U8 +Sf /opt/homebrew/share/dcmtk/report.css "$f" > "$out"
done
```

### "Pull a single concept value out of an SR (scripting)"

`dsr2xml` + `xmllint --xpath` (or `xq`) is more reliable than
text-scraping `dsrdump`:

```bash
dsr2xml +Xn input.sr |
  xmllint --xpath "//num[concept/value='113838']/value/text()" -
```

(`113838` is the DCM code for `Dose Length Product Total` in RDSR.)

---

## See also

- [common-options.md](common-options.md) — shared `-v` / `-d` /
  `--read-file` / `--write-xfer-*` flag families.
- `dcmdump` — raw attribute-level view of any DICOM file, including
  SRs. Use when you suspect encoding bugs below the SR-tree level.
- `dcmconv` — convert between transfer syntaxes; useful for
  normalizing an SR before round-tripping.
- David Clunie, *DICOM Structured Reporting* (PixelMed Publishing,
  2000) — `dsrdump`'s output format follows the conventions in this
  book.
