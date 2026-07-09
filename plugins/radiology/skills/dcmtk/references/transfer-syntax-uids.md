# DICOM Transfer-Syntax UIDs ↔ DCMTK Flags

A flat lookup for the transfer syntaxes you actually see in the wild.
Pair this with [common-options.md](common-options.md) when picking
`-x*` (SCU proposal) / `+t*` (output re-encoding) / `+x*` (read hint) flags.

## Uncompressed

| TS UID                                  | Name                                | DCMTK SCU flag  | DCMTK output flag |
|-----------------------------------------|-------------------------------------|-----------------|-------------------|
| `1.2.840.10008.1.2`                     | Implicit VR Little Endian (the DICOM default) | `-xi`  | `+ti`             |
| `1.2.840.10008.1.2.1`                   | Explicit VR Little Endian            | `-xe`           | `+te`             |
| `1.2.840.10008.1.2.1.99`                | Deflated Explicit VR Little Endian (needs zlib) | `-xd` | `+td`         |
| `1.2.840.10008.1.2.2`                   | Explicit VR Big Endian (retired)     | `-xb`           | `+tb`             |

## JPEG (DCT, 8/12-bit)

| TS UID                          | Name                                                 | SCU flag | Encoder (`dcmcjpeg`) | Decoder (`dcmdjpeg`) |
|---------------------------------|------------------------------------------------------|----------|----------------------|----------------------|
| `1.2.840.10008.1.2.4.50`        | JPEG Baseline (Process 1), 8-bit lossy               | `-xy`    | `+eb`                | reads automatically  |
| `1.2.840.10008.1.2.4.51`        | JPEG Extended (Process 2 & 4), 12-bit lossy          | `-xx`    | `+ee`                | reads automatically  |
| `1.2.840.10008.1.2.4.57`        | JPEG Lossless (Process 14)                           | (none)   | `+el`                | reads automatically  |
| `1.2.840.10008.1.2.4.70`        | JPEG Lossless (Process 14 SV1) — the common lossless | `-xs`    | `+e1`                | reads automatically  |

> Encoder flags per the `dcmcjpeg` man page: `+e1` is the SV1 lossless
> default and `+eb` is baseline — not `+e1`=baseline/`+e7`=SV1 as some
> older docs say. Full table in [image-codecs.md](image-codecs.md).

## JPEG 2000

| TS UID                          | Name                                          | SCU flag | Codec tool       |
|---------------------------------|-----------------------------------------------|----------|------------------|
| `1.2.840.10008.1.2.4.90`        | JPEG 2000 Lossless Only                       | `-xv`    | (no DCMTK encoder; decode with `dcmdjpls` only if Part-15 J2K) |
| `1.2.840.10008.1.2.4.91`        | JPEG 2000 (Lossless or Lossy)                 | `-xw`    | (decode-only)    |

DCMTK does not bundle a JPEG 2000 encoder. If you have to **produce** J2K
DICOM, do it with an external pipeline (e.g., OpenJPEG → `img2dcm`).
For **decoding**, only the JPEG 2000 *Part-1* TS is supported.

## JPEG-LS

| TS UID                          | Name                                | SCU flag | Encoder (`dcmcjpls`) | Decoder (`dcmdjpls`) |
|---------------------------------|-------------------------------------|----------|----------------------|----------------------|
| `1.2.840.10008.1.2.4.80`        | JPEG-LS Lossless                    | `-xt`    | `+el`                | reads automatically  |
| `1.2.840.10008.1.2.4.81`        | JPEG-LS Lossy (Near-Lossless)       | `-xu`    | `+en`                | reads automatically  |

## RLE

| TS UID                          | Name                | SCU flag | Encoder (`dcmcrle`) | Decoder (`dcmdrle`) |
|---------------------------------|---------------------|----------|---------------------|---------------------|
| `1.2.840.10008.1.2.5`           | RLE Lossless        | `-xr`    | (default — no flag) | (default — no flag) |

## MPEG / HEVC video

| TS UID                          | Name                                              | SCU flag |
|---------------------------------|---------------------------------------------------|----------|
| `1.2.840.10008.1.2.4.100`       | MPEG-2 Main Profile / Main Level                  | `-xm`    |
| `1.2.840.10008.1.2.4.101`       | MPEG-2 Main Profile / High Level                  | `-xh`    |
| `1.2.840.10008.1.2.4.102`       | MPEG-4 AVC/H.264 High Profile / Level 4.1         | `-xn`    |
| `1.2.840.10008.1.2.4.103`       | MPEG-4 AVC/H.264 BD-compatible HP / Level 4.1     | `-xl`    |
| `1.2.840.10008.1.2.4.104`       | MPEG-4 AVC/H.264 HP / Level 4.2 — 2D video        | `-x2`    |
| `1.2.840.10008.1.2.4.105`       | MPEG-4 AVC/H.264 HP / Level 4.2 — 3D video        | `-x3`    |
| `1.2.840.10008.1.2.4.106`       | MPEG-4 AVC/H.264 Stereo HP / Level 4.2            | `-xo`    |
| `1.2.840.10008.1.2.4.107`       | HEVC/H.265 Main Profile / Level 5.1               | `-x4`    |
| `1.2.840.10008.1.2.4.108`       | HEVC/H.265 Main 10 Profile / Level 5.1            | `-x5`    |

DCMTK doesn't encode/decode the video bitstreams itself; it stores and
transports them. Encoding/decoding is the caller's job (ffmpeg etc.).

---

## Picking the right `-x*` for SCU work

```
You want to send …                       Use this -x* on storescu / dcmsend
─────────────────────────────────────────────────────────────────────────
Already-uncompressed DICOM, peer unknown   default (no flag)
Already-JPEG-baseline files                -xy
Already-JPEG-lossless (Process 14 SV1)     -xs
Already-RLE files                          -xr
Already-JPEG-LS files                      -xt (lossless) / -xu (lossy)
Already-JPEG-2000 files                    -xv (lossless) / -xw (any)
Implicit-VR-only legacy peer               -xi
```

The SCU never silently transcodes — if you propose a TS the file isn't in,
the association still works but the file is sent in whatever TS the peer
accepts that *matches* the file. Mismatch means "presentation context
rejected" errors. When in doubt, run with `-v` to see the negotiation.

## Picking the right output TS for offline conversion (`dcmconv`)

```
Goal                                       dcmconv flag
─────────────────────────────────────────────────────────────────────────
Normalize byte order to LE explicit (most portable)   +te
Make implicit VR (for ancient toolchains)             +ti
Squeeze size with deflate                             +td   (needs zlib)
```

`dcmconv` cannot encode JPEG/JPEG-LS/RLE — for that you must call the
dedicated codec tool (`dcmcjpeg`, `dcmcjpls`, `dcmcrle`).
