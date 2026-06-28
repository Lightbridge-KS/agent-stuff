# DCMTK dcmdata Tools

The `dcmdata` module ships DCMTK's **file-level** tools: everything they do
operates on DICOM objects sitting on local disk, never over the network. Use
them to:

- **Inspect** what's in a file (`dcmdump`, `dcm2json`, `dcm2xml`, `dcmftest`)
- **Modify** attributes in place (`dcmodify`)
- **Convert** between uncompressed transfer syntaxes (`dcmconv`)
- **Round-trip** between DICOM and a textual representation (`dcmdump` ⇄ `dump2dcm`)
- **Encode / decode** RLE-compressed pixel data (`dcmcrle`, `dcmdrle`)
- **Index** a folder of DICOM files into a media-interchange `DICOMDIR` (`dcmgpdir` / `dcmmkdir`)

For anything that goes over a DICOM association (C-STORE, C-FIND, C-MOVE,
C-ECHO, …) reach for the `dcmnet` tools instead (`storescu`, `findscu`,
`movescu`, `echoscu`, etc.). Shared flags — verbosity, input/output file
format, transfer-syntax read/write — are documented once in
[common-options.md](common-options.md); this page covers what's specific to
each `dcmdata` tool.

---

## dcmdump

> Dump a DICOM file's data set to stdout as a human-readable list of tags, VRs and values.

This is the single most-used DCMTK command. Whenever you need to know
"what's actually inside this `.dcm` file", `dcmdump` is the first thing to
reach for.

### Synopsis

```
dcmdump [options] dcmfile-in...
```

`dcmfile-in` may be a single file, a list of files, `-` for stdin, or — with
`+sd` — a directory to scan.

### Output format

Each attribute is printed on its own line:

```
(0010,0010) PN [Doe^John]                                  # 8, 1 PatientName
(0010,0020) LO [PAT-12345]                                 # 10, 1 PatientID
(0008,0016) UI =CTImageStorage                             # 26, 1 SOPClassUID
(7fe0,0010) OW (not loaded)                                # 524288, 1 PixelData
```

Read it like this:

| Column        | Meaning                                                              |
|---------------|----------------------------------------------------------------------|
| `(gggg,eeee)` | DICOM tag (group, element) in hex.                                   |
| `VR`          | Value Representation (PN, LO, UI, …).                                |
| `[value]`     | String values in square brackets.                                    |
| `=Name`       | UI values shown by their dictionary name when known (e.g. `=CTImageStorage`). |
| `(not loaded)`| Pixel Data and other big values aren't fetched by default — see `+M`/`-M`/`+R`. |
| `# N, M`      | Length in bytes (`N`), value multiplicity (`M`).                     |
| `Name`        | Dictionary name of the tag (if known).                               |

Sequences (VR `SQ`) print with an indented body wrapped in `(Sequence with explicit length …)` and `(SequenceDelimitationItem …)` markers.

### Essential flags

| Flag                              | Effect                                                                                  |
|-----------------------------------|-----------------------------------------------------------------------------------------|
| `+sd`, `--scan-directories`       | Treat any directory in `dcmfile-in` as a folder to scan, not as an error.               |
| `+sp PATTERN`, `--scan-pattern`   | Glob pattern within scanned directories (only with `+sd`).                              |
| `+r`,  `--recurse`                | Recurse into subdirectories (default: do not recurse).                                  |
| `+M`,  `--load-all`               | Load very long tag values (incl. PixelData). **Default.**                               |
| `-M`,  `--load-short`             | Skip very long values — print `(not loaded)`. Huge speedup on whole studies.            |
| `+R K`, `--max-read-length K`     | "Long value" threshold in kB (4…4194302, default 4). Tune what `-M` skips.              |
| `+L`,  `--print-all`              | Print long string/text values completely instead of truncating with `…`.                |
| `-L`,  `--print-short`            | Truncate long values (default).                                                         |
| `+T`,  `--print-tree`             | Print the dataset as a simple tree instead of indented blocks.                          |
| `+F`,  `--print-filename`         | Print a banner with the filename before each file (useful with many inputs).            |
| `+Fs`, `--print-file-search`      | Like `+F`, but the banner appears **only** for files that contain a `+P`-searched tag.  |
| `+P TAG`, `--search TAG`          | Print only the named tag (`(gggg,eeee)` or dictionary name). Repeatable. Default: dump everything. |
| `+s`,  `--search-all`             | When searching, return all matches throughout the dataset (incl. inside sequences). Default. |
| `-s`,  `--search-first`           | When searching, only return the first match.                                            |
| `+p`,  `--prepend`                | Prepend the sequence hierarchy to printed tags: `(0040,0275).(0010,0010)`. Only with `+P`. |
| `+E`,  `--ignore-errors`          | Try to keep printing even after a parse error. Pair with `+Ep` (`--ignore-parse-errors`) for very broken files. |
| `+Un`, `--map-uid-names`          | Show known UIDs as `=Name`. Default.                                                    |
| `-Un`, `--no-uid-names`           | Print raw UIDs only.                                                                    |
| `+U8`, `--convert-to-utf8`        | Convert string element values to UTF-8 (respects `(0008,0005) SpecificCharacterSet`).   |
| `+st TAG`, `--stop-after-elem`    | Stop parsing after a given tag.                                                         |
| `+sb TAG`, `--stop-before-elem`   | Stop parsing **before** a given tag (works even if the tag is absent). Great for "just show me the metadata, not the pixels": `+sb PixelData`. |
| `+W DIR`, `--write-pixel DIR`     | Dump Pixel Data bytes to `<DIR>/<auto>.raw` (little-endian) alongside the textual dump. |
| `+C`,  `--print-color`            | Colorize output with ANSI escapes.                                                      |

For input file format (`+f`/`-f`/`+fo`), input transfer syntax (`-t*`), and
log verbosity, see [common-options.md](common-options.md).

### Examples

```bash
# 1) Just dump everything.
dcmdump input.dcm

# 2) Dump but skip Pixel Data — much faster on big studies.
dcmdump +sb PixelData input.dcm

# 3) Print just one attribute (by name or by tag).
dcmdump +P PatientName input.dcm
dcmdump +P "(0010,0010)" input.dcm

# 4) Grep two tags across every .dcm in a tree, with filename headers.
dcmdump +sd +r +Fs +P PatientID +P StudyInstanceUID study/

# 5) Show full values (untruncated) and color the output.
dcmdump +L +C input.dcm | less -R

# 6) Round-trip: dump → edit text → rebuild.
dcmdump input.dcm > input.dump
$EDITOR input.dump
dump2dcm input.dump output.dcm

# 7) Dump piped from stdin (e.g. extracted from a tarball).
tar -xOf archive.tar some/file.dcm | dcmdump -

# 8) Bulk-extract pixel data to .raw files next to the dumps.
mkdir -p raw_out
dcmdump +W raw_out input.dcm > input.txt
```

### Gotchas

- **`+L` is "print long values", not "print long tag names".** Tag names are
  always printed in the trailing comment; `+L` controls value truncation.
- **`+R` is `--max-read-length`, not "recurse".** dcmdump descends into
  sequences automatically — there is no separate "recurse-sequences" flag.
  `+r` is the *directory* recursion flag and only matters with `+sd`.
- **`(not loaded)` does not mean the file is broken.** It means the value was
  larger than `--max-read-length` and was skipped to save memory. Add `+M`
  (already the default) or raise `+R` if you actually need it.
- **`+sd` is required to scan directories.** Without it `dcmdump foo/` errors
  out — passing a directory is otherwise treated as a bad filename.
- **Pixel Data values with `+M` can be huge.** Always pair with `+sb PixelData`
  or `-M` if you only care about metadata.
- **dump2dcm can round-trip dcmdump's *default indented* output**, but **not
  the `+T` tree output.** Don't use `+T` if you plan to feed the dump back
  through dump2dcm.

---

## dcmodify

> Insert, modify, or delete attributes in a DICOM file in place. Supports nested sequence items via tag paths.

`dcmodify` is the workhorse for anonymisation, ad-hoc tag fixes, and
constructing query files for `findscu`/`movescu`. It edits files **in
place** by default (a `.bak` is written next to each input unless you say
otherwise).

### Synopsis

```
dcmodify [options] dcmfile-in...
```

Multiple input files are processed independently — each gets its own
modifications applied and (unless `-nb`) its own backup.

### Tag-path syntax

dcmodify takes paths of the form:

```
{ sequence[item-no]. }* element
```

| Part         | Example            | Meaning                                              |
|--------------|--------------------|------------------------------------------------------|
| `sequence`   | `(0040,0275)` or `RequestAttributesSequence` | A sequence tag.            |
| `item-no`    | `[0]`, `[2]`       | Item index inside that sequence (0-based).           |
| `*` wildcard | `[*]`              | "All items in this sequence" (works with `-i`/`-m`/`-e`). |
| `element`    | `(0010,0010)` or `PatientName` | The leaf attribute to set/insert/erase.  |

Examples:

```
PatientName
(0010,0010)
(0040,0275)[0].(0010,0010)
RequestAttributesSequence[*].ScheduledProcedureStepID
(0040,0275)[0].ReferencedStudySequence[0].SOPInstanceUID
```

When you `-i` (insert) a deep path and some intermediate sequences/items
don't exist yet, dcmodify creates them automatically — except across an
item wildcard with no items present (it can't know how many to create).

### Essential flags

#### Operations

| Flag                         | Effect                                                                                          |
|------------------------------|-------------------------------------------------------------------------------------------------|
| `-i`,  `--insert PATH=VAL`   | Insert (or overwrite) the attribute at `PATH` with `VAL`. Missing intermediate nodes are created. |
| `-if`, `--insert-from-file PATH=FILE` | Same as `-i` but the value is the raw contents of `FILE` (use for `PixelData=pixels.raw`). |
| `-m`,  `--modify PATH=VAL`   | Modify an **existing** attribute. ERROR if the path or leaf is missing (use `-imt` to make that non-fatal). |
| `-mf`, `--modify-from-file PATH=FILE` | Same as `-m` but value from `FILE`.                                                    |
| `-ma`, `--modify-all TAG=VAL`| Modify **every** occurrence of `TAG` in the dataset, including inside every item of every sequence. Tag only — no path, no wildcard. |
| `-e`,  `--erase PATH`        | Delete the attribute / item at `PATH`.                                                          |
| `-ea`, `--erase-all TAG`     | Delete every occurrence of `TAG` throughout the dataset.                                        |
| `-ep`, `--erase-private`     | Delete every private element (odd group number). Standard anonymisation building block.         |

#### UID generation (anonymisation)

| Flag                       | Effect                                                                              |
|----------------------------|-------------------------------------------------------------------------------------|
| `-gst`, `--gen-stud-uid`   | Generate a fresh `StudyInstanceUID` (0020,000D).                                    |
| `-gse`, `--gen-ser-uid`    | Generate a fresh `SeriesInstanceUID` (0020,000E).                                   |
| `-gin`, `--gen-inst-uid`   | Generate a fresh `SOPInstanceUID` (0008,0018). The metaheader `MediaStorageSOPInstanceUID` is also updated automatically (cannot be disabled). |
| `-nmu`, `--no-meta-uid`    | When you `-m`/`-i` `SOPClassUID` or `SOPInstanceUID` in the dataset, do **not** sync the metaheader copies. |

#### File handling

| Flag                       | Effect                                                                              |
|----------------------------|-------------------------------------------------------------------------------------|
| `--backup`                 | Write `<input>.bak` before modifying. **Default.**                                  |
| `-nb`,  `--no-backup`      | Skip the backup. Dangerous on large batches — there is no undo.                     |
| `+fc`,  `--create-file`    | If `dcmfile-in` doesn't exist, create it from scratch (used for building query files). Output is always Part-10 file format with explicit-VR LE when creating new. |

#### Error tolerance

| Flag                       | Effect                                                                              |
|----------------------------|-------------------------------------------------------------------------------------|
| `-ie`,  `--ignore-errors`  | If a modify op fails on one file, still try the next file (and still save the current one if it had any successful ops). |
| `-imt`, `--ignore-missing-tags` | Treat "tag not found" as success for `-m`/`-e`. Idempotency-friendly.          |
| `-iun`, `--ignore-un-values` | Don't write values into elements whose VR is UN (i.e. private tags not in your dictionary). |
| `-nrc`, `--no-reserv-check`| When inserting a private tag, skip the check that a matching reservation `(gggg,00xx)` exists. The inserted tag's VR becomes UN. |

For input/output transfer syntax see [common-options.md](common-options.md);
dcmodify also accepts `+t*` to re-encode on save (default: write same TS as
input).

### Examples

```bash
# 1) Change PatientName in place (a .bak is written automatically).
dcmodify -m "PatientName=Anon^Patient" input.dcm

# 2) Insert PatientName only if it isn't already there (use -i; -m would
#    error if the tag is missing). -i also overwrites if present.
dcmodify -i "(0010,0010)=Anon^Patient" input.dcm

# 3) Edit a nested attribute inside the first item of a sequence.
dcmodify -m "(0040,0275)[0].(0010,0010)=Anon^Patient" input.dcm

# 4) Wipe one tag from every item of a sequence using the item wildcard.
dcmodify -e "RequestAttributesSequence[*].ScheduledProcedureStepID" input.dcm

# 5) Common "lightweight anonymisation" recipe.
dcmodify \
  -m "PatientName=ANON" \
  -m "PatientID=ANON-001" \
  -m "PatientBirthDate=19000101" \
  -ep \
  -gst -gse -gin \
  -nb \
  study/*.dcm

# 6) Erase a tag everywhere it appears, tolerating files where it's missing.
dcmodify -ea "(0010,1000)" -imt -ie study/*.dcm

# 7) Build a C-FIND query file from scratch (no input file exists).
dcmodify +fc \
  -i "QueryRetrieveLevel=STUDY" \
  -i "PatientID=PAT-12345" \
  -i "StudyDate=20240101-" \
  query.dcm

# 8) Insert PixelData from a raw binary file.
dcmodify -if "PixelData=pixels.raw" input.dcm

# 9) Edit and simultaneously re-encode to explicit VR LE.
dcmodify -m "PatientName=ANON" +te input.dcm
```

### Gotchas

- **`-i` vs `-m`.** `-i` inserts-or-overwrites and silently creates missing
  intermediate nodes; `-m` only modifies and errors if anything along the
  path is missing. Pick `-i` when you're "ensuring" a value, `-m` when you
  expect it to be there.
- **`-ma` is tag-only, not path-aware.** It walks the whole dataset
  modifying every occurrence of the tag. It does not accept paths or
  wildcards — those belong to `-i`/`-m`/`-e`.
- **`.bak` files litter the filesystem.** `dcmodify -m … *.dcm` on a study
  of 1000 slices produces 1000 `.bak` files. Use `-nb` once you trust the
  command — but always test on one file first.
- **In-place only.** Unlike most DCMTK tools, dcmodify has **no
  `--output-file` flag**. If you need the original untouched, copy it
  yourself first (or rely on `.bak`, but be aware of the size cost).
- **UIDs aren't auto-cascaded.** `-gst` only regenerates `StudyInstanceUID`.
  If you want a fully fresh study identity, pass all three: `-gst -gse -gin`.
  Note that with multiple input files, dcmodify generates a **different**
  new UID for each file — so passing `-gst study/*.dcm` gives every slice
  its own Study UID, which is almost never what you want. To assign one
  shared new UID, generate it once (`uuidgen` / `dcmuidgen`) and use
  `-m StudyInstanceUID=…` instead.
- **Metaheader UIDs auto-sync.** Modifying `SOPClassUID` or `SOPInstanceUID`
  in the dataset also rewrites the matching metaheader tags. Disable with
  `-nmu` if you have a specific reason.
- **Private tags need a reservation.** Inserting `(0029,1000)` requires a
  `(0029,0010)` reservation in the same dataset (with a matching private
  creator string). Use `-nrc` to bypass, accepting that the tag will be
  stored as VR=UN.

---

## dcmconv

> Convert a DICOM file between uncompressed transfer syntaxes, or between file/dataset formats. Does NOT compress or decompress pixel data.

### Synopsis

```
dcmconv [options] dcmfile-in dcmfile-out
```

### What it can do

- Change byte order: implicit-VR LE ↔ explicit-VR LE ↔ explicit-VR BE.
- Toggle Part-10 file meta header on or off (`+F`/`-F`/`+Fm`).
- Re-encode to deflated explicit-VR LE (`+td`, needs zlib).
- Convert string values to UTF-8 / Latin-1 / ASCII / arbitrary charset
  (`+U8`, `+L1`, `+A7`, `+C`).
- Strip private elements with invalid groups (`-ig`).
- Apply various data-correction repairs while parsing (see input options).

### What it CANNOT do

- **Compress** to JPEG / JPEG-LS / JPEG 2000 / RLE — use `dcmcjpeg`,
  `dcmcjpls`, `dcmcjp2k`, `dcmcrle`.
- **Decompress** the above — use `dcmdjpeg`, `dcmdjpls`, `dcmdjp2k`,
  `dcmdrle`.

If you pass a JPEG-compressed file to `dcmconv` and ask for `+te`, it will
refuse: the encapsulated pixel data is already in a non-uncompressed
transfer syntax and can't be re-wrapped as little-endian.

### Essential flags

| Flag                             | Effect                                                                  |
|----------------------------------|-------------------------------------------------------------------------|
| `+t=`, `--write-xfer-same`       | Keep input TS. **Default.**                                             |
| `+te`/`+tb`/`+ti`                | Re-encode to explicit-LE / explicit-BE / implicit-LE.                   |
| `+td`, `--write-xfer-deflated`   | Deflated explicit-VR LE. Needs zlib.                                    |
| `+tg`, `--write-xfer-ge`         | Non-standard "private GE" implicit-VR LE with big-endian pixel data — niche legacy interop. |
| `+Fm`, `--write-new-meta-info`   | Write the output with a freshly built file meta header. **Default.**    |
| `+F`,  `--write-file`            | Write Part-10 file format (preserve original meta header where possible). |
| `-F`,  `--write-dataset`         | Strip the file meta header.                                             |
| `+U8`, `--convert-to-utf8`       | Convert affected string values to UTF-8 (and update `SpecificCharacterSet`). |
| `+L1`, `+A7`, `+C CHARSET`       | Same idea, but to Latin-1, 7-bit ASCII, or any DICOM defined term.      |
| `-Ct`, `--transliterate`         | Approximate untranslatable characters with similar-looking ones.        |
| `-Cd`, `--discard-illegal`       | Drop characters that can't be encoded in the destination charset.       |
| `-ig`, `--no-invalid-groups`     | Drop elements whose group number is invalid (0, 1, 2 outside meta).     |
| `-eo`, `--abort-oversized`       | Abort on oversized explicit-length sequences/items instead of switching to undefined length. |
| `+cl L`, `--compression-level L` | Deflate compression level 0–9 (default 6). Only with `+td`.             |

### Examples

```bash
# 1) Re-encode implicit-VR LE → explicit-VR LE (very common).
dcmconv +te input.dcm output.dcm

# 2) Strip the Part-10 meta header (produce a raw dataset).
dcmconv -F input.dcm dataset.dcm

# 3) Convert character encoding from Latin-1 to UTF-8.
dcmconv +U8 input.dcm output_utf8.dcm

# 4) Squeeze a file with deflate (great for archival of metadata-only files).
dcmconv +td +cl 9 input.dcm output.dcm.deflated

# 5) Pipe out to stdout, e.g. for inline processing.
dcmconv +te input.dcm - | dcmdump -
```

### Gotchas

- **Not a codec tool.** If `dcmconv +te` fails with "Cannot change to little
  endian explicit", the file is JPEG/JPEG-LS/RLE-encoded. Decompress first
  with the matching `dcmd*` tool.
- **The output transfer syntax is unchanged by default.** `dcmconv in.dcm
  out.dcm` produces a byte-for-byte-equivalent copy under most
  circumstances. Add `+te`/`+tb`/`+ti`/`+td` to actually transcode.
- **Character-set conversion is a separate axis** from transfer syntax.
  `+U8` updates `SpecificCharacterSet` and the affected element values but
  doesn't touch byte order; combine with `+te` if you want both.

---

## dcm2json

> Convert a DICOM file to DICOM JSON Model (PS3.18 Annex F).

The DICOM JSON Model is the canonical JSON representation used by DICOMweb
services (QIDO-RS, WADO-RS metadata). Each attribute becomes an object
keyed by its 8-hex-digit tag, with `vr`, `Value` (an array), and — for
binary values — either `InlineBinary` (base64) or `BulkDataURI`.

### Synopsis

```
dcm2json [options] dcmfile-in [jsonfile-out]
```

Omitting `jsonfile-out` writes to stdout.

### Example output

```json
{
  "00100010": {
    "vr": "PN",
    "Value": [ { "Alphabetic": "Doe^John" } ]
  },
  "00100020": {
    "vr": "LO",
    "Value": [ "PAT-12345" ]
  },
  "00080060": {
    "vr": "CS",
    "Value": [ "CT" ]
  }
}
```

### Essential flags

| Flag                                | Effect                                                                              |
|-------------------------------------|-------------------------------------------------------------------------------------|
| `+fc`, `--formatted-code`           | Pretty-print with indentation and newlines. **Default.**                            |
| `-fc`, `--compact-code`             | Minified output (one long line) — best for piping to `jq` or storing compactly.     |
| `+m`,  `--write-meta`               | Include the file meta header (group 0002) in the JSON. **Non-conforming to PS3.18** — use only for debugging. |
| `-ee`, `--encode-extended`          | Permit `inf` / `nan` in numeric values. Strict (default) reports an error instead.  |
| `-ia` / `-in` / `-is`               | IS / DS encoding mode: auto (default), always number (fail if invalid), always string. |
| `-b`,  `--bulk-disabled`            | Inline every binary value as base64 (`InlineBinary`). **Default.**                  |
| `+b`,  `--bulk-enabled`             | Write large attributes as `BulkDataURI` references to separate files.               |
| `+bz S`, `--bulk-size S`            | Cut-off threshold in kB for "large" (default 1).                                    |
| `+bp URI`, `--bulk-uri-prefix URI`  | Prefix used when generating bulk URIs (default: a local `file://` URI). Use the URI of your WADO-RS endpoint in production. |
| `+bd DIR`, `--bulk-dir DIR`         | Directory the bulk files are written into (default `.`).                            |
| `+bs`, `--bulk-subdir`              | Create a subdirectory per SOP instance under `+bd`. Keeps things tidy.              |

### Examples

```bash
# 1) Pretty-printed JSON to stdout.
dcm2json input.dcm

# 2) Compact JSON, piped through jq for a single attribute.
dcm2json -fc input.dcm | jq '."00100010"'

# 3) Externalise binary blobs (Pixel Data, private OBs) as BulkDataURIs
#    pointing at sibling files in ./bulk/.
mkdir -p bulk
dcm2json +b +bd bulk +bp "https://example.org/wado/bulk/" \
  input.dcm output.json

# 4) Write JSON straight to a file.
dcm2json input.dcm output.json
```

### Gotchas

- **`+fc` and `-fc` are the actual flag names** (formatted-code /
  compact-code). They are not `+fp` / `--format-pretty`.
- **`+m` (write-meta) breaks the standard.** It includes group 0002, which
  the JSON Model explicitly excludes. Don't use for interchange — only for
  ad-hoc debugging.
- **Encapsulated multi-frame pixel data isn't representable** in DICOM JSON
  Model at all; `dcm2json` errors out on those files. Decompress first if
  you need JSON.
- **The default file-URI bulk prefix is rarely what you want.** Always set
  `+bp` to your actual WADO-RS bulk endpoint when generating JSON for
  external consumption.
- **UTF-8 only.** Output is always UTF-8, regardless of the input's
  `SpecificCharacterSet`. DCMTK needs character-set conversion support
  (`oficonv`) compiled in.

---

## dcm2xml

> Convert a DICOM file to XML, either DCMTK's own format or the standard "Native DICOM Model" (PS3.19).

### Synopsis

```
dcm2xml [options] dcmfile-in [xmlfile-out]
```

### Two output formats

| Format            | Flag    | When to use                                                |
|-------------------|---------|------------------------------------------------------------|
| DCMTK-specific    | `-dtk` (default) | Easier to read/script. Has a DTD shipped at `<datadir>/dcm2xml.dtd`. |
| Native DICOM Model | `-nat` | Standards-compliant (PS3.19 / DICOM Application Hosting). Required if a downstream consumer expects it. |

### Essential flags

| Flag                          | Effect                                                                          |
|-------------------------------|---------------------------------------------------------------------------------|
| `-dtk`, `--dcmtk-format`      | DCMTK's XML layout. **Default.**                                                |
| `-nat`, `--native-format`     | Native DICOM Model layout (PS3.19).                                             |
| `+Xn`,  `--use-xml-namespace` | Add the XML namespace declaration to the root element.                          |
| `+Xd`,  `--add-dtd-reference` | Add a `<!DOCTYPE … SYSTEM "dcm2xml.dtd">` reference (DCMTK format only).        |
| `+Xe`,  `--embed-dtd-content` | Inline the DTD content (DCMTK format only).                                     |
| `-Wn`,  `--no-element-name`   | Omit the human-readable element name attribute (DCMTK format only).             |
| `+Wb`,  `--write-binary-data` | Write OB/OW values into the XML. **Off by default** — pair carefully with `+M`. |
| `+Eh` / `+Eu` / `+Eb`         | Binary encoding: hex (default for DCMTK), UUID reference (default for Native), or Base64. |
| `+U8`,  `--convert-to-utf8`   | Convert all string values to UTF-8 (recommended for downstream XML parsers).    |
| `+Ca CHARSET`, `--charset-assume` | If the input has no `SpecificCharacterSet`, assume `CHARSET`.               |
| `+M` / `-M` / `+R K`          | Same big-value loading semantics as `dcmdump`.                                  |

### Examples

```bash
# 1) Default DCMTK XML to stdout.
dcm2xml input.dcm

# 2) Standard Native DICOM Model, UTF-8 converted, written to file.
dcm2xml -nat +U8 input.dcm output.xml

# 3) DCMTK format with embedded DTD and Base64 binary values.
dcm2xml +Xe +Wb +Eb input.dcm output.xml
```

### Gotchas

- **By default binary data is omitted**, replaced with a `binary="hidden"`
  attribute. Use `+Wb` to include it — and `+M` to also load Pixel Data
  before you do, otherwise it stays "(not loaded)".
- **Native DICOM Model produces UUID-keyed `<BulkData>` placeholders** for
  binary values; there's no built-in mechanism to also dump those bulk
  blobs to files. Implement that on top if needed.
- **Multi-charset DICOM files (code extensions)** are not supported. Use
  `+U8` to flatten everything to UTF-8 first.

---

## dump2dcm

> Inverse of dcmdump: parse a textual dump back into a DICOM file.

Lets you round-trip "dump → edit text → rebuild" for any small-scale change
that's awkward to express in `dcmodify` syntax, or for hand-authoring tiny
test fixtures.

### Synopsis

```
dump2dcm [options] dumpfile-in dcmfile-out
```

### Dump-file syntax (cheat sheet)

```
(0008,0020) DA [19921012]            # comment OK after a '#'
(0008,0016) UI =MRImageStorage       # =Name resolves UID via the dictionary
(0010,0010) PN [Doe^John]
(0018,1310) US 256\256\0\0           # VM > 1, backslash-separated
(0028,0009) AT (3004,000c)           # AT values use (gggg,eeee) form
(0002,0001) OB 01\00                 # OB hex bytes, '\'-separated
(7fe0,0010) OB =pixels.raw           # OB / OW from external file
```

- One element per line.
- `[ … ]` for textual values (PN, LO, LT, etc.).
- `=Name` for UI tags (resolved via dictionary).
- `=filename` for OB/OW to pull bytes from disk.
- `# …` is a comment; blank lines are fine; lines need not be sorted by tag.
- VR is optional **if the tag is in the dictionary**.

### Essential flags

| Flag                            | Effect                                                                             |
|---------------------------------|------------------------------------------------------------------------------------|
| `+f`,  `--read-meta-info`       | Honour `(0002,xxxx)` meta-header elements in the dump if present. **Default.**     |
| `-f`,  `--ignore-meta-info`     | Ignore them and let dump2dcm build a fresh meta header.                            |
| `+l N`, `--line N`              | Maximum line length to accept (default 4096). Bump if you have huge values inline. |
| `+Ug`, `--generate-new-uids`    | Generate a fresh Study/Series/SOPInstanceUID set on output.                        |
| `+Uo`, `--overwrite-uids`       | When `+Ug` is set, overwrite UIDs that were already present in the dump.           |
| `+Fu`, `--update-meta-info`     | Update specific meta-header fields based on the dataset.                           |
| `+E`,  `--ignore-errors`        | Try to write even if the dump has syntactic problems.                              |
| `+t=`/`+te`/`+tb`/`+ti`/`+td`   | Output transfer syntax (default: same as declared in the dump's meta header).      |

### Examples

```bash
# 1) Edit-in-place workflow.
dcmdump input.dcm > input.dump
$EDITOR input.dump
dump2dcm input.dump output.dcm

# 2) Hand-author a tiny fixture file from scratch.
cat > fixture.dump <<'EOF'
(0008,0016) UI =SecondaryCaptureImageStorage
(0008,0018) UI [1.2.826.0.1.3680043.8.498.1]
(0010,0010) PN [Test^Patient]
(0010,0020) LO [TEST-001]
(0020,000d) UI [1.2.826.0.1.3680043.8.498.2]
(0020,000e) UI [1.2.826.0.1.3680043.8.498.3]
EOF
dump2dcm +Ug fixture.dump fixture.dcm

# 3) Edit the dump but regenerate UIDs on save.
dump2dcm +Ug +Uo input.dump output.dcm

# 4) Pull large binary data in from a sidecar file (referenced as =pixels.raw
#    in the dump itself).
dump2dcm input.dump output.dcm
```

### Gotchas

- **Only the default indented dcmdump output is supported.** dump2dcm
  cannot read `dcmdump +T` (tree) output.
- **Comments aren't preserved across a round-trip.** dcmdump produces
  `# length, vm  Name` annotations, but dump2dcm just discards them.
- **No DICOMDIR support.** dump2dcm won't update the offset elements that
  make a DICOMDIR valid. Build DICOMDIRs with `dcmgpdir`/`dcmmkdir`.
- **OB/OW values must be even-length bytes**, with no automatic padding.
  Bring your own padding byte if you're hand-authoring.

---

## dcmftest

> One-shot check: does a file have the DICOM Part-10 magic word `DICM` at byte 128?

### Synopsis

```
dcmftest file...
```

No options. For each input it prints one of:

```
yes: <filename>
no: <filename>
```

The exit code equals the number of files that came back `no` — so an exit
code of 0 means every file passed.

### Examples

```bash
# 1) Check one file.
dcmftest input.dcm

# 2) Use in a shell guard.
if dcmftest input.dcm > /dev/null; then
  echo "Valid Part-10 file."
else
  echo "Missing or wrong meta header."
fi

# 3) Find every "DICOM-looking" file in a tree.
fd -t f . study/ | xargs dcmftest | awk -F': ' '$1=="yes" { print $2 }'
```

### Gotchas

- **It only checks the magic word.** A `yes` doesn't mean the dataset
  parses, only that the file has the right preamble. For a stricter check
  follow up with `dcmdump +fo input.dcm`.
- **Raw datasets (no meta header) always report `no`.** That's the intended
  meaning, not a bug. To validate a raw dataset, force `dcmdump -f`.
- **The exit code is the count of failures**, not 0/1. If you pass 50 files
  and 3 fail, exit code is 3. Useful in scripts; surprising at first.

---

## dcmgpdir (alias dcmmkdir)

> Build a DICOMDIR — the index file that DICOM Part-10 media (CD, DVD, USB) require alongside their `.dcm` files.

`dcmgpdir` is a deprecated alias for `dcmmkdir`. New scripts should call
`dcmmkdir`; the option set is identical.

A DICOMDIR is a small DICOM-formatted file (literally named `DICOMDIR`,
no extension) that lives at the root of a media set and indexes every
referenced instance under a Patient → Study → Series → Instance hierarchy.
Without it, conforming media-interchange viewers won't see your files.

### Synopsis

```
dcmmkdir [options] [dcmfile-in...]
```

Pass either explicit file paths or — with `+r` — a directory to scan.

### Essential flags

#### Identifiers

| Flag                          | Effect                                                                          |
|-------------------------------|---------------------------------------------------------------------------------|
| `+F ID`, `--fileset-id ID`    | File-set ID written into the DICOMDIR (default `DCMTK_MEDIA_DEMO`; `""` for none). |
| `+R FILE`, `--descriptor FILE`| Add a file-set descriptor file ID (e.g. `README`).                              |
| `+C CHARSET`, `--char-set CHARSET` | Character set of the descriptor (default `ISO_IR 100` if a descriptor is present). |

#### Reading

| Flag                          | Effect                                                                          |
|-------------------------------|---------------------------------------------------------------------------------|
| `+id DIR`, `--input-directory DIR` | Look up referenced files relative to `DIR`. **Required for `+r`** (default: current dir). |
| `+r`,  `--recurse`            | Recurse into subdirectories of the scanned directory.                           |
| `-r`,  `--no-recurse`         | Don't recurse. **Default.**                                                     |
| `+p PATTERN`, `--pattern PATTERN` | Glob pattern for files within scanned dirs (only with `+r`).                |
| `-m`,  `--keep-filenames`     | Expect filenames already in DICOM media format (8.3, uppercase). **Default.**   |
| `+m`,  `--map-filenames`      | Map filenames to DICOM media format (uppercase, strip trailing `.`).            |

#### Profiles (which DICOMDIR is produced)

| Flag                          | Profile                                                                          |
|-------------------------------|----------------------------------------------------------------------------------|
| `-Pgp`, `--general-purpose`   | General Purpose Interchange on CD/DVD/BD (`STD-GEN-…`). **Default.**             |
| `-Pmi`, `--general-mime`      | General Purpose MIME Interchange (`STD-GEN-MIME`). Looser TS constraints.        |
| `-Pdv`/`-Pd2`/`-Pbd`/`-Pb2`   | DVD/BD with JPEG / JPEG 2000.                                                    |
| `-Pfl`/`-Pf2`                 | USB / flash interchange with JPEG / JPEG 2000.                                   |
| `-Pmp`/`-Pbm`/`-Pbh`/…        | MPEG video profiles.                                                             |
| `-Pbc`/`-Pxa`/`-Pxd`/`-Pde`/`-Pcm`/`-Pus`/`-Pum`/`-Pec`/`-Phd` | Specialised profiles for Cardiac XA, Dental, CT/MR, Ultrasound, ECG, hemodynamics. |

#### Consistency / type-1 handling

| Flag                              | Effect                                                                       |
|-----------------------------------|------------------------------------------------------------------------------|
| `+W`,  `--warn-inconsist-files`   | Warn but continue on inconsistencies between files. **Default.**             |
| `-W`,  `--no-consistency-check`   | Skip the check entirely.                                                     |
| `-a`,  `--abort-inconsist-file`   | Abort on the first inconsistency.                                            |
| `-I`,  `--strict`                 | Error out if a DICOMDIR type-1 attribute is missing. **Default.**            |
| `+I`,  `--invent`                 | Invent placeholder values for missing type-1 attributes.                     |
| `+Ipi`, `--invent-patient-id`     | Invent a new PatientID when PatientName matches across patients.             |
| `+Nrs`, `--allow-retired-sop`     | Allow SOP classes retired in earlier editions of the standard.               |
| `-Nxc`, `--no-xfer-check`         | Don't reject files with non-standard TS (just warn).                         |
| `-Nec`, `--no-encoding-check`     | Don't reject non-standard pixel encodings (just warn).                       |
| `-Nrc`, `--no-resolution-check`   | Don't reject non-standard spatial resolutions (just warn).                   |

#### Writing

| Flag                          | Effect                                                                           |
|-------------------------------|----------------------------------------------------------------------------------|
| `+D FILE`, `--output-file FILE` | Path of the generated DICOMDIR (default: `./DICOMDIR`).                        |
| `-A`, `--replace`             | Replace an existing DICOMDIR. **Default.**                                       |
| `+A`, `--append`              | Append to an existing DICOMDIR.                                                  |
| `+U`, `--update`              | Update an existing DICOMDIR with the listed files.                               |
| `-w`, `--discard`             | Parse and validate but don't actually write — use to "lint" a media set.         |
| `-nb`, `--no-backup`          | Skip the `DICOMDIR.bak` written before replacement.                              |

#### Icon images

| Flag                          | Effect                                                                           |
|-------------------------------|----------------------------------------------------------------------------------|
| `+X`,  `--add-icon-image`     | Add a monochrome icon to each IMAGE record (default for cardiac profiles).       |
| `-Xs N`, `--icon-image-size N`| Icon side length (1–128). Fixed at 128 for XA, 64 for CT/MR.                     |
| `-Xi PFX`, `--icon-file-prefix PFX` | Use `PFX+<filename>` PGM as the icon instead of rendering one.             |
| `-Xd FILE`, `--default-icon FILE`   | Fallback icon if rendering fails (default: a black image).                 |

### Examples

```bash
# 1) Build a DICOMDIR in ./study/ for everything under ./study/.
cd study/
dcmmkdir +r +id . *

# 2) Equivalent, run from elsewhere, with an explicit output path.
dcmmkdir +r +id study/ +D study/DICOMDIR study/*

# 3) Permissive build: don't reject odd TS, invent missing type-1 attrs,
#    keep going on inconsistencies. Useful for messy real-world data.
dcmmkdir +r +id study/ +I -Nxc -Nec -Nrc +W study/*

# 4) Use the MIME profile (no strict TS constraints).
dcmmkdir -Pmi +r +id study/ study/*

# 5) Lint a media set without writing the DICOMDIR.
dcmmkdir -w +r +id media/ media/*

# 6) Update an existing DICOMDIR with one extra series.
dcmmkdir +U +id study/ study/new_series/*
```

### Gotchas

- **The default profile insists on a media-friendly transfer syntax.** With
  `-Pgp` the only uncompressed TS permitted is implicit-VR LE (1.2.840.10008.1.2);
  explicit-VR LE files will be rejected. Either transcode the inputs with
  `dcmconv +ti`, switch profiles (`-Pmi` is the most permissive), or pass
  `-Nxc` to downgrade the rejection to a warning.
- **Strict mode aborts on the first missing type-1 attribute** (e.g. a
  missing `PatientID`). `+I` is almost always what you want when wrangling
  real-world data; combine with `+Ipi` when two patients share a name.
- **`+id` is required if you pass a directory rather than file names.**
  Without it, dcmmkdir tries to interpret each directory entry as a file
  literal.
- **Filenames must be DICOM-media-conformant** (8 chars + `.` + 3 chars,
  uppercase letters / digits / `_`) for the resulting media to be
  fully-conformant — use `+m` to auto-map if you started from arbitrary
  filenames.
- **`dcmgpdir` is just a thin alias** kept for back-compat. Prefer
  `dcmmkdir` in new scripts and docs.

---

## dcmcrle

> Encode an uncompressed DICOM file to RLE Lossless (TS UID 1.2.840.10008.1.2.5).

RLE Lossless is the simplest compressed TS in DICOM — useful when you
need *some* size reduction without the implementation overhead of JPEG-LS
or JPEG 2000, and you absolutely need lossless.

### Synopsis

```
dcmcrle [options] dcmfile-in dcmfile-out
```

### Supported transfer syntaxes

| Direction | UIDs                                                                                  |
|-----------|---------------------------------------------------------------------------------------|
| Input     | Implicit VR LE, Explicit VR LE, Explicit VR BE, Deflated Explicit VR LE (if zlib).   |
| Output    | RLE Lossless (`1.2.840.10008.1.2.5`).                                                |

### Essential flags

| Flag                          | Effect                                                                          |
|-------------------------------|---------------------------------------------------------------------------------|
| `+ff`, `--fragment-per-frame` | Encode each frame as a single fragment. **Default — DICOM-conformant.**         |
| `+fs S`, `--fragment-size S`  | Cap each fragment at `S` kB. **Non-standard** — only do this if you know the receiver tolerates it. |
| `+ot`, `--offset-table-create`| Build the Basic Offset Table. **Default.**                                      |
| `-ot`, `--offset-table-empty` | Leave the offset table empty (smaller output, less random-frame-access).        |
| `+cd`, `--class-default`      | Keep the original SOP Class UID. **Default.**                                   |
| `+cs`, `--class-sc`           | Convert to Secondary Capture Image Storage (implies new SOP Instance UID).      |
| `+un`, `--uid-never`          | Keep the existing SOP Instance UID. **Default.**                                |
| `+ua`, `--uid-always`         | Always assign a fresh SOP Instance UID. Strongly recommended whenever you create a lossy/lossless variant of an existing instance. |

### Examples

```bash
# 1) Plain RLE encode.
dcmcrle input.dcm output.dcm

# 2) Encode and rebrand as a Secondary Capture (e.g. derived screenshot).
dcmcrle +cs input.dcm derived.dcm

# 3) Encode preserving original UIDs but verbose so you can see what happened.
dcmcrle -v input.dcm output.dcm

# 4) Batch-encode every file in a directory in parallel.
fd -e dcm . study/ | xargs -P 4 -I{} dcmcrle {} {}.rle && \
  fd -e dcm.rle . study/ | xargs -I{} mv {} "$(dirname {})/$(basename {} .dcm.rle).dcm"
```

### Gotchas

- **Don't keep the old SOP Instance UID** when emitting a derived,
  re-encoded copy — even though RLE is lossless. The output is a new
  *instance* of the same image; downstream systems use the SOP Instance
  UID as a unique identity key. Use `+ua` (or generate UIDs yourself).
- **`+fs` produces non-conformant files.** The DICOM standard explicitly
  forbids multiple fragments per frame for RLE. Avoid unless interoperating
  with a very specific receiver.
- **Compression ratios are modest.** RLE shines for synthetic / overlay
  images with long runs of identical pixels; for typical CT/MR data,
  JPEG-LS or JPEG 2000 Lossless compress far better.

---

## dcmdrle

> Decode an RLE-compressed DICOM file back to an uncompressed transfer syntax.

The inverse of `dcmcrle`. Used whenever an upstream system gives you RLE
data and your downstream tool doesn't speak it.

### Synopsis

```
dcmdrle [options] dcmfile-in dcmfile-out
```

### Supported transfer syntaxes

| Direction | UIDs                                                                                  |
|-----------|---------------------------------------------------------------------------------------|
| Input     | Implicit VR LE, Explicit VR LE, Explicit VR BE, Deflated Explicit VR LE (if zlib), **RLE Lossless**. |
| Output    | Implicit VR LE, Explicit VR LE, Explicit VR BE.                                       |

`dcmdrle` accepts uncompressed inputs too — it just passes them through.

### Essential flags

| Flag                            | Effect                                                                        |
|---------------------------------|-------------------------------------------------------------------------------|
| `+te`, `--write-xfer-little`    | Output explicit-VR LE. **Default.**                                           |
| `+tb`, `--write-xfer-big`       | Output explicit-VR BE.                                                        |
| `+ti`, `--write-xfer-implicit`  | Output implicit-VR LE (mandatory for media-interchange DICOMDIRs).            |
| `+ud`, `--uid-default`          | Keep the same SOP Instance UID. **Default.**                                  |
| `+ua`, `--uid-always`           | Assign a fresh SOP Instance UID. Recommended when downstream systems treat the decoded file as a new instance. |
| `+bd`, `--byte-order-default`   | RLE byte segment order: most-significant byte first. **Default.**             |
| `+br`, `--byte-order-reverse`   | LSB-first segment order — workaround for encoders that got it wrong.          |

### Examples

```bash
# 1) Decode to explicit-VR LE (default).
dcmdrle input.dcm output.dcm

# 2) Decode for inclusion in a CD/DVD DICOMDIR (needs implicit-VR LE).
dcmdrle +ti input.dcm output.dcm

# 3) Batch-decode a directory.
mkdir -p decoded
for f in study/*.dcm; do
  dcmdrle "$f" "decoded/$(basename "$f")"
done

# 4) Decode a file whose RLE byte segment order was wrongly encoded.
dcmdrle +br broken.dcm fixed.dcm
```

### Gotchas

- **`+ud` keeps the SOP Instance UID** — fine for archival round-trips, but
  if you're going to *store* the decoded copy alongside the original you
  almost certainly want `+ua` (and probably new Series/Study UIDs too, via
  `dcmodify -gse -gst` afterwards).
- **For DICOMDIR-bound media use `+ti`.** The general-purpose DICOMDIR
  profile only accepts implicit-VR LE among uncompressed TSes; default
  `+te` will get the file rejected by `dcmmkdir -Pgp`.
- **`+br` is a corrective measure, not a normal flag.** Default `+bd` is
  correct for any RLE encoder that follows the standard. Reach for `+br`
  only when you see scrambled multi-byte pixel values after decoding with
  the default.
