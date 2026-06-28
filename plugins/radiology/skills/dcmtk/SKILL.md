---
name: dcmtk
description: "Reference for the DCMTK (OFFIS DICOM Toolkit) command-line tools — the canonical CLI for working with DICOM files and DIMSE network services. Use when converting, dumping, anonymizing, or validating DICOM files, or running DIMSE services (C-ECHO/STORE/FIND/MOVE/GET), worklists, or structured reports from the terminal."
metadata:
  version: "2026-06-12"
---

# DCMTK Command-Line Reference

DCMTK is the **OFFIS DICOM Toolkit** — a mature, BSD-licensed reference
implementation of large parts of the DICOM standard. This skill covers its
**command-line tools** (the C++ API is out of scope here).

If you can do it with DICOM, there is probably a `dcm*` binary for it.
The catch: the tool set is large (~70 binaries across 12 modules) and the
flag conventions (`-x` vs `+x` are *different flags*) are surprising. This
skill exists so an AI agent can pick the right tool, write a correct
invocation on the first try, and avoid the classic DCMTK potholes.

## Mental model

DCMTK groups tools into modules by what they touch:

```
dcmdata    on-disk DICOM files: parse, dump, modify, encode/decode (no network)
dcmnet     DIMSE over TCP: ECHO, STORE, FIND, MOVE, GET
dcmimage   rendering DICOM pixel data to common image formats (PNG/PNM/BMP/TIFF)
dcmjpeg    JPEG (DCT) compression / decompression of DICOM pixel data
dcmjpls    JPEG-LS compression / decompression of DICOM pixel data
dcmsr      Structured Reporting: dump, render, round-trip with XML
dcmqrdb    a small standalone Q/R database server (test PACS) + indexer
dcmwlm     a small standalone Modality Worklist server
dcmsign    DICOM digital signatures (sign / verify / remove)
dcmrt      Radiotherapy object inspection (RT Plan / Struct / Dose / etc.)
dcmpstat   Presentation states + print SCP/SCU (advanced; not covered here)
dcmtls     TLS support (used by dcmnet tools; not a tool of its own)
```

The CLI naming is consistent once you see it: tools that **encode** start with `dcmc*`
(`dcmcjpeg`, `dcmcjpls`, `dcmcrle`); tools that **decode** start with `dcmd*`
(`dcmdjpeg`, `dcmdjpls`, `dcmdrle`); SCUs end in `*scu` (network client) and
SCPs end in `*scp` (network server).

### The DIMSE service map

```
   Service Class      Operation        SCU tool             SCP tool
   ─────────────────────────────────────────────────────────────────
   Verification       C-ECHO           echoscu              storescp accepts
   Storage            C-STORE          storescu, dcmsend    storescp, dcmrecv
   Query/Retrieve     C-FIND           findscu              dcmqrscp
                      C-MOVE           movescu              dcmqrscp
                      C-GET            getscu               dcmqrscp
   Worklist           C-FIND           findscu (with -W)    wlmscpfs
```

For a real PACS you'd use Orthanc / DCM4CHEE / ConQuest as the SCP. DCMTK's
own SCPs (`dcmqrscp`, `wlmscpfs`) are for testing and integration scaffolding.

### The flag-prefix convention

```
  -x   ALWAYS a mutually-exclusive choice (one mode out of several)
  +x   ALWAYS turns a feature on or adds something
  --x  long form of -x or +x; same semantics
```

So `-xe` (propose little-endian) and `+e1` (encode JPEG Baseline) are not
related — different prefix, different tool family, different meaning.

## Which tool for which task

| You want to …                                       | Tool                | Reference                       |
|-----------------------------------------------------|---------------------|---------------------------------|
| Verify a PACS is reachable                          | `echoscu`           | [dcmnet.md](references/dcmnet.md) |
| Send DICOM file(s) to a PACS                        | `dcmsend` (or `storescu` for fine TS control) | [dcmnet.md](references/dcmnet.md) |
| Receive DICOM into a folder                         | `storescp` (or `dcmrecv`) | [dcmnet.md](references/dcmnet.md) |
| Query a PACS (by PatientID / Date / Accession)      | `findscu`           | [dcmnet.md](references/dcmnet.md) |
| Pull studies from a PACS                            | `movescu` or `getscu` | [dcmnet.md](references/dcmnet.md) |
| Show all tags in a DICOM file                       | `dcmdump`           | [dcmdata.md](references/dcmdata.md) |
| Find one tag in a DICOM file                        | `dcmdump --search KEY` | [dcmdata.md](references/dcmdata.md) |
| Anonymize / modify a tag                            | `dcmodify`          | [dcmdata.md](references/dcmdata.md) |
| Convert DICOM → JSON                                | `dcm2json`          | [dcmdata.md](references/dcmdata.md) |
| Convert DICOM → XML                                 | `dcm2xml`           | [dcmdata.md](references/dcmdata.md) |
| Verify a file is valid DICOM Part-10                | `dcmftest`          | [dcmdata.md](references/dcmdata.md) |
| Build a DICOMDIR for media interchange              | `dcmmkdir` (legacy alias: `dcmgpdir`) | [dcmdata.md](references/dcmdata.md) |
| Change transfer syntax (uncompressed only)          | `dcmconv`           | [dcmdata.md](references/dcmdata.md) |
| Compress DICOM with JPEG                            | `dcmcjpeg`          | [image-codecs.md](references/image-codecs.md) |
| Decompress JPEG-encoded DICOM                       | `dcmdjpeg`          | [image-codecs.md](references/image-codecs.md) |
| Compress / decompress with JPEG-LS                  | `dcmcjpls` / `dcmdjpls` | [image-codecs.md](references/image-codecs.md) |
| Compress / decompress with RLE                      | `dcmcrle` / `dcmdrle` | [dcmdata.md](references/dcmdata.md) |
| Render DICOM → PNG / JPEG / TIFF / BMP / PNM        | `dcm2img`           | [image-codecs.md](references/image-codecs.md) |
| Resize a DICOM image                                | `dcmscale`          | [image-codecs.md](references/image-codecs.md) |
| Wrap JPEG/PNG/BMP/TIFF as a DICOM                   | `img2dcm`           | [img-pdf-import.md](references/img-pdf-import.md) |
| Wrap a PDF (or CDA/STL/OBJ) as Encapsulated DICOM   | `dcmencap` (legacy alias: `pdf2dcm`) | [img-pdf-import.md](references/img-pdf-import.md) |
| Extract embedded PDF/CDA/STL/OBJ from a DICOM       | `dcmdecap` (legacy alias: `dcm2pdf`) | [img-pdf-import.md](references/img-pdf-import.md) |
| Dump a Structured Report's content tree             | `dsrdump`           | [dcmsr.md](references/dcmsr.md) |
| Render SR → HTML                                    | `dsr2html`          | [dcmsr.md](references/dcmsr.md) |
| Round-trip SR through XML                           | `dsr2xml` / `xml2dsr` | [dcmsr.md](references/dcmsr.md) |
| Stand up a test PACS                                | `dcmqrscp` + `dcmqridx` | [dcmqrdb-wlm.md](references/dcmqrdb-wlm.md) |
| Stand up a test Modality Worklist server            | `wlmscpfs`          | [dcmqrdb-wlm.md](references/dcmqrdb-wlm.md) |
| Sign / verify DICOM digital signatures              | `dcmsign`           | [dcmsign-dcmrt.md](references/dcmsign-dcmrt.md) |
| Inspect RT Plan / Struct / Dose objects             | `drtdump`           | [dcmsign-dcmrt.md](references/dcmsign-dcmrt.md) |

For shared flags (logging, network, TLS, transfer-syntax negotiation, file
format) see [common-options.md](references/common-options.md). For transfer-
syntax UIDs and the matching `-x*` / `+t*` flags see
[transfer-syntax-uids.md](references/transfer-syntax-uids.md).

## Top recipes

The examples below use these placeholders — replace them with the real values
for the target environment:

```
PACS_HOST       hostname or IP of the peer PACS                  e.g. pacs.hospital.local
PACS_PORT       DICOM TCP port of the peer                       e.g. 104, 4242, 11112
PACS_AET        called AE title — must match the peer's config   e.g. MAIN_PACS
MY_AET          our calling AE title                             e.g. ACME_SCU
```

### 1. Verify a PACS is reachable (C-ECHO)

```bash
echoscu -v PACS_HOST PACS_PORT -aec PACS_AET -aet MY_AET
```

Success looks like `Received Echo Response (Success)`. If you see
`Association Rejected` the peer either doesn't know your `-aec` AE title or
your IP isn't whitelisted in its config.

### 2. Send DICOM files to a PACS (C-STORE)

**Single file, full TS control:**

```bash
storescu -v PACS_HOST PACS_PORT -aec PACS_AET -aet MY_AET input.dcm
```

**Folder, recursively, with per-file rename on success:**

```bash
dcmsend -v PACS_HOST PACS_PORT -aec PACS_AET -aet MY_AET +sd +r /path/to/studies/
```

When to use which:
- `storescu` — battle-tested, full `-x*` control over TS negotiation, no
  built-in "scan a folder" mode beyond `+sd +r`. Reach for it when you need
  exact control over which TS are proposed.
- `dcmsend` — newer, simpler. Handles directory scanning, status summary,
  `.done` / `.bad` renaming. Recommended default for batch sends to a known
  peer.

Common failure: `Association Aborted: presentation context not supported`.
The peer doesn't accept the SOP class or the TS the file is encoded in. Run
with `-d` to see the negotiation; the offered ACs vs accepted ACs make the
problem obvious.

### 3. Receive DICOM into a folder (C-STORE SCP)

```bash
storescp -v -aet MY_AET --output-directory /path/to/incoming/ \
         --sort-conc-studies study_ PACS_PORT
```

Files arrive under `/path/to/incoming/study_<StudyInstanceUID>/`.

For more flexible filename templating and per-study post-processing hooks,
`dcmrecv` is the modern alternative — same idea, simpler config:

```bash
dcmrecv -v --output-directory /path/to/incoming/ PACS_PORT
```

### 4. Query a PACS (C-FIND)

A C-FIND query is built from `-k` keys: each `-k` either constrains the
search (`-k "(0010,0020)=PATIENT_ID"`) or requests that attribute be
returned (`-k "(0010,0010)"` with empty value).

**All studies for a patient:**

```bash
findscu -v -S \
  -k "(0008,0052)=STUDY" \
  -k "(0010,0020)=PATIENT_ID" \
  -k "(0010,0010)" \
  -k "(0020,000D)" \
  -k "(0008,0020)" \
  PACS_HOST PACS_PORT -aec PACS_AET -aet MY_AET
```

Flags to know:
- `-S` study root model (default and most common); `-P` patient root; `-W` worklist
- `(0008,0052)` QueryRetrieveLevel — must match the model (STUDY/SERIES/IMAGE)
- Each `-k` with a value constrains; each `-k` with no value (just the tag)
  asks the SCP to return it

### 5. Retrieve studies (C-MOVE)

C-MOVE asks the SCP to push instances to a destination AE — which means the
destination must be a running storescp/dcmrecv reachable from the SCP, and
the destination's AE title must be pre-registered on the SCP.

**Terminal A — start the local listener:**

```bash
storescp -v --output-directory ./retrieved/ -aet MY_AET 11112
```

**Terminal B — issue the C-MOVE (destination = our `MY_AET` on port 11112):**

```bash
movescu -v -S \
  -k "(0008,0052)=STUDY" \
  -k "(0020,000D)=1.2.3.4.5.STUDY.UID" \
  -aem MY_AET \
  PACS_HOST PACS_PORT -aec PACS_AET -aet MY_AET
```

If the PACS has no entry for `MY_AET` in its configuration the move fails
with `Move Destination Unknown`. `movescu` itself can also act as a
subordinate listener with `--port 11112 --output-directory ./out/` — useful
for tests where you don't want a separate `storescp` terminal.

For point-to-point retrieval where the SCP doesn't need to know about your
listener at all, **C-GET** (`getscu`) is simpler:

```bash
getscu -v -S -k "(0008,0052)=STUDY" -k "(0020,000D)=1.2.3.4.5.STUDY.UID" \
       --output-directory ./retrieved/ \
       PACS_HOST PACS_PORT -aec PACS_AET
```

But many production PACS don't support C-GET — C-MOVE is the safer default.

### 6. Dump tags from a file

**Whole file, every tag:**

```bash
dcmdump input.dcm
```

**Just one tag (by name or by group/element):**

```bash
dcmdump --search PatientID input.dcm
dcmdump --search "0010,0010" input.dcm
```

Output is one line per attribute:
```
(0010,0010) PN [DOE^JANE]                                #   8, 1 PatientName
```
Columns: tag, VR, value, length, value multiplicity, attribute name.

To **recurse into sequence items** (e.g., reading a Structured Report tree)
add `+R`. To skip the raw pixel data dump add `--max-read-length 4`. The
output of `dcmdump` can be parsed back into DICOM by `dump2dcm` for
round-trip editing.

### 7. Anonymize / modify tags

`dcmodify` modifies in place (creates a `.bak` backup unless `-nb`):

```bash
# Replace PatientName everywhere it appears (main set + every sequence item)
dcmodify -nb -ma "(0010,0010)=ANON^PATIENT" input.dcm

# Insert a tag that wasn't there
dcmodify -nb -i "(0010,4000)=anonymized 2026-05-25" input.dcm

# Delete every private tag (group is odd)
dcmodify -nb -ep input.dcm

# Generate new UIDs for the study/series/instance hierarchy
dcmodify -nb -gst -gse -gsi input.dcm
```

Operation flags (mutually exclusive per-tag):
- `-i` insert if absent (error if present)
- `-m` modify if present (error if absent)
- `-ma` modify-all (main set + every sequence item)
- `-e` erase / `-ea` erase-all / `-ep` erase-private
- `-gst` `-gse` `-gsi` regenerate Study/Series/SOPInstance UIDs

**Gotcha:** by default `dcmodify` writes a `.bak` of every modified file.
On a 10k-file anonymization that doubles your disk usage and is almost
always unwanted — always pass `-nb` for batch work.

### 8. Render DICOM to PNG / JPEG / TIFF / BMP / PNM

```bash
dcm2img +on input.dcm out.png      # PNG (8-bit)
dcm2img +on2 input.dcm out.png     # PNG (16-bit — keep full bit depth)
dcm2img +oj input.dcm out.jpg      # JPEG (8-bit lossy baseline)
dcm2img +ot input.dcm out.tiff     # TIFF
dcm2img +ob input.dcm out.bmp      # BMP
dcm2img +op input.dcm out.pgm      # PNM raw (PGM for grayscale, PPM for color)
```

`dcm2img` flag-letter convention: **`+o<letter>`** picks the output format
(`n`=PNG, `j`=JPEG, `t`=TIFF, `b`=BMP, `p`=PNM/PGM/PPM, `l`=JPEG-LS).
`+oa` (`--write-auto`) picks based on the output filename extension.

`dcm2img` automatically decompresses JPEG / JPEG-LS / RLE inputs — no
separate `dcmdjpeg` step is needed. For multi-frame data, `+Fa` writes one
output file per frame (filenames get a frame-number suffix).

If you need to control windowing rather than letting `dcm2img` use the
file's VOI LUT:

```bash
dcm2img +on +Wm input.dcm out.png         # use min/max of pixels as window
dcm2img +on +W 50 350 input.dcm out.png   # WindowCenter=50, WindowWidth=350
```

`dcm2pnm`, `dcmj2pnm`, `dcml2pnm` are **deprecated aliases** for `dcm2img`
in 3.7 — they still work but print a deprecation banner. New code should
call `dcm2img`.

## Cross-cutting gotchas

**Transfer-syntax negotiation drama.** The single most common source of
"why doesn't this work" with `storescu` / `movescu`. The SCU proposes a
list of TS for each SOP class; the SCP picks one. Mismatches give
`presentation context not supported`. Solutions:
- Run with `-d` (debug) to see the negotiation.
- If your file is already compressed (JPEG / JPEG-LS / RLE), propose the
  matching TS with the right `-x*` flag — DCMTK will NOT transcode on the
  fly to keep the association alive.
- See [transfer-syntax-uids.md](references/transfer-syntax-uids.md).

**AE-title rules.** Max 16 characters, ASCII uppercase + digits + `._-`,
no leading/trailing whitespace. Some PACS silently trim or normalize, then
reject because the trimmed value doesn't match their whitelist. Always
verify with the peer's log what AE title it actually saw.

**`dcm2img` first, then dedicated decoders.** When you just want to look at
an image, `dcm2img` handles compressed inputs natively. The dedicated
`dcmdjpeg` / `dcmdjpls` / `dcmdrle` tools are only needed when you want to
keep the data in DICOM form (e.g., decompress to send to a peer that
doesn't support the compressed TS).

**`dcmodify` `.bak` files.** Default behavior creates `<file>.bak` next to
every modified file. Use `-nb` for any batch operation.

**`dcmconv` can't compress.** It only converts between uncompressed TS. For
JPEG/JPEG-LS/RLE compression you must use the dedicated codec tools
(`dcmcjpeg`, `dcmcjpls`, `dcmcrle`).

**`img2dcm` synthesizes metadata.** A bare `img2dcm input.jpg out.dcm`
creates a DICOM with random Patient/Study/Series UIDs and no real patient
identifiers. Most PACS will accept it but you'll have an orphan study.
Always pass `--study-from REFERENCE.dcm` (or `--series-from`) to inherit
the right Patient/Study/Series context.

**Deprecated aliases that still ship.** Several DCMTK 3.7 binaries print a
deprecation banner and forward to a newer tool with a richer feature set:
- `dcm2pnm`, `dcmj2pnm`, `dcml2pnm` → use `dcm2img`
- `dcmgpdir` → use `dcmmkdir`
- `pdf2dcm` → use `dcmencap` (also handles CDA/STL/OBJ/MTL input)
- `dcm2pdf` → use `dcmdecap` (also extracts CDA/STL/OBJ/MTL)
The legacy binaries still work for now; new scripts should use the modern
names.

**DICOMDIR's ISO 9660 trap.** `dcmmkdir` requires every referenced file's
path (directory components and filename) to use only `A-Z 0-9 _`, with each
component ≤ 8 characters and the extension ≤ 3 characters (classic DOS
8.3). A hyphen, lowercase letter, or 9+-char directory name kills the
build with `invalid character(s) in filename`. Stage the files into an
ISO-9660-clean tree (`STUDY01/SERIES01/IMG00001`) before running.

**Data dictionary missing.** If a tool errors with "data dictionary not
loaded" your install is broken or `DCMDICTPATH` points somewhere wrong. On
macOS Homebrew, the dictionary lives at `/opt/homebrew/share/dcmtk/dicom.dic`.

**`--version` lies (kind of).** Every tool prints the version banner, but
optional features (JPEG 2000, zlib, OpenSSL/TLS, libtiff, libpng) depend on
compile-time linkage. Always check `<tool> --version | head -20` for the
"with X support" lines before assuming a feature is available.

## Reference files

Load these into your context only when a task touches the relevant area:

| File                                                            | Load when …                                                                |
|-----------------------------------------------------------------|----------------------------------------------------------------------------|
| [common-options.md](references/common-options.md)               | Any DCMTK invocation — covers the shared flags (logging, network, TLS, file format). |
| [transfer-syntax-uids.md](references/transfer-syntax-uids.md)   | Anything touching compression, TS negotiation, or `dcmconv` / `dcmcjpeg`. |
| [dcmnet.md](references/dcmnet.md)                               | C-ECHO, C-STORE, C-FIND, C-MOVE, C-GET — anything `*scu` / `*scp` / `dcmsend` / `dcmrecv`. |
| [dcmdata.md](references/dcmdata.md)                             | Parsing, modifying, converting, building or indexing DICOM files on disk. |
| [image-codecs.md](references/image-codecs.md)                   | Rendering DICOM to PNG/JPEG/TIFF, or JPEG / JPEG-LS / RLE compression.    |
| [img-pdf-import.md](references/img-pdf-import.md)               | Wrapping non-DICOM input (JPEG, PNG, BMP, TIFF, PDF) as a DICOM object.   |
| [dcmsr.md](references/dcmsr.md)                                 | Structured Reporting: inspect, render to HTML, round-trip through XML.    |
| [dcmqrdb-wlm.md](references/dcmqrdb-wlm.md)                     | Standing up a test PACS (`dcmqrscp`) or a test worklist (`wlmscpfs`).     |
| [dcmsign-dcmrt.md](references/dcmsign-dcmrt.md)                 | Digital signatures or RT object inspection.                               |

## Quick-check: does my install have what I need?

```bash
echoscu --version | head -20    # check OpenSSL/TLS, zlib
dcm2img --version | head -20    # check libpng / libtiff / libopenjpeg
dcmcjpls --version              # check JPEG-LS linkage
```

If a feature line is missing the linked library, the corresponding flag
will silently be absent from `--help`. Don't troubleshoot by guessing —
verify the linkage first.
