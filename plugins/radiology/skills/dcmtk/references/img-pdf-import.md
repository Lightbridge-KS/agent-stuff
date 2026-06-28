# DCMTK Image / PDF Import & Export

DCMTK ships a small family of bridge tools that move data between DICOM and
non-DICOM file formats. This page covers the three you reach for most often:

| Tool       | Direction                          | Use it when…                                                                  |
|------------|------------------------------------|-------------------------------------------------------------------------------|
| `img2dcm`  | image → DICOM image SOP            | You have a JPEG / BMP (etc.) and need a valid DICOM image object.            |
| `pdf2dcm`  | PDF → Encapsulated PDF Storage     | You have a PDF report and need it inside DICOM. **Deprecated wrapper around `dcmencap`** in 3.7.0+. |
| `dcm2pdf`  | Encapsulated PDF Storage → PDF     | You have a DICOM file whose payload *is* a PDF and you want the PDF back. **Deprecated wrapper around `dcmdecap`** in 3.7.0+. |

Shared flags (`--help`, `--verbose`, `--debug`, `+F`/`-F`, `+te`/`+ti`, etc.)
are documented in [common-options.md](common-options.md) — they are not
re-explained per tool here.

---

## When do I need `img2dcm` vs `pdf2dcm`?

Pick by **input MIME type**, not by what the DICOM object is conceptually for:

```
JPEG / BMP / (JPEG-LS)   ──► img2dcm   ──► Secondary Capture or VL Photo image
PDF                      ──► pdf2dcm   ──► Encapsulated PDF Storage
CDA / STL / MTL / OBJ    ──► dcmencap  ──► Encapsulated CDA / 3D model storage
```

Common pitfalls:

- **Trying to wrap a PDF as Secondary Capture via `img2dcm`.** Doesn't work —
  `img2dcm` does not accept PDF input at all, and Secondary Capture is a *pixel*
  IOD (Rows / Columns / PixelData). PDFs belong in **Encapsulated PDF Storage**
  (SOP Class UID `1.2.840.10008.5.1.4.1.1.104.1`). Use `pdf2dcm`.
- **Trying to view an Encapsulated PDF in a regular DICOM image viewer.**
  Most image viewers ignore the encapsulated stream — you need a PDF-aware
  viewer or you have to `dcm2pdf` the payload back out first.
- **Confusing "DICOM-ized report" with "structured report".** Encapsulated PDF
  is *not* DICOM SR. It's just a PDF inside a DICOM envelope. If you need
  searchable, queryable content, generate an SR instead (out of scope here).

> **3.7.0 note on deprecation.** In DCMTK 3.7.0, `pdf2dcm` and `dcm2pdf` print
> a deprecation banner on every invocation and delegate to `dcmencap` /
> `dcmdecap`, which support the same flags plus CDA / STL / MTL / OBJ. New
> code should call `dcmencap` / `dcmdecap` directly. The flag set documented
> below is what works in both the legacy and successor binaries.

---

## `img2dcm` — wrap a standard image into a DICOM image SOP

### Synopsis

```
img2dcm [options] imgfile-in... dcmfile-out
```

Multiple input filenames are only meaningful with `--new-sc` (Multi-frame
Secondary Capture). For single-frame SOP classes pass exactly one input.

### Essential flags

#### Input format selection

| Flag                    | Effect                                                                              |
|-------------------------|-------------------------------------------------------------------------------------|
| `-i JPEG`               | Default. Also handles JPEG-LS — the same plugin probes the bitstream.               |
| `-i BMP`                | Read a BMP. Only common BMP variants — RLE-encoded and bit-field BMPs are rejected. |

> **Format gotcha.** Despite what older DCMTK docs sometimes imply, **`img2dcm`
> in 3.7.0 ships with JPEG and BMP plugins only** — no PNG, no TIFF. Run
> `img2dcm --help` and check the line beginning "supported formats:" on your
> own build. If you need PNG/TIFF in, convert externally first (`magick
> in.png out.jpg`) and then feed the JPEG to `img2dcm`. Run `img2dcm --version`
> to see which optional libraries the binary was actually linked with.

#### Output SOP class

| Flag          | SOP class written                                                                  |
|---------------|-------------------------------------------------------------------------------------|
| `-sc`         | **Default.** "Old" Secondary Capture Image Storage (`1.2.840.10008.5.1.4.1.1.7`). Deprecated by the standard but the most widely-accepted choice — almost every viewer renders it. |
| `-nsc`        | "New" Secondary Capture family — `img2dcm` auto-picks the right one based on bit depth (1 / 8 / 16) and color vs. grayscale. Required for **multi-frame** output. |
| `-vlp`        | Visible Light Photographic Image Storage (`1.2.840.10008.5.1.4.1.1.77.1.4`). The right answer for dermatology, endoscopy, gross pathology shots. |
| `-oph`        | Ophthalmic Photography Image Storage. Comes with required XML templates (see Files). |

There is **no** `--vl-microscopic` plugin in `img2dcm` (despite the family
existing in the standard). For VL Microscopic you have to build the dataset
yourself with `dump2dcm` / `dcmodify`.

#### Patient / study / series inheritance — *the* big topic

A bare `img2dcm input.jpg out.dcm` produces a minimum-viable DICOM file with
**synthesized** Study/Series/SOP Instance UIDs and an empty (but present)
PatientID, PatientName, etc. Most PACS and viewers will accept the file, but
it will land as an orphan study with no real patient context. **You almost
always want to attach the new object to existing context.**

Three mechanisms, applied in this order:

| Flag                     | Inherits                                                                                          |
|--------------------------|----------------------------------------------------------------------------------------------------|
| `-df`, `--dataset-from FILE`     | **Full** DICOM dataset is imported as a template (then PixelData / Rows / Columns / SOP Class UID are replaced). SOP Instance UID is *not* copied. Use `<datadir>/SC.dump` or `VLP.dump` as a starting template. |
| `-dx`, `--dataset-from-xml FILE` | Same as `--dataset-from` but the template is the XML format produced by `dcm2xml`. Mutually exclusive with `--dataset-from`. |
| `-stf`, `--study-from FILE`      | Patient + study attributes only (Patient Name/ID/Sex/Birth Date, Specific Character Set, Study Instance UID, Study Date/Time, Referring Physician, Study ID, Accession Number). |
| `-sef`, `--series-from FILE`     | All of `--study-from` **plus** Series Instance UID, Series Number, Manufacturer. Use when the new image belongs in an *existing* series, not a new one. |
| `-ii`, `--instance-inc`          | When `--series-from` is used, increment the InstanceNumber from the source instead of reusing it. |
| `-k`, `--key TAG=VALUE`          | Force a specific attribute. Applied **last**, so it overrides everything else. Repeatable. Accepts `gggg,eeee="…"`, a dictionary keyword, or a path expression (same syntax as `dcmodify`). |

Order of precedence (rightmost wins):

```
defaults  <  --dataset-from / --dataset-from-xml  <  --study-from  <  --series-from  <  --key
```

#### Attribute validity checking

| Flag             | Effect                                                                                |
|------------------|----------------------------------------------------------------------------------------|
| `--do-checks`    | Default. Verify type 1/2 attributes are present.                                       |
| `--no-checks`    | Skip checking. **Produces invalid DICOM** unless you patch it later with `dcmodify`.   |
| `+i2`            | Insert missing type 2 attributes with zero length (default; only with `--do-checks`).  |
| `-i2`            | Don't insert missing type 2 attributes.                                                |
| `+i1`            | Invent values for missing type 1 attributes (default; only with `--do-checks`).        |
| `-i1`            | Don't invent type 1 values — error out instead. Use when you'll provide them via `-k`. |

#### JPEG-specific knobs

| Flag                | Effect                                                                                       |
|---------------------|----------------------------------------------------------------------------------------------|
| `-dp`               | Disable progressive JPEG support (retired TS `…4.55`).                                       |
| `-de`               | Disable extended sequential JPEG (TS `…4.51`).                                               |
| `-jf`               | **Require** a JFIF header — abort if missing. Most digital-camera JPEGs lack JFIF.           |
| `-ka`               | Keep APPn segments (EXIF, etc.) inside the embedded JPEG. JFIF (APP0) is *always* stripped.  |
| `-rc`               | Strip the COM (comment) segment.                                                             |

#### JPEG transfer-syntax behavior — important

`img2dcm` **does not transcode JPEG bytes**. It strips JFIF/APPn markers and
encapsulates the original bitstream into the DICOM pixel data, then **picks
the transfer syntax automatically** based on the JPEG's coding process:

| JPEG coding process                            | Output transfer syntax UID         |
|------------------------------------------------|------------------------------------|
| Process 1 — baseline 8-bit                     | `1.2.840.10008.1.2.4.50`           |
| Process 2 / 4 — extended sequential 8 / 12-bit | `1.2.840.10008.1.2.4.51`           |
| Process 10 / 12 — progressive 8 / 12-bit       | `1.2.840.10008.1.2.4.55` (retired) |
| JPEG-LS lossless                               | `1.2.840.10008.1.2.4.80`           |
| JPEG-LS near-lossless                          | `1.2.840.10008.1.2.4.81`           |

JPEG-Lossless, arithmetic, and hierarchical JPEG encodings are **not**
supported. If your source is one of those, transcode first with
`dcmcjpeg`/`dcmcjpls` after wrapping, or convert to baseline JPEG outside
DICOM.

If you need an *uncompressed* DICOM (some legacy PACS want only explicit-VR
LE), decompress the JPEG to a pixel buffer outside DICOM and rebuild — or run
the resulting compressed DICOM through `dcmdjpeg`.

### Examples

```bash
# 1. Quick-and-dirty: JPEG → Secondary Capture, all IDs invented.
#    Result is technically valid DICOM but orphaned — no real patient/study.
img2dcm input.jpg out.dcm

# 2. BMP → Secondary Capture.
img2dcm -i BMP input.bmp out.dcm

# 3. THE REALISTIC CASE: attach a new SC image to an existing study.
#    reference.dcm is any DICOM instance from the target study.
img2dcm input.jpg out.dcm \
    --study-from reference.dcm \
    -k "SeriesDescription=Clinical photo" \
    -k "Modality=XC"

# 4. Add to an *existing series* (e.g. another photo in the same series),
#    auto-incrementing InstanceNumber.
img2dcm input.jpg out.dcm \
    --series-from reference.dcm \
    --instance-inc

# 5. Visible Light Photographic instead of Secondary Capture — the correct
#    SOP class for clinical photography (derm, endoscopy, gross specimen).
img2dcm input.jpg out.dcm -vlp \
    --study-from reference.dcm \
    -k "PatientName=Doe^Jane"

# 6. Multi-frame Secondary Capture from several JPEGs (one output file).
img2dcm frame_01.jpg frame_02.jpg frame_03.jpg out.dcm --new-sc \
    --study-from reference.dcm

# 7. Skip validity checks — produces an incomplete file you'll fix with
#    dcmodify later. Don't ship this to a PACS as-is.
img2dcm input.jpg partial.dcm --no-checks

# 8. Preserve EXIF inside the embedded JPEG bitstream (DICOM-legal gray area).
img2dcm input.jpg out.dcm --keep-appn

# 9. Use a hand-prepared template (from <datadir>/SC.dump dumped via dump2dcm)
#    instead of relying on auto-invented type 1 attributes.
img2dcm input.jpg out.dcm --dataset-from sc_template.dcm
```

### Gotchas

- **No PNG / TIFF.** Convert externally first.
- **SOP Instance UID is *never* copied** from the template — a fresh one is
  generated every run. If you need a stable SOP Instance UID, force it with
  `-k "SOPInstanceUID=1.2.3.…"`. Re-using UIDs across instances is normally
  wrong; only do this when intentionally replacing an instance.
- **`-k` is applied last** — it wins over `--study-from`, `--series-from`,
  and the template. This is the *only* way to override a value from the
  template.
- **Character set conflicts.** When you mix `--dataset-from` with
  `--study-from`, the study file's character set is converted to the
  template's. If conversion fails, the run aborts; pass `-Ct`
  (`--transliterate`) or `-Cd` (`--discard-illegal`) to recover. Values passed
  via `-k` are raw bytes — `img2dcm` will not transcode them, so feed
  UTF-8/Latin-1 to match `SpecificCharacterSet`.
- **Don't use `--no-checks` for files you'll send to a PACS.** Many SCPs
  reject objects with missing type 1 attributes during C-STORE.

---

## `pdf2dcm` — wrap a PDF as DICOM Encapsulated PDF Storage

> **In DCMTK 3.7.0 this tool prints a deprecation banner and forwards to
> `dcmencap`.** The flags below work identically against either binary; new
> scripts should call `dcmencap` directly.

### Synopsis

```
pdf2dcm  [options] pdffile-in  dcmfile-out
dcmencap [options] docfile-in  dcmfile-out   # successor — same flags, also CDA/STL/MTL/OBJ
```

The output SOP Class UID is **`1.2.840.10008.5.1.4.1.1.104.1`** (Encapsulated
PDF Storage). The PDF is stored verbatim in the `EncapsulatedDocument`
(`0042,0011`) attribute.

### Essential flags

#### Input format

| Flag       | Effect                                                                |
|------------|-----------------------------------------------------------------------|
| `+fa`      | Auto-detect input file type (default — `dcmencap` only).              |
| `+fp`      | Force PDF input.                                                      |
| `+fc`      | Encapsulated CDA Storage (`dcmencap`, not `pdf2dcm`).                 |
| `+fs` / `+fm` / `+fo` | STL / MTL / OBJ 3D model storage (`dcmencap`).             |

#### Document title and language

| Flag                              | Effect                                                                            |
|-----------------------------------|------------------------------------------------------------------------------------|
| `+t TITLE`,    `--title TITLE`    | DocumentTitle (`0042,0010`). Default: empty (legacy `pdf2dcm` defaulted to the input filename — confirm on your binary). Set it explicitly; PACS worklists display it. |
| `+cn CSD CV CM`, `--concept-name` | Coded representation of the title (Coding Scheme Designator, Code Value, Code Meaning). Used for SR-style indexing. |
| *(no `--language` flag in 3.7.0)* | DocumentLanguage is not a top-level CLI flag in the current `dcmencap`. Inject it with `-k "0008,0012"` style overrides if your IOD profile requires it. |

#### Patient + study + series context

Encapsulated PDF Storage requires the **full Patient + General Study + General
Series** modules. Provide context via *one* of:

| Flag                          | Effect                                                                            |
|-------------------------------|------------------------------------------------------------------------------------|
| `+sg`, `--generate`           | Default. Generate fresh Study + Series UIDs.                                       |
| `+st`, `--study-from FILE`    | Inherit patient + study attributes from an existing DICOM file (same semantics as `img2dcm --study-from`). |
| `+se`, `--series-from FILE`   | Inherit patient + study + series. Attaches the PDF to an existing series.          |
| `+pn NAME`, `--patient-name`  | Manually set PatientName (DICOM PN syntax: `Family^Given^Middle^Prefix^Suffix`).   |
| `+pi ID`,   `--patient-id`    | PatientID.                                                                         |
| `+pb DATE`, `--patient-birthdate` | PatientBirthDate in `YYYYMMDD`.                                                |
| `+ps SEX`,  `--patient-sex`   | `M`, `F`, or `O`.                                                                  |

#### Instance number

| Flag                          | Effect                                                                |
|-------------------------------|-----------------------------------------------------------------------|
| `+i1`, `--instance-one`       | Use InstanceNumber `1` (default; **not** valid with `+se`).           |
| `+ii`, `--instance-inc`       | Increment from the source (only with `+se`).                          |
| `+is N`, `--instance-set N`   | Force a specific InstanceNumber.                                      |

#### Device / manufacturer

| Flag                      | Effect                                          |
|---------------------------|--------------------------------------------------|
| `+mn NAME`, `--manufacturer`       | Manufacturer.                          |
| `+mm NAME`, `--manufacturer-model` | Manufacturer Model Name.              |
| `+ds N`,    `--device-serial`      | DeviceSerialNumber.                    |
| `+sv V`,    `--software-versions`  | SoftwareVersions.                      |

#### Burned-in annotation (PHI flag)

| Flag                  | Effect                                                                              |
|-----------------------|--------------------------------------------------------------------------------------|
| `+an`, `--annotation-yes` | Default. Set `BurnedInAnnotation = YES` — the doc may contain patient-identifying text. |
| `-an`, `--annotation-no`  | `BurnedInAnnotation = NO`. Only set this if you've actually verified the PDF is de-identified. |

#### Catch-all override

| Flag                  | Effect                                                                              |
|-----------------------|--------------------------------------------------------------------------------------|
| `-k`, `--key TAG=VALUE` | Same as in `img2dcm` / `dcmodify`. Applied last; wins over everything.            |

### Examples

```bash
# 1. Simplest possible: PDF in, DICOM out. Generates orphan UIDs.
pdf2dcm report.pdf out.dcm

# 2. THE REALISTIC CASE: attach the report to an existing study.
pdf2dcm report.pdf out.dcm \
    --study-from reference.dcm \
    --title "Radiology Report"

# 3. Attach to an existing series (e.g. an addendum to an earlier report).
pdf2dcm report.pdf out.dcm \
    --series-from reference.dcm \
    --instance-inc \
    --title "Addendum 2026-05-25"

# 4. Stand-alone PDF, manually filling patient identity (no template).
pdf2dcm report.pdf out.dcm \
    --patient-name "Doe^Jane" \
    --patient-id  "HN-00012345" \
    --patient-birthdate 19800115 \
    --patient-sex F \
    --title "External Report"

# 5. De-identified handout (you've verified there is no PHI in the PDF).
pdf2dcm handout.pdf out.dcm \
    --study-from reference.dcm \
    --annotation-no \
    --title "Patient Information Handout"

# 6. Force a specific Modality (default is "OT") via -k.
pdf2dcm report.pdf out.dcm \
    --study-from reference.dcm \
    --title "Report" \
    -k "Modality=DOC"

# 7. Same thing but via the modern dcmencap (recommended in 3.7.0+).
dcmencap report.pdf out.dcm --filetype-pdf \
    --study-from reference.dcm \
    --title "Radiology Report"
```

### Gotchas

- **PDF size.** DCMTK has no hard limit — the file is read into memory and
  written verbatim. Practical limits are imposed by the receiving PACS: most
  reject `EncapsulatedDocument` payloads over **~100 MB**, and many cap
  silently around 50 MB. If you have a huge report, split or downsample
  before wrapping.
- **Encrypted / password-protected PDFs.** DCMTK doesn't care — it stores the
  bytes as-is. The PDF stays encrypted inside DICOM. Most PACS report viewers
  will fail to render it. Decrypt first if you want it viewable.
- **`Modality` defaults to `OT`** (Other). Some PACS/RIS prefer `DOC` for
  documents; set it explicitly with `-k "Modality=DOC"` if you need it.
- **MIME type.** `dcmencap` sets `MIMETypeOfEncapsulatedDocument` to
  `application/pdf` for PDF input. Don't override it with `-k` unless you
  know what you're doing — some viewers route on MIME.
- **`pdf2dcm` deprecation banner** is harmless but pollutes script logs. Use
  `dcmencap` instead, or redirect stderr.

---

## `dcm2pdf` — extract a PDF out of a DICOM Encapsulated PDF object

> **In DCMTK 3.7.0 this tool prints a deprecation banner and forwards to
> `dcmdecap`.** Same flags either way. `dcmdecap` additionally handles CDA,
> STL, MTL, and OBJ encapsulated documents.

### Synopsis

```
dcm2pdf  [options] dcmfile-in  pdffile-out
dcmdecap [options] dcmfile-in  encfile-out
```

`-` for either filename means stdin/stdout — handy for pipelines.

### Essential flags

It's almost entirely shared options. The only tool-specific knob is:

| Flag                       | Effect                                                                                   |
|----------------------------|------------------------------------------------------------------------------------------|
| `-x`, `--exec COMMAND`     | Execute `COMMAND` after writing the PDF. `#f` in `COMMAND` is replaced with the output filename. Useful for "extract and open in viewer" one-liners. |

Everything else is the standard DCMTK input-side stack — see
[common-options.md](common-options.md):

- **Input file format:** `+f`, `+fo`, `-f`
- **Input transfer syntax:** `-t=`, `-td`, `-te`, `-tb`, `-ti`
- **Odd-length tolerance:** `+ao`, `+ae`
- **UN handling:** `+ui` / `-ui`, `+uc` / `-uc`
- **Auto-correction:** `+dc` / `-dc`
- **Deflated bitstream:** `+bd` / `+bz` (only relevant if the encapsulated
  payload was deflate-compressed inside the DICOM stream — uncommon for PDF).

### Examples

```bash
# 1. The 99% case.
dcm2pdf input.dcm out.pdf

# 2. Extract and open it immediately (macOS).
dcm2pdf input.dcm out.pdf --exec "open #f"

# 3. Extract via the modern dcmdecap.
dcmdecap input.dcm out.pdf

# 4. Pull a PDF out of a non-conformant DICOM that has no file meta header.
dcm2pdf input.dcm out.pdf --read-dataset

# 5. Pipe via stdin/stdout — extract from a network stream, gzip on the fly.
cat input.dcm | dcm2pdf - - | gzip > out.pdf.gz
```

### Gotchas

- **Only works on Encapsulated PDF Storage** (SOP Class UID
  `1.2.840.10008.5.1.4.1.1.104.1`). If you point it at any other SOP class,
  it errors out. Check with:

  ```bash
  dcmdump +P "SOPClassUID" input.dcm
  ```

- **CDA / STL / OBJ.** `dcm2pdf` will not extract these (it's PDF-only).
  Use `dcmdecap` — it sniffs `MIMETypeOfEncapsulatedDocument` and writes the
  raw bytes whatever they are.
- **Output is byte-identical to what was wrapped.** If the original PDF was
  encrypted or had embedded fonts, you get them back unchanged. Hash the
  extracted file against the original to verify lossless round-trip.
- **`--exec` runs through the shell** — don't pass user-controlled filenames
  into it without quoting.

---

## See also

- [common-options.md](common-options.md) — shared CLI conventions.
- `dcmcjpeg`, `dcmdjpeg`, `dcmcjpls`, `dcmcrle` — change the transfer syntax of
  an existing DICOM image (re-encode the pixel data).
- `dump2dcm` / `dcm2xml` — build / inspect templates for `img2dcm
  --dataset-from`.
- `dcmodify` — patch attributes after the fact when `img2dcm -k` isn't
  enough (e.g. editing inside sequences).
- `dcmencap` / `dcmdecap` — the non-deprecated successors to `pdf2dcm` /
  `dcm2pdf`; same flag vocabulary plus CDA / STL / MTL / OBJ.
