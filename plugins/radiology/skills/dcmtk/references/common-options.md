# DCMTK Common Options

Almost every DCMTK tool shares a baseline set of options. Documenting them here
once keeps the per-tool reference files focused on what makes each tool
unique. When a tool's reference page lists a flag *without* an explanation,
look it up here.

DCMTK's flag convention is unusual and a frequent source of confusion:

```
  -x   ALWAYS a "this OR that" choice — selects a mode
  +x   ALWAYS turns a feature ON (or adds something)
  --x  long form of -x or +x; same semantics
```

So `-xe` and `+xe` are *different flags*, not the same flag in two forms.
`storescu -xe` means "propose little-endian explicit first"; `dcm2img +Fa`
means "enable: all frames". Skim a tool's help once with `--help` to see
which prefix each option uses — guessing will burn you.

---

## General options (essentially every tool)

| Flag                            | Effect                                                                 |
|---------------------------------|------------------------------------------------------------------------|
| `-h`, `--help`                  | Print help and exit. Always read this once per tool — flags vary.      |
| `--version`                     | Print version + which optional libraries (zlib, OpenSSL, libpng…) were linked in. Crucial when troubleshooting "format not supported" errors. |
| `--arguments`                   | Echo the expanded command-line. Useful when wrapping the tool in a script. |
| `-q`, `--quiet`                 | Only fatal errors printed.                                             |
| `-v`, `--verbose`               | Print processing details (associations, file I/O, conversions).        |
| `-d`, `--debug`                 | Verbose + protocol-level traces. The default tool to reach for when something silently misbehaves. |
| `-ll`, `--log-level LEVEL`      | `fatal | error | warn | info | debug | trace`. Finer than `-v`/`-d`.   |
| `-lc`, `--log-config FILE`      | Use a log4cplus-style config file. Lets you route logs to file/syslog. |

`--debug` is more useful than `--verbose` in 90% of debugging sessions —
it shows the actual DICOM PDUs / dataset traversal, not just "I am doing X".

---

## Input file format (all tools that read DICOM files)

| Flag                  | Effect                                                          |
|-----------------------|-----------------------------------------------------------------|
| `+f`, `--read-file`   | Auto-detect: DICOM file format **or** raw dataset. Default.     |
| `+fo`, `--read-file-only` | Require the Part-10 file meta header. Fail if missing.      |
| `-f`, `--read-dataset`| Treat input as a raw dataset (no file meta info). Used for partial dumps. |

If a file came out of a non-conformant source (some legacy modalities, or raw
network captures) you may have to pass `-f` to read it at all. `dcmftest <file>`
tells you whether a file has a valid Part-10 header (`yes`) or not (`no`).

---

## Input transfer-syntax hint (tools that parse pixel data)

By default DCMTK reads the TS UID from the file meta header. These flags only
matter if the header is wrong or missing.

| Flag                       | Effect                                                |
|----------------------------|-------------------------------------------------------|
| `-t=`, `--read-xfer-auto`  | Use the TS from the file meta header (default).       |
| `-td`, `--read-xfer-detect`| Probe the byte stream and guess. Ignore the header.   |
| `-te`, `--read-xfer-little`| Force explicit-VR little-endian.                      |
| `-tb`, `--read-xfer-big`   | Force explicit-VR big-endian.                         |
| `-ti`, `--read-xfer-implicit` | Force implicit-VR little-endian.                   |

---

## Output file format (tools that write DICOM)

| Flag                          | Effect                                                          |
|-------------------------------|-----------------------------------------------------------------|
| `+F`, `--write-file`          | Write Part-10 file format (with file meta header). Default.     |
| `-F`, `--write-dataset`       | Write raw dataset only — no file meta header.                   |
| `+te`, `--write-xfer-little`  | Re-encode output as explicit-VR little-endian.                  |
| `+tb`, `--write-xfer-big`     | Re-encode output as explicit-VR big-endian.                     |
| `+ti`, `--write-xfer-implicit`| Re-encode output as implicit-VR little-endian.                  |
| `+td`, `--write-xfer-deflated`| Deflated explicit-VR LE (needs zlib).                           |
| `+u`, `--enable-new-vr`       | Allow UN / UT / UC / UR / OD / OF / OL / OV / SV / UV (default).|
| `-u`, `--disable-new-vr`      | Downgrade unknown VRs to OB. Use for talking to ancient peers.  |

For lossy/lossless **compression** as an output transfer syntax, use the
dedicated codec tools (`dcmcjpeg`, `dcmcjpls`, `dcmcrle`) rather than asking a
general tool to recompress — the codec tools have the quality/process knobs.

---

## Network options (all dcmnet tools: storescu/scp, findscu, movescu, getscu, echoscu, dcmsend, dcmrecv)

### IP version

| Flag              | Effect                                                  |
|-------------------|---------------------------------------------------------|
| `-i4`, `--ipv4`   | IPv4 only (default).                                    |
| `-i6`, `--ipv6`   | IPv6 only.                                              |
| `-i0`, `--ip-auto`| DNS-based: try whatever the lookup returns.             |

### Application Entity titles

| Flag                      | Default        | Effect                                              |
|---------------------------|----------------|-----------------------------------------------------|
| `-aet`, `--aetitle AET`   | tool-specific (e.g., `STORESCU`, `MOVESCU`) | This side's *calling* AE title. |
| `-aec`, `--call AET`      | `ANY-SCP`      | The peer's *called* AE title. Many PACS reject associations whose `-aec` doesn't match their configured AE title exactly. |
| `-aem`, `--move AET`      | the calling AET| **C-MOVE only**: AE title that should be the destination of the moved instances. The destination AE must be pre-registered on the PACS. |

**AE title rules.** Max 16 characters, uppercase ASCII letters + digits +
`._-` only, no leading/trailing spaces. If your AET contains a hyphen or
underscore some peers will trim it — always check what the peer's logs see.

### Timeouts

| Flag                          | Default   | Effect                                            |
|-------------------------------|-----------|---------------------------------------------------|
| `-to`, `--timeout SEC`        | unlimited | Connection request timeout.                       |
| `-ts`, `--socket-timeout SEC` | 60        | Network socket idle timeout. Set 0 to disable.    |
| `-ta`, `--acse-timeout SEC`   | 30        | Association control (negotiation) timeout.        |
| `-td`, `--dimse-timeout SEC`  | unlimited | Per-DIMSE-message timeout. Set this if a hung SCP could otherwise pin you forever. |

### Association sizing

| Flag                              | Default | Range          | Effect                                  |
|-----------------------------------|---------|----------------|-----------------------------------------|
| `-pdu`, `--max-pdu BYTES`         | 16384   | 4096–131072    | Max PDU we'll accept on receive.        |
| `--max-send-pdu BYTES`            | unset   | 4096–131072    | Cap on outgoing PDU. Set if peer can't handle larger PDUs. |

If a peer rejects with `Association Aborted: Maximum PDU Length` you've
either proposed too large a `--max-pdu` or the peer's own cap is below
your minimum. Drop to 16384 and work upward.

---

## Transfer-syntax negotiation (storescu, dcmsend, movescu)

The `-x*` family on **SCU** tools controls *what TS we propose*; the peer
chooses one. Default: propose all uncompressed TS, explicit VR first.

| Flag                       | Proposes                                                          |
|----------------------------|-------------------------------------------------------------------|
| `-x=`, `--propose-uncompr` | All uncompressed TS, explicit VR with local byte order first. **Default.** |
| `-xe`, `--propose-little`  | All uncompressed TS, explicit VR LE first.                        |
| `-xb`, `--propose-big`     | All uncompressed TS, explicit VR BE first.                        |
| `-xi`, `--propose-implicit`| Implicit VR LE **only**.                                          |
| `-xs`, `--propose-lossless`| JPEG Lossless (Process 14 SV1) + uncompressed fallback.          |
| `-xy`, `--propose-jpeg8`   | JPEG Process 1 (8-bit lossy) + uncompressed.                      |
| `-xx`, `--propose-jpeg12`  | JPEG Process 2/4 (12-bit lossy) + uncompressed.                   |
| `-xv`, `--propose-j2k-lossless` | JPEG 2000 Lossless + uncompressed.                           |
| `-xw`, `--propose-j2k-lossy`    | JPEG 2000 Lossy + uncompressed.                              |
| `-xt`, `--propose-jls-lossless` | JPEG-LS Lossless + uncompressed.                             |
| `-xu`, `--propose-jls-lossy`    | JPEG-LS Lossy + uncompressed.                                |
| `-xm`, `--propose-mpeg2`        | MPEG-2 Main@Main only (no fallback).                         |
| `-xn`, `--propose-mpeg4`        | MPEG-4 AVC/H.264 HP/L4.1 only.                               |
| `-x4`, `--propose-hevc`         | HEVC/H.265 Main@L5.1 only.                                   |
| `-xr`, `--propose-rle`          | RLE Lossless + uncompressed.                                 |
| `-xd`, `--propose-deflated`     | Deflated explicit VR LE + uncompressed (needs zlib).         |
| `-R`,  `--required`             | Only propose presentation contexts the input files actually need. |
| `+C`,  `--combine`              | One presentation context per abstract syntax with multiple TS, instead of one PC per TS. Saves PC slots when sending many SOP classes. |

If you don't know what the peer accepts and you don't want to send already-
compressed bytes, leave the default. If your inputs are already JPEG-encoded,
pick the matching `-x*` so DCMTK doesn't transparently transcode.

For the actual TS UIDs see [transfer-syntax-uids.md](transfer-syntax-uids.md).

---

## TLS options (all dcmnet tools)

DCMTK supports DICOM-TLS when built against OpenSSL. Check
`echoscu --version` for `with OpenSSL`. If absent, none of the `+tls` flags
exist on your binary.

| Flag                                       | Effect                                              |
|--------------------------------------------|-----------------------------------------------------|
| `-tls`, `--disable-tls`                    | Plain TCP/IP (default).                             |
| `+tls KEY CERT`, `--enable-tls KEY CERT`   | Authenticated TLS with your key + cert.             |
| `+tla`, `--anonymous-tls`                  | TLS without certificate. Most peers reject this.    |
| `+cf FILE`, `--add-cert-file FILE`         | Trust this CA / peer cert file.                     |
| `+cd DIR`, `--add-cert-dir DIR`            | Trust all certs in this directory.                  |
| `-ic`, `--ignore-peer-cert`                | Disable peer verification. Diagnostic only.         |
| `+ph`, `--list-profiles`                   | List supported TLS profiles and exit.               |
| `+pg`, `--profile-8996`                    | BCP 195 RFC 8996 TLS profile (default; current).    |

When debugging TLS handshake failures: start with `+ph` to confirm the
profile you want is even compiled in, then use `-ic` *just* to isolate
"is it a cert problem or a profile problem" — never leave `-ic` on in
production.

---

## Logging configuration file

The `-lc FILE` option (everywhere) takes a log4cplus-style config. Example
that writes everything to a rotating file:

```ini
log4cplus.rootLogger = INFO, FILE

log4cplus.appender.FILE = log4cplus::RollingFileAppender
log4cplus.appender.FILE.File = /var/log/dcmtk.log
log4cplus.appender.FILE.MaxFileSize = 10MB
log4cplus.appender.FILE.MaxBackupIndex = 5
log4cplus.appender.FILE.layout = log4cplus::PatternLayout
log4cplus.appender.FILE.layout.ConversionPattern = %D{%Y-%m-%d %H:%M:%S} %-5p %c - %m%n
```

The DCMTK source ships an example at `<etcdir>/logger.cfg`.

---

## Environment variables

| Variable        | Used by                          | Purpose                                                   |
|-----------------|----------------------------------|-----------------------------------------------------------|
| `DCMDICTPATH`   | every tool                       | Colon-separated list of data dictionary files. If unset, the default `<datadir>/dicom.dic` is loaded (Windows builds typically have it compiled-in). |
| `TCP_NODELAY`   | network tools                    | If set to `1`, disables Nagle on association sockets.     |
| `TMPDIR` / `TEMP` / `TMP` | tools that create temp files | Standard meaning.                                  |

If a tool errors with "no data dictionary loaded" your install is broken or
`DCMDICTPATH` points somewhere wrong. On macOS Homebrew, the dictionary lives
under `/opt/homebrew/share/dcmtk/dicom.dic`.

---

## Command files (`@filename`)

Every DCMTK tool accepts arguments via a command file:

```
storescu @opts.txt PACS_HOST PACS_PORT study.dcm
```

with `opts.txt` containing:

```
-v
-aet MYSCU
-aec PACS
--max-pdu 32768
```

Whitespace is treated as a separator (use quotes for values with spaces).
Command files **cannot** include other command files. Useful for keeping
long invocations readable in scripts and Makefiles.
