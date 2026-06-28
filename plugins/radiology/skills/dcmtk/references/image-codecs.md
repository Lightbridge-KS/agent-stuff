# DCMTK Image-Conversion and Codec Tools

Tools for moving DICOM pixel data **out** of DICOM (to PNG/PNM/JPEG/BMP/TIFF)
and for transcoding between DICOM transfer syntaxes (uncompressed ↔ JPEG,
JPEG-LS). The modern unified converter is `dcm2img`; everything else is either
a transcoding codec (`dcmcjpeg`/`dcmdjpeg`/`dcmcjpls`/`dcmdjpls`), an in-DICOM
resampler (`dcmscale`), or a deprecated alias kept for backward compatibility
(`dcm2pnm`/`dcmj2pnm`/`dcml2pnm`).

See [common-options.md](common-options.md) for shared flags (logging, input
file/transfer-syntax flags, output dataset/file-format flags). See
[transfer-syntax-uids.md](transfer-syntax-uids.md) for the TS UID table.

---

## When to use which tool

| Goal                                              | Use                                                  |
|---------------------------------------------------|------------------------------------------------------|
| DICOM → PNG / JPEG / TIFF / BMP / PNM             | `dcm2img`                                            |
| DICOM → PNG when input is JPEG/JPEG-LS/RLE compressed | `dcm2img` (it decompresses transparently)        |
| Resize a DICOM (output stays DICOM)               | `dcmscale`                                           |
| Compress an uncompressed DICOM with JPEG          | `dcmcjpeg`                                           |
| Decompress a JPEG-encoded DICOM back to native    | `dcmdjpeg`                                           |
| Compress an uncompressed DICOM with JPEG-LS       | `dcmcjpls`                                           |
| Decompress a JPEG-LS-encoded DICOM back to native | `dcmdjpls`                                           |
| Re-encode JPEG-LS DICOM as JPEG (or vice versa)   | Pipeline: `dcmdjpls` → `dcmcjpeg`                    |

---

## The "JPEG-encoded DICOM → PNG" pipeline

There are two ways to do this. Pick based on whether you need an intermediate
uncompressed DICOM file.

### One step (recommended)

`dcm2img` natively handles JPEG, JPEG-LS, and RLE compressed inputs. No
separate decompress step is needed:

```bash
dcm2img input.dcm out.png
```

This works whether `input.dcm` is uncompressed, JPEG baseline, JPEG lossless,
JPEG-LS, or RLE. The DCMTK image library calls the relevant codec
internally — you do not need to invoke `dcmdjpeg` or `dcmdjpls` first.

### Two steps (when you also want the decompressed DICOM)

If you want to keep an uncompressed DICOM alongside the PNG (for example to
feed another tool that does not support encapsulated transfer syntaxes):

```bash
# JPEG-compressed input
dcmdjpeg input.dcm decoded.dcm
dcm2img  decoded.dcm out.png

# JPEG-LS-compressed input
dcmdjpls input.dcm decoded.dcm
dcm2img  decoded.dcm out.png
```

The `dcmdjpeg` / `dcmdjpls` step writes an uncompressed Explicit-VR LE file
(default `+te`). Pipe-style chaining works too:

```bash
dcmdjpeg input.dcm - | dcm2img - out.png
```

(both tools accept `-` for stdin/stdout).

---

## dcm2img

> Modern unified converter: DICOM image → PNG, JPEG, JPEG-LS, BMP, TIFF, or PGM/PPM.

This is the tool to reach for in 99% of "I have a DICOM, I want a regular
image file" tasks. It supersedes the legacy trio `dcm2pnm` / `dcmj2pnm` /
`dcml2pnm` — they are now thin aliases that just defer here.

`dcm2img` also handles compressed inputs natively (JPEG baseline + extended +
lossless, JPEG-LS lossless + near-lossless, RLE Lossless), so the common
"decompress then convert" two-tool dance is unnecessary.

### Synopsis

```
dcm2img [options] dcmfile-in [bitmap-out]
```

If `bitmap-out` is omitted the image is written to stdout (ASCII PGM/PPM by
default — useful for piping into ImageMagick).

### Output format selection

If you give `dcm2img` an output filename it picks the format from the
extension (`.png` → PNG, `.jpg` → JPEG, `.bmp` → BMP, `.tif`/`.tiff` → TIFF,
`.pgm`/`.ppm` → PNM). To force a specific format regardless of extension, use
one of the `+o*` flags:

| Flag    | Long form                  | Output                                                          |
|---------|----------------------------|-----------------------------------------------------------------|
| `+oa`   | `--write-auto`             | Pick from filename extension (default for files; falls back to BMP if unknown). |
| `+op`   | `--write-raw-pnm`          | 8-bit **binary** PGM/PPM.                                       |
| `+opb`  | `--write-8-bit-pnm`        | 8-bit **ASCII** PGM/PPM (default when output is stdout).        |
| `+opw`  | `--write-16-bit-pnm`       | 16-bit ASCII PGM/PPM.                                           |
| `+opn N`| `--write-n-bit-pnm N`      | n-bit (1..32) ASCII PGM/PPM. Useful for preserving native depth.|
| `+ob`   | `--write-bmp`              | 8-bit monochrome **or** 24-bit color BMP.                       |
| `+obp`  | `--write-8-bit-bmp`        | 8-bit palette BMP (monochrome only).                            |
| `+obt`  | `--write-24-bit-bmp`       | 24-bit truecolor BMP.                                           |
| `+obr`  | `--write-32-bit-bmp`       | 32-bit truecolor BMP.                                           |
| `+ot`   | `--write-tiff`             | 8-bit monochrome or 24-bit color TIFF (needs libtiff).          |
| `+on`   | `--write-png`              | 8-bit monochrome or 24-bit color PNG (needs libpng).            |
| `+on2`  | `--write-16-bit-png`       | 16-bit monochrome / 48-bit color PNG.                           |
| `+oj`   | `--write-jpeg`             | 8-bit lossy JPEG (baseline) — for output, *not* DICOM-JPEG.     |
| `+ol`   | `--write-jpls`             | JPEG-LS image file (needs libcharls).                           |

PNG support requires DCMTK to have been built with libpng; TIFF requires
libtiff. Check with `dcm2img --version`. If a format is missing, the flag is
simply absent from `--help`.

Quality / sub-options for the writer formats:

| Flag     | Long form               | Effect                                                          |
|----------|-------------------------|-----------------------------------------------------------------|
| `+Jq Q`  | `--compr-quality Q`     | JPEG quality 0..100 (default 90).                               |
| `+Js4`   | `--sample-444`          | JPEG 4:4:4 (no chroma subsampling).                             |
| `+Js2`   | `--sample-422`          | JPEG 4:2:2 (default).                                           |
| `+Js1`   | `--sample-411`          | JPEG 4:1:1.                                                     |
| `+Tl`    | `--compr-lzw`           | TIFF LZW compression (default).                                 |
| `+Tr`    | `--compr-rle`           | TIFF RLE compression.                                           |
| `+Tn`    | `--compr-none`          | TIFF uncompressed.                                              |
| `+il`/`-il` | `--interlace` / `--nointerlace` | PNG interlaced vs not (default interlaced).          |
| `+mf`/`-mf` | `--meta-file` / `--meta-none`  | PNG: include DICOM metadata as PNG tEXt chunks.       |
| `+Trl`   | `--rendered-lossless`   | JPEG-LS file output: encode the *rendered* image losslessly (default). |
| `+Tll`   | `--true-lossless`       | JPEG-LS file output: encode the raw pixel data losslessly.      |
| `+f8`    | `--force-8-bit`         | Force 8-bit output depth (not with `+Tll`).                     |

### Frame selection (multi-frame inputs)

| Flag         | Long form                | Effect                                                       |
|--------------|--------------------------|--------------------------------------------------------------|
| `+F N`       | `--frame N`              | Write only frame N (1-based). Default: 1.                    |
| `+Fr N C`    | `--frame-range N C`      | Write C frames starting at frame N.                          |
| `+Fa`        | `--all-frames`           | Write every frame.                                           |
| `+Fc`        | `--use-frame-counter`    | When writing multiple frames, append a 0-based counter to filenames (default). |
| `+Fn`        | `--use-frame-number`     | Use the absolute DICOM frame number instead of a counter.    |

With `+Fr` or `+Fa`, `dcm2img` appends a number to the output filename: given
`out.png` it produces `out.0.png`, `out.1.png`, … (or `out.1.png`, `out.2.png`,
… with `+Fn`).

### VOI windowing (essential for monochrome diagnostic images)

By default `dcm2img` does **no** windowing — it just maps the modality-LUT
output linearly to the output bit depth. For CT/MR/XA you almost always want
to apply a window:

| Flag         | Long form                  | Effect                                                                 |
|--------------|----------------------------|------------------------------------------------------------------------|
| `-W`         | `--no-windowing`           | No VOI windowing (default — usually wrong for grayscale diagnostic).   |
| `+Wi N`      | `--use-window N`           | Use the N-th VOI window (Window Center/Width pair) from the dataset.   |
| `+Wl N`      | `--use-voi-lut N`          | Use the N-th VOI LUT from the dataset.                                 |
| `+Wm`        | `--min-max-window`         | Auto-window using the actual pixel min / max.                          |
| `+Wn`        | `--min-max-window-n`       | Same, but ignore extreme outliers (background padding, burned overlays).|
| `+Wr L T W H`| `--roi-min-max-window …`   | Min/max window over an ROI rectangle (left, top, width, height).       |
| `+Wh N`      | `--histogram-window N`     | Histogram-based auto-window, ignoring N percent of pixels.             |
| `+Ww C W`    | `--set-window C W`         | Explicit center/width.                                                 |
| `+Wfl`       | `--linear-function`        | VOI LUT function = LINEAR.                                             |
| `+Wfs`       | `--sigmoid-function`       | VOI LUT function = SIGMOID.                                            |

Rule of thumb: use `+Wi 1` if the dataset has one or more presets baked in
(most modality output); use `+Wm` or `+Wh 5` for ad-hoc dumps where you do
not know what the dataset declares.

### Modality LUT, presentation LUT, polarity

| Flag    | Long form              | Effect                                                            |
|---------|------------------------|-------------------------------------------------------------------|
| `+M`    | `--use-modality`       | Apply Modality LUT / Rescale Slope+Intercept (default).           |
| `-M`    | `--no-modality`        | Skip modality transform. Output stays in raw stored pixel units.  |
| `+Pid`  | `--identity-shape`     | Presentation LUT shape = IDENTITY.                                |
| `+Piv`  | `--inverse-shape`      | Presentation LUT shape = INVERSE (swap black/white).              |
| `+Pod`  | `--lin-od-shape`       | Presentation LUT shape = LIN OD (optical density mapping).        |
| `+P`    | `--change-polarity`    | Invert output pixel values (cheap negative).                      |
| `+G`    | `--grayscale`          | Convert color to grayscale on the way out.                        |

### Geometry: rotation, flip, scaling, clipping

| Flag         | Long form               | Effect                                                       |
|--------------|-------------------------|--------------------------------------------------------------|
| `+Rl`        | `--rotate-left`         | Rotate −90°.                                                 |
| `+Rr`        | `--rotate-right`        | Rotate +90°.                                                 |
| `+Rtd`       | `--rotate-top-down`     | Rotate 180°.                                                 |
| `+Lh`        | `--flip-horizontally`   | Flip on vertical axis.                                       |
| `+Lv`        | `--flip-vertically`     | Flip on horizontal axis.                                     |
| `+Lhv`       | `--flip-both-axes`      | Flip both.                                                   |
| `+Sxv N`     | `--scale-x-size N`      | Scale x to N pixels; y auto-computed to keep aspect ratio.   |
| `+Syv N`     | `--scale-y-size N`      | Scale y to N pixels; x auto-computed.                        |
| `+Sxf F`     | `--scale-x-factor F`    | Scale x by float factor; y auto.                             |
| `+Syf F`     | `--scale-y-factor F`    | Scale y by factor; x auto.                                   |
| `+a`/`-a`    | `--recognize-aspect` / `--ignore-aspect` | Respect (default) or ignore Pixel Aspect Ratio. |
| `+i N`       | `--interpolate N`       | Interpolation 1..4 when scaling (see Gotchas).               |
| `-i`         | `--no-interpolation`    | Nearest-neighbour.                                           |
| `+C L T W H` | `--clip-region L T W H` | Crop a rectangle (left, top, width, height) in pixels.       |

### Compressed-input handling (JPEG / JPEG-LS only)

These only matter when the input is JPEG-encoded:

| Flag    | Long form                | Effect                                                          |
|---------|--------------------------|-----------------------------------------------------------------|
| `+cp`   | `--conv-photometric`     | Convert YCbCr → RGB if photometric interpretation says so (default). |
| `+cl`   | `--conv-lossy`           | Assume YCbCr and convert to RGB for any lossy JPEG.             |
| `+cg`   | `--conv-guess`           | Convert if the JPEG library guesses YCbCr.                      |
| `+cgl`  | `--conv-guess-lossy`     | Both `+cl` and `+cg` combined.                                  |
| `+ca`   | `--conv-always`          | Always treat color images as YCbCr → RGB.                       |
| `+cn`   | `--conv-never`           | Never touch the color space.                                    |
| `+bs`/`-bs` | `--bits-stored-fix` / `--bits-stored-keep` | Reconcile vs preserve BitsStored mismatch between header and bitstream. |
| `+w6`   | `--workaround-pred6`     | Lossless-JPEG 16-bit predictor-6 overflow workaround.           |
| `+wi`   | `--workaround-incpl`     | Tolerate JPEG fragments with incomplete data.                   |
| `+wc`   | `--workaround-cornell`   | Cornell-encoder Huffman-overflow workaround (legacy 16-bit lossless). |

### Other useful flags

| Flag    | Long form         | Effect                                                          |
|---------|-------------------|-----------------------------------------------------------------|
| `-im`   | `--image-info`    | Print image details (geometry, photometric, etc.) — needs `-v`. |
| `-o`    | `--no-output`     | Skip file output. Pair with `-im -v` to just inspect.           |
| `-O`    | `--no-overlays`   | Do not render burned-in graphic overlays.                       |
| `+O N`  | `--display-overlay N` | Render overlay plane N (0=all).                             |
| `+Ma`   | `--accept-acr-nema` | Tolerate ACR-NEMA images without Photometric Interpretation.  |
| `+Mp`   | `--accept-palettes` | Tolerate non-standard palette tag numbers.                    |

### Examples

Convert a single-frame CT to PNG with auto windowing:

```bash
dcm2img +Wm input.dcm out.png
```

Apply the first VOI preset from the dataset and write 16-bit PNG:

```bash
dcm2img +Wi 1 +on2 input.dcm out.png
```

Dump every frame of a multi-frame study as numbered JPEGs at quality 85:

```bash
dcm2img +Fa +oj +Jq 85 input.dcm out.jpg
# produces out.0.jpg, out.1.jpg, …
```

Inspect the image (no file written):

```bash
dcm2img -v -im -o input.dcm
```

Pipe a binary PGM into ImageMagick for further processing:

```bash
dcm2img +Wm +op input.dcm - | magick pgm:- -auto-level out.png
```

### Gotchas

- **Default is no windowing**, so monochrome diagnostic images often come out
  nearly black or nearly white without `+Wm`, `+Wi`, or `+Ww`. This trips up
  every newcomer.
- The `+Sxv`/`+Syv`/`+Sxf`/`+Syf` family are *mutually exclusive in effect* —
  giving more than one is undefined. To pin both axes independently, use
  `dcmscale` (or post-process the output).
- PNG / TIFF / JPEG-LS output flags only work if the corresponding library
  was linked at build time. Always check `dcm2img --version`.
- Output to stdout (no filename) defaults to **ASCII** PGM/PPM (`+opb`), which
  is huge. Force `+op` for binary if piping.
- `dcm2img` can also *write* JPEG and JPEG-LS image **files** — this is for
  the output bitmap, not for changing the input DICOM's transfer syntax. To
  re-encode a DICOM, use `dcmcjpeg` / `dcmcjpls`.

---

## dcm2pnm

> Deprecated alias for `dcm2img`. The flag set is identical; only the binary name differs.

New code should call `dcm2img`. DCMTK 3.7 still ships `dcm2pnm` as a stub for
backward compatibility — the man page is one paragraph long and just points
at `dcm2img`. Old scripts work unchanged.

---

## dcmscale

> Resize a DICOM image and **keep the output in DICOM** (uncompressed or RLE).

Unlike `dcm2img` (which writes a PNG/JPEG/etc.), `dcmscale` writes a
properly-formed DICOM file with rescaled pixel data, new Rows / Columns, and
(by default) a fresh SOP Instance UID. Use it when downstream tools want
DICOM, not a bitmap.

### Synopsis

```
dcmscale [options] dcmfile-in dcmfile-out
```

Both filenames are required (no stdout-default like `dcm2img`).

### Essential flags

| Flag         | Long form               | Effect                                                            |
|--------------|-------------------------|-------------------------------------------------------------------|
| `+Sxv N`     | `--scale-x-size N`      | Resize x to N pixels; y auto-computed from aspect ratio.          |
| `+Syv N`     | `--scale-y-size N`      | Resize y to N pixels; x auto-computed.                            |
| `+Sxf F`     | `--scale-x-factor F`    | Resize x by float factor; y auto.                                 |
| `+Syf F`     | `--scale-y-factor F`    | Resize y by factor; x auto.                                       |
| `-S`         | `--no-scaling`          | No scaling (default — but then why call dcmscale).                |
| `+i N`       | `--interpolate N`       | Interpolation algorithm 1..4 (default 1). See below.              |
| `-i`         | `--no-interpolation`    | Nearest-neighbour resampling.                                     |
| `+a`/`-a`    | `--recognize-aspect` / `--ignore-aspect` | Honour Pixel Aspect Ratio (default) or stretch.  |
| `+C L T W H` | `--clip-region L T W H` | Crop *before* scaling.                                            |
| `+ua`        | `--uid-always`          | Assign a new SOP Instance UID (default).                          |
| `+un`        | `--uid-never`           | Keep the original SOP Instance UID — almost always wrong.         |
| `+t=`        | `--write-xfer-same`     | Write back with the same TS as input (default).                   |
| `+te` `+ti` `+tb` | `--write-xfer-*`   | Force a specific uncompressed output TS.                          |

If you only give an X size, Y is computed to preserve aspect (and vice versa).
Give both `+Sxv` and `+Syv` to stretch to an exact box.

### Interpolation algorithms

| `+i N` | Algorithm                                                          |
|--------|--------------------------------------------------------------------|
| 0      | Off — equivalent to `-i` / nearest-neighbour.                      |
| 1      | Free scaling, pbmplus toolkit (default).                           |
| 2      | Free scaling, c't magazine algorithm.                              |
| 3      | Bilinear magnification (Stanescu).                                 |
| 4      | Bicubic magnification (Stanescu).                                  |

The user-facing manual page lists 1..4; `0` is the implicit "no interpolation"
case toggled with `-i`. For diagnostic-quality downsampling start with `+i 4`
(bicubic); for fast thumbnails `+i 1` is plenty.

### Examples

Downsample to 512 pixels wide, preserving aspect, with bicubic interpolation:

```bash
dcmscale +Sxv 512 +i 4 input.dcm out.dcm
```

Halve both dimensions:

```bash
dcmscale +Sxf 0.5 +i 2 input.dcm out.dcm
```

Crop a 256×256 ROI and scale it up 2×:

```bash
dcmscale +C 100 100 256 256 +Sxf 2.0 +i 4 input.dcm out.dcm
```

### Gotchas

- `dcmscale` **only handles uncompressed and RLE input**. For JPEG / JPEG-LS
  input, decompress first with `dcmdjpeg` / `dcmdjpls`.
- New SOP Instance UID is the default (`+ua`) — this is correct DICOM
  semantics (the scaled image is a *different* instance). Override with
  `+un` only if you really know why.
- If neither `+Sxv`/`+Syv`/`+Sxf`/`+Syf` is given, the tool runs but writes
  the image unchanged (modulo group lengths and a new UID).

---

## dcmcjpeg

> Encode an uncompressed DICOM with JPEG (lossy DCT or lossless DCT). The output is a DICOM file with an encapsulated transfer syntax.

This is the workhorse for shrinking DICOM-on-disk. Pick the wrong process and
peers will reject the file — most of the gotchas below are about that.

### Synopsis

```
dcmcjpeg [options] dcmfile-in dcmfile-out
```

### JPEG process selection (pick exactly one)

| Flag    | Long form                  | Output TS                                | Use for                                       |
|---------|----------------------------|------------------------------------------|-----------------------------------------------|
| `+e1`   | `--encode-lossless-sv1`    | JPEG Lossless Process 14 SV1 (1.2.840.10008.1.2.4.70) | **Default**. Most common lossless variant; widely supported. |
| `+el`   | `--encode-lossless`        | JPEG Lossless Process 14 (1.2.840.10008.1.2.4.57)     | Generic lossless (selection value selectable). |
| `+eb`   | `--encode-baseline`        | JPEG Baseline Process 1 (1.2.840.10008.1.2.4.50)      | 8-bit lossy. Most compatible lossy mode.       |
| `+ee`   | `--encode-extended`        | JPEG Extended Process 2 & 4 (1.2.840.10008.1.2.4.51)  | 12-bit lossy. Use for >8-bit modalities.       |
| `+es`   | `--encode-spectral`        | JPEG Spectral Selection Process 6 & 8 (.53) | Lossy; rarely used in practice.            |
| `+ep`   | `--encode-progressive`     | JPEG Full Progression Process 10 & 12 (.55) | Lossy; rarely used.                         |

> **Flag-name note.** The man page uses `+e1` for the SV1 lossless default
> (not `+e7` as some older docs say) and `+eb` for baseline (not `+e1`). If
> in doubt, run `dcmcjpeg --help` and read the actual binary.

### Lossless encoder selection

| Flag    | Long form               | Effect                                                            |
|---------|-------------------------|-------------------------------------------------------------------|
| `+tl`   | `--true-lossless`       | True-lossless codec (default since 3.5.4). Guarantees identical pixels. |
| `+pl`   | `--pseudo-lossless`     | Old "pseudo-lossless" codec — internal color conversions can introduce tiny errors. Higher compression ratio. |

With `+tl` (default), color-space, windowing, and pixel-scaling flags are
ignored or overridden. Use `+pl` only if you knowingly need the older
behaviour or to interoperate with very old peers.

### Lossless representation tuning

| Flag    | Long form                   | Range / Default        | Effect                                              |
|---------|-----------------------------|------------------------|-----------------------------------------------------|
| `+sv N` | `--selection-value N`       | 1..7, default 6        | Selection value for `+el` (Process 14, non-SV1).    |
| `+pt N` | `--point-transform N`       | 0..15, default 0       | Point transform. **N > 0 silently makes it lossy.** |

### Lossy representation tuning

| Flag    | Long form               | Range / Default       | Effect                                                  |
|---------|-------------------------|-----------------------|---------------------------------------------------------|
| `+q Q`  | `--quality Q`           | 0..100, default 90    | JPEG quality factor for lossy modes. 80–95 is the typical diagnostic range. |
| `+sm S` | `--smooth S`            | 0..100, default 0     | Pre-compression low-pass smoothing. Raises ratio; lowers quality. |
| `+ho`/`-ho` | `--huffman-optimize` / `--huffman-standard` | default `+ho` | Optimize Huffman tables (slightly smaller; default). |

### Compressed bits per sample

| Flag    | Long form          | Effect                                                  |
|---------|--------------------|---------------------------------------------------------|
| `+ba`   | `--bits-auto`      | Pick automatically based on input (default; forced with `+tl`). |
| `+be`   | `--bits-force-8`   | Force 8 bits/sample.                                    |
| `+bt`   | `--bits-force-12`  | Force 12 bits/sample (not valid with `+eb` baseline).   |
| `+bs`   | `--bits-force-16`  | Force 16 bits/sample (lossless only).                   |

### Color-space handling (lossy JPEG color images)

The encoder converts the color space and rewrites
**(0028,0004) PhotometricInterpretation** in the output accordingly. This is
the source of most "my PACS rejects this" issues.

| Flag    | Long form           | Effect on PhotometricInterpretation                                       |
|---------|---------------------|---------------------------------------------------------------------------|
| `+cy`   | `--color-ybr`       | Convert to YCbCr (default). With subsampling `+s2` → `YBR_FULL_422`.      |
| `+cr`   | `--color-rgb`       | Keep RGB. Not recommended for lossy — most peers expect YCbCr.            |
| `+cm`   | `--monochrome`      | Convert color → monochrome before encoding.                               |

### YCbCr subsampling

| Flag    | Long form                  | Sampling | Photometric                                           |
|---------|----------------------------|----------|-------------------------------------------------------|
| `+s2`   | `--sample-422`             | 4:2:2    | `YBR_FULL_422` (default; DICOM-conformant).           |
| `+s4`   | `--nonstd-444`             | 4:4:4    | `YBR_FULL` (**non-standard for lossy DICOM**).        |
| `+n2`   | `--nonstd-422-full`        | 4:2:2    | `YBR_FULL` (non-standard).                            |
| `+n1`   | `--nonstd-411-full`        | 4:1:1    | `YBR_FULL` (non-standard).                            |
| `+np`   | `--nonstd-411`             | 4:1:1    | `YBR_FULL_422` (non-standard).                        |

The `+s2` default is what 99% of PACS expect. The non-standard variants exist
only for interop with broken peers — DCMTK warns when you ask for them.

### VOI windowing (monochrome lossy only; ignored with `+tl`)

Same flags as `dcm2img`: `-W` (default off), `+Wi N`, `+Wl N`, `+Wm`, `+Wn`,
`+Wr L T W H`, `+Wh N`, `+Ww C W`. Apply only if you want a window "baked
into" the lossy-compressed pixel data.

### SOP UID handling

| Flag    | Long form          | Effect                                                       |
|---------|--------------------|--------------------------------------------------------------|
| `+ud`   | `--uid-default`    | New SOP Instance UID only if lossy (default).                |
| `+ua`   | `--uid-always`     | Always assign a new SOP Instance UID.                        |
| `+un`   | `--uid-never`      | Never assign a new SOP Instance UID.                         |
| `+cd`   | `--class-default`  | Keep SOP Class UID (default).                                |
| `+cs`   | `--class-sc`       | Rewrite as Secondary Capture (implies `+ua`).                |

### Encapsulation tuning

| Flag    | Long form              | Effect                                                       |
|---------|------------------------|--------------------------------------------------------------|
| `+ff`   | `--fragment-per-frame` | One fragment per frame (default; recommended).               |
| `+fs S` | `--fragment-size S`    | Cap fragment at S kB. Multi-fragment per frame may result.   |
| `+ot`   | `--offset-table-create`| Build a Basic Offset Table (default).                        |
| `-ot`   | `--offset-table-empty` | Leave BOT empty (some viewers don't care).                   |

### Examples

Default lossless (Process 14 SV1) — the safest re-compression:

```bash
dcmcjpeg input.dcm out.dcm
```

Lossy baseline at quality 80 for a color image:

```bash
dcmcjpeg +eb +q 80 input.dcm out.dcm
```

12-bit lossy for a CT (BitsAllocated=16, BitsStored=12):

```bash
dcmcjpeg +ee +q 90 input.dcm out.dcm
```

Convert to Secondary Capture + lossy JPEG when you do not care about
preserving the original IOD (e.g. teaching files):

```bash
dcmcjpeg +eb +q 85 +cs input.dcm out.dcm
```

### Gotchas

- **The default is lossless `+e1`.** Many users assume "JPEG compression"
  means lossy and produce surprisingly large files.
- Specifying both `+eb` and `+bt` (12-bit) is invalid — baseline is 8-bit
  only.
- `+pt N` with N>0 quietly makes "lossless" lossy. Leave it at 0 unless you
  understand the implication.
- The IOD rules are **not** enforced: encoding an MR image with `BitsAllocated=8`
  or an NM image as `YBR_FULL` will silently produce a non-conformant file.
  See the man-page NOTES for SOP-class-specific traps.
- `dcmcjpeg` re-encodes Pixel Data on *every* dataset element, including the
  Icon Image Sequence — so the resulting object is wholly re-compressed.

---

## dcmdjpeg

> Decode a JPEG-encoded DICOM back to an uncompressed transfer syntax. Strict inverse of `dcmcjpeg`.

It is much simpler than the encoder — there is essentially one decision
(output TS) and a small set of compressed-image color-space conversions.

### Synopsis

```
dcmdjpeg [options] dcmfile-in dcmfile-out
```

### Essential flags

| Flag    | Long form                | Effect                                                       |
|---------|--------------------------|--------------------------------------------------------------|
| `+te`   | `--write-xfer-little`    | Output as Explicit-VR LE (default).                          |
| `+tb`   | `--write-xfer-big`       | Output as Explicit-VR BE.                                    |
| `+ti`   | `--write-xfer-implicit`  | Output as Implicit-VR LE.                                    |
| `+cp`   | `--conv-photometric`     | YCbCr → RGB based on photometric interpretation (default).   |
| `+cl`   | `--conv-lossy`           | Always convert lossy-JPEG color to RGB.                      |
| `+cn`   | `--conv-never`           | Never touch the color space.                                 |
| `+pa`   | `--planar-auto`          | Pick planar configuration based on SOP class (default).      |
| `+px`   | `--color-by-pixel`       | Force color-by-pixel.                                        |
| `+pl`   | `--color-by-plane`       | Force color-by-plane.                                        |
| `+bs`/`-bs` | `--bits-stored-fix`/`-keep` | Reconcile or preserve BitsStored mismatches.        |
| `+ud`/`+ua` | `--uid-default` / `--uid-always` | Keep or assign new SOP Instance UID.            |
| `+w6` `+wi` `+wc` | `--workaround-…` | Decoder workarounds (predictor-6 overflow, incomplete fragments, Cornell Huffman bug). |

### Examples

Plain decompress:

```bash
dcmdjpeg input.dcm out.dcm
```

Decompress and force a specific output endianness for downstream tools:

```bash
dcmdjpeg +ti input.dcm out.dcm
```

Decompress while suppressing the YCbCr→RGB conversion:

```bash
dcmdjpeg +cn input.dcm out.dcm
```

### Gotchas

- `dcmdjpeg` does **not** produce a non-DICOM image — output is always a
  DICOM file. For "JPEG-encoded DICOM → PNG" go through `dcm2img` instead
  (one step).
- The default `+te` is Explicit-VR Little-Endian, even if the *input file
  meta header* recorded a different uncompressed TS. Force with `+ti`/`+tb`
  if you need to match the original byte order.

---

## dcmj2pnm

> Deprecated alias for `dcm2img` (the JPEG-decoding-variant ancestor). Flag set identical to `dcm2img`; only the binary name differs.

New code should call `dcm2img`. The 3.7 binary is a thin shim that points
back here.

---

## dcmcjpls

> Encode an uncompressed DICOM with JPEG-LS (lossless or near-lossless).

JPEG-LS gives much better lossless ratios than JPEG-Lossless Process 14 for
most medical images, especially CT and CR. The tool surface is small — the
only thing most users tune is lossless vs near-lossless and the NEAR
parameter.

### Synopsis

```
dcmcjpls [options] dcmfile-in dcmfile-out
```

### Process selection

| Flag    | Long form                 | Output TS                                              | Notes                |
|---------|---------------------------|--------------------------------------------------------|----------------------|
| `+el`   | `--encode-lossless`       | JPEG-LS Lossless (1.2.840.10008.1.2.4.80)              | **Default**.         |
| `+en`   | `--encode-nearlossless`   | JPEG-LS Lossy / Near-Lossless (1.2.840.10008.1.2.4.81) | NEAR set via `+md`.  |

### Near-lossless tuning

| Flag    | Long form                 | Range / Default        | Effect                                                |
|---------|---------------------------|------------------------|-------------------------------------------------------|
| `+md D` | `--max-deviation D`       | int, default 2         | NEAR parameter: maximum absolute error per pixel.    |

NEAR = 0 is mathematically lossless. NEAR = 1..3 is usually visually
indistinguishable. NEAR > 5 starts showing artefacts at diagnostic display.

### Advanced compression tuning (rarely changed)

| Flag    | Long form                 | Effect                                                          |
|---------|---------------------------|-----------------------------------------------------------------|
| `+t1 N` | `--threshold1 N`          | Regional gradient threshold 1.                                  |
| `+t2 N` | `--threshold2 N`          | Threshold 2.                                                    |
| `+t3 N` | `--threshold3 N`          | Threshold 3.                                                    |
| `+rs N` | `--reset N`               | Run-mode reset interval (default 64).                           |

Defaults are derived from bits-per-sample and almost always best left alone.

### Encoder mode (lossless only)

| Flag    | Long form              | Effect                                                            |
|---------|------------------------|-------------------------------------------------------------------|
| `+pr`   | `--prefer-raw`         | Raw encoder — encode the pixel cell exactly as read (default).    |
| `+pc`   | `--prefer-cooked`      | Cooked encoder — split overlay bits to (60xx,3000) and encode only the stored bits. |

### Interleave mode

| Flag    | Long form                  | Effect                                                          |
|---------|----------------------------|-----------------------------------------------------------------|
| `+il`   | `--interleave-line`        | Line-interleaved (default).                                     |
| `+is`   | `--interleave-sample`      | Sample-interleaved.                                             |
| `+iv`   | `--interleave-default`     | Pick the mode that requires no conversion of the source.        |

### Padding, SOP, encapsulation

| Flag    | Long form              | Effect                                                          |
|---------|------------------------|-----------------------------------------------------------------|
| `+ps`   | `--padding-standard`   | Pad odd-length bitstreams with extended EOI marker (DICOM-correct; default). |
| `+pz`   | `--padding-zero`       | Pad with zero byte (non-conformant; for HP LOCO interop only).  |
| `+ff`   | `--fragment-per-frame` | One fragment per frame (default).                               |
| `+fs S` | `--fragment-size S`    | Cap fragment at S kB.                                           |
| `+ot`/`-ot` | `--offset-table-create` / `--offset-table-empty` | BOT on (default) or empty.        |
| `+cd`/`+cs` | `--class-default` / `--class-sc` | Keep SOP class (default) or rewrite as Secondary Capture. |
| `+ud`/`+ua`/`+un` | `--uid-default` / `--uid-always` / `--uid-never` | SOP Instance UID handling. |

### Examples

Lossless (the typical case):

```bash
dcmcjpls input.dcm out.dcm
```

Near-lossless with NEAR=1 (visually lossless for most modalities):

```bash
dcmcjpls +en +md 1 input.dcm out.dcm
```

More aggressive near-lossless, NEAR=5:

```bash
dcmcjpls +en +md 5 input.dcm out.dcm
```

### Gotchas

- NEAR is set with **`+md`**, not on `+en` directly — `+en 3` is parsed as
  `+en` followed by a stray argument and will error.
- Near-lossless changes the SOP Instance UID by default (`+ud` semantics
  treat near-lossless as lossy).
- Use `+pz` (zero padding) **only** to talk to legacy HP LOCO implementations;
  it produces non-DICOM-conformant bitstreams.

---

## dcmdjpls

> Decode a JPEG-LS-encoded DICOM back to an uncompressed transfer syntax.

Mirror of `dcmdjpeg` but for JPEG-LS. Same shape, same complexity (very
little).

### Synopsis

```
dcmdjpls [options] dcmfile-in dcmfile-out
```

### Essential flags

| Flag    | Long form                 | Effect                                                       |
|---------|---------------------------|--------------------------------------------------------------|
| `+te`   | `--write-xfer-little`     | Output as Explicit-VR LE (default).                          |
| `+tb`   | `--write-xfer-big`        | Output as Explicit-VR BE.                                    |
| `+ti`   | `--write-xfer-implicit`   | Output as Implicit-VR LE.                                    |
| `+pr`   | `--planar-restore`        | Restore planar configuration as in the Planar Configuration attribute (default). |
| `+pa`   | `--planar-auto`           | Pick planar configuration from SOP class + photometric.      |
| `+px`   | `--color-by-pixel`        | Force color-by-pixel.                                        |
| `+pl`   | `--color-by-plane`        | Force color-by-plane.                                        |
| `+ud`/`+ua` | `--uid-default` / `--uid-always` | Keep or assign new SOP Instance UID.            |
| `+wi`   | `--workaround-incpl`      | Tolerate incomplete JPEG-LS fragments.                       |
| `+io`   | `--ignore-offsettable`    | Ignore the Basic Offset Table when decompressing.            |

### Examples

Plain decompress:

```bash
dcmdjpls input.dcm out.dcm
```

Decompress and force Implicit-VR LE on output:

```bash
dcmdjpls +ti input.dcm out.dcm
```

### Gotchas

- `+pr` (planar restore) differs from `dcmdjpeg`'s `+pa` (planar auto) as
  the *default*. If you need round-trip identical planar config, the
  defaults are correct; if you need to normalise across mixed-source data,
  set `+pa` explicitly.
- Like `dcmdjpeg`, this outputs **DICOM**, not PNG. For PNG, use
  `dcm2img` directly on the JPEG-LS file.

---

## dcml2pnm

> Deprecated alias for `dcm2img` (the JPEG-LS-decoding-variant ancestor). Flag set identical to `dcm2img`; only the binary name differs.

Use `dcm2img` for new code. The 3.7 binary is a one-paragraph stub.

---

## See also

- [common-options.md](common-options.md) — shared flag families (logging, input, output dataset/file format).
- [transfer-syntax-uids.md](transfer-syntax-uids.md) — the canonical TS UID table.
- `img2dcm` — the reverse direction: PNG/JPEG/BMP → DICOM (covered in the file-tools reference).
