# DCMTK Signing and Radiotherapy Tools (`dcmsign`, `drtdump`)

Two unrelated tools grouped here because each is small.

- **`dcmsign`** — create, verify, and remove DICOM Digital Signatures (DICOM
  Part 15, Supplement 41). Reach for it when:
  - You need *provenance* / *trust* on stored DICOM objects — e.g. an
    FDA-cleared AI workflow that has to prove "this report came from this
    algorithm with this version, signed by this key" at audit time.
  - You're implementing or testing an IHE *Document Digital Signature* (DSG)
    or *ATNA*-adjacent workflow that requires signed Structured Reports.
  - You need a quick CLI to verify a counterparty's signed DICOM object
    against their certificate before ingesting it.
  - You're investigating an unexpected dataset change and want to see whether
    a present signature still validates over the current bytes.

  Note: `dcmsign` requires DCMTK to be built with OpenSSL. Confirm with
  `dcmsign --version` and look for "with OpenSSL" — if it's not there, none
  of the signature commands exist on your binary.

- **`drtdump`** — semantic dump of an RT (radiotherapy) DICOM object: RT
  Plan, RT Structure Set, RT Dose, RT Image, RT Treatment Record. Reach for
  it when you want a human-readable view of a plan/contours/dose object for
  radiation-oncology QA. `dcmdump` shows the raw bytes; `drtdump` shows the
  RT-specific module structure (beams, control points, contour sequences,
  fraction groups, …) at a level closer to how a planning system thinks
  about the object.

For shared flags (logging, input/output file format, transfer syntax,
command files, `DCMDICTPATH`) see [common-options.md](common-options.md).

---

## `dcmsign` — sign and verify DICOM digital signatures

`dcmsign` reads a DICOM file, performs one signature operation
(create / verify / remove / insert-timestamp), and — if it modified the
dataset — writes the result to an output file. The output filename is
*optional* for verify-only runs, *required* otherwise.

The DICOM signature mechanism (Part 15, derived from Supplement 41) wraps
a per-signature MAC over a normalized serialization of a selected attribute
set, embeds the result as a Digital Signatures Sequence `(0400,0500)` item,
and attaches the signer's X.509 certificate. Multiple signatures (different
profiles, different keys) can coexist on one object.

### Synopsis

```
dcmsign [options] dcmfile-in [dcmfile-out]
```

Use `-` for stdin / stdout.

### The five operations

| Flag | Operation |
|------|-----------|
| `--verify` (default) | Verify every signature present. Exits non-zero if any signature fails. |
| `+s KEY CERT`, `--sign KEY CERT` | Create a new signature in the **main dataset**. Both args required. |
| `+si KEY CERT LOC`, `--sign-item KEY CERT LOC` | Create a new signature inside a *sequence item*. `LOC` is a path like `ReferencedSeriesSequence[0].ReferencedImageSequence[1]`. |
| `+r UID`, `--remove UID` | Remove one signature, identified by its DigitalSignatureUID. |
| `+ra`, `--remove-all` | Remove every signature from the dataset. |
| `+t TSQ TSR UID`, `--insert-timestamp TSQ TSR UID` | Attach an RFC 3161 timestamp response to an existing signature. |

### Essential flags

#### Input (defaults under [common-options.md](common-options.md))

| Flag | Effect |
|------|--------|
| `+f`, `--read-file` | Auto-detect file vs raw dataset (default). |
| `+fo`, `--read-file-only` | Require a Part-10 file meta header. |
| `-f`, `--read-dataset` | Treat input as a raw dataset. |

#### Key / certificate format

| Flag | Effect |
|------|--------|
| `-pem`, `--pem-keys` | Read keys/certs as PEM (default; supports password-protected private keys). |
| `-der`, `--der-keys` | Read keys/certs as DER. |
| `+ps`, `--std-passwd` | Prompt for the private-key password on stdin (default; only with `--sign` / `--sign-item`). |
| `+pw PW`, `--use-passwd PW` | Pass the password on the command line. **Avoid** — visible to `ps`. |
| `-pw`, `--null-passwd` | Use an empty password. Only safe for test keys. |

#### Hash / MAC algorithm (only with `--sign` / `--sign-item`)

| Flag | MAC |
|------|-----|
| `+mr`, `--mac-ripemd160` | RIPEMD-160 (**default** in DCMTK 3.7) |
| `+ms`, `--mac-sha1` | SHA-1 |
| `+mm`, `--mac-md5` | MD5 |
| `+m2`, `--mac-sha256` | SHA-256 |
| `+m3`, `--mac-sha384` | SHA-384 |
| `+m5`, `--mac-sha512` | SHA-512 |

In 2026, **prefer `+m2` / `+m3` / `+m5`**. RIPEMD-160 is the DICOM default
for legacy compatibility, but SHA-2 is what every modern verifier actually
trusts. MD5 and SHA-1 are present only for backward-compatibility and should
not be used for new signatures.

#### Signature profile (only with `--sign` / `--sign-item`)

| Flag | Profile |
|------|---------|
| `-pf`, `--profile-none` | No profile — just sign whatever tags you list (default). |
| `+pb`, `--profile-base` | Base RSA Digital Signature Profile (Part 15 §C.1). Minimum required attribute set. |
| `+pc`, `--profile-creator` | Creator RSA Digital Signature Profile — "signed by the creating application". |
| `+pa`, `--profile-auth` | Authorization Digital Signature Profile — "signed by an authorizing physician". |
| `+pr`, `--profile-sr` | Structured-Report RSA Profile (signing for SR documents). |
| `+pv`, `--profile-srv` | SR RSA Profile, verification side. |

A profile silently *adds* the attributes it requires to whatever tag list
you specify with `--tag` / `--tag-file`.

#### Verification (only with `--verify`)

| Flag | Effect |
|------|--------|
| `+rv`, `--verify-if-present` | Verify if a signature is present; pass otherwise (default). |
| `+rg`, `--require-sig` | Fail if no signature at all. |
| `+rc`, `--require-creator` | Fail unless a Creator RSA signature is present. |
| `+ru`, `--require-auth` | Fail unless an Authorization signature is present. |
| `+rs`, `--require-sr` | Fail unless an SR RSA signature is present. |
| `+cf FILE`, `--add-cert-file FILE` | Add a trusted CA cert to the store. |
| `+uf FILE`, `--add-ucert-file FILE` | Add an *untrusted* intermediate CA cert (for chain building). |
| `+cd DIR`, `--add-cert-dir DIR` | Add a hashed certificate directory (filenames `hash.N`, `hash.rN`). |
| `+cr FILE`, `--add-crl-file FILE` | Add a CRL file (implies `--enable-crl-vfy`). |
| `+cl`, `--enable-crl-vfy` | Require CRL presence for each CA during verification. |

#### Timestamp creation (RFC 3161, only with `--sign` / `--sign-item`)

| Flag | Effect |
|------|--------|
| `-ts`, `--timestamp-off` | Don't generate a timestamp request (default). |
| `+ts TSQ UID`, `--timestamp-file TSQ UID` | Write a Time-Stamp Query to `TSQ` and the signature's UID to `UID`. You then take `TSQ` to a TSA out-of-band, receive a TSR, and feed it back with `--insert-timestamp`. |
| `+tm2` / `+tm3` / `+tm5` | TSQ digest algorithm SHA-256 / SHA-384 / SHA-512. |
| `+tn` (default) / `-tn` | Include / omit nonce in the TSQ. |
| `+tc` (default) / `-tc` | Request the TSA certificate be embedded in the TSR. |
| `+tp OID`, `--ts-policy OID` | Request a specific TSA policy OID. |

#### Tag selection (only with `--sign` / `--sign-item`)

| Flag | Effect |
|------|--------|
| `-t TAG`, `--tag TAG` | Add one tag to the signature attribute list. `TAG` is `gggg,eeee` or a dictionary name. Can be repeated. |
| `-tf FILE`, `--tag-file FILE` | Read tags from a plaintext file (one per line). |

Default behavior with no `--tag` and `--profile-none` is to sign **all
elements** in the dataset/item.

#### Output

Standard output options (`+t=`, `+te`, `+tb`, `+ti`, `+e`/`-e`) — see
[common-options.md](common-options.md).

| Flag | Effect |
|------|--------|
| `+d FILE`, `--dump FILE` | Dump the canonical byte stream that was fed into the MAC. Lets you diff what was actually hashed when investigating "valid yesterday, invalid today" failures. |

### Exit codes worth checking in scripts

| Code | Meaning |
|------|---------|
| `0` | Success / verification passed |
| `1` | Command-line syntax error |
| `5` | DCMTK built without OpenSSL |
| `20`–`33` | Input file / tag / TSQ / TSR / UID file errors |
| `40` / `46` | Output file errors |
| `80`–`87` | Processing errors (sign / remove / TS failed) |
| `100` | No signatures present (with `--require-sig`) |
| `101` | Signature verification failed (cryptographic mismatch) |
| `102` | Verification policy violated (e.g. `--require-creator` not met) |

A script wrapping `dcmsign --verify` should treat `100`–`102` distinctly:
`100` means "nothing to verify", `101` means "tamper detected", `102` means
"valid signature but not the kind we required".

### Examples

Verify all signatures in a file using a trusted CA bundle:

```
dcmsign --verify \
  +cf /path/to/ca-bundle.pem \
  signed_input.dcm
```

Sign with SHA-256, the Creator profile, embedded password:

```
dcmsign +s /path/to/signer.key /path/to/signer.crt \
  +m2 +pc \
  +ps \
  input.dcm signed_output.dcm
```

(Prompts for the private-key password on stdin.)

Sign a specific subset of tags using a tag-list file:

```
dcmsign +s signer.key signer.crt \
  +m2 \
  -tf signing_tags.txt \
  input.dcm signed_output.dcm
```

with `signing_tags.txt`:

```
PatientID
PatientName
StudyInstanceUID
SeriesInstanceUID
SOPInstanceUID
(0040,a730)
```

Sign an item deep inside a sequence (signs the second referenced image
under the first referenced series):

```
dcmsign +si signer.key signer.crt \
  'ReferencedSeriesSequence[0].ReferencedImageSequence[1]' \
  +m2 \
  input.dcm signed_output.dcm
```

Remove all signatures (audit / re-sign workflow):

```
dcmsign +ra input.dcm unsigned_output.dcm
```

Two-step certified timestamp:

```
# 1. Sign and emit a TSQ + UID file
dcmsign +s signer.key signer.crt +m2 \
  +ts request.tsq sig.uid \
  input.dcm signed_output.dcm

# 2. (Out-of-band: send request.tsq to TSA, receive response.tsr)

# 3. Attach the TSR back to the signature identified by sig.uid
dcmsign +t request.tsq response.tsr sig.uid \
  signed_output.dcm signed_output_with_ts.dcm
```

### Gotchas

- **Built without OpenSSL → no signature commands.** Always check
  `dcmsign --version` first. Exit code 5 if you call it on a non-OpenSSL
  build.
- **Default MAC is RIPEMD-160**, not SHA-256. Almost every modern verifier
  prefers SHA-256+ — pass `+m2` (or stronger) explicitly for new signatures.
- **Don't pass private-key passwords via `+pw`.** They show up in `ps -ef`,
  shell history, syslog, and container logs. Use the default `+ps` and pipe
  the password in, or store the key unencrypted on a path with strict file
  permissions if the threat model allows.
- **`--sign-item` location strings are zero-indexed.** First item is `[0]`,
  not `[1]`. Off-by-one here silently signs the wrong item.
- **A signature covers a normalized byte stream**, not the file as written.
  Re-encoding the file with a different transfer syntax (e.g. via `dcmconv`
  +te → +ti) **breaks** the signature only if the change touches the signed
  attributes' encoding. Use `+d` to capture the canonical stream when
  debugging.
- **Pixel-data signatures are sensitive to compression changes.** Any
  recompression (`dcmcjpeg`, `dcmcrle`, …) of signed pixel data will
  invalidate any signature that includes `(7FE0,0010) PixelData`.
- **CRL verification is opt-in.** Without `+cl` / `+cr`, revoked certs are
  silently accepted. For any production verification path, supply a CRL.
- **Hashed cert directory format is OpenSSL's.** Filenames must be
  `<hash>.N` for certs and `<hash>.rN` for CRLs, with `<hash>` from
  `openssl x509 -hash -noout` / `openssl crl -hash -noout`. `c_rehash`
  produces this layout automatically.
- **Signature format compatibility.** Use the default `-fn` (new format).
  `-fo` exists only to verify legacy signatures created with DCMTK before
  3.5.4 and is non-conformant when the dataset contains compressed pixel
  data.

---

## `drtdump` — structured dump of RT DICOM objects

A semantic, RT-aware textual dump. Behavior depends on the SOP class of
the input:

| SOP class | UID | What `drtdump` shows |
|-----------|-----|---------------------|
| RT Image | `1.2.840.10008.5.1.4.1.1.481.1` | Header attributes, image module, RT-image-specific geometry (gantry / collimator / table angles, isocenter). |
| RT Dose | `1.2.840.10008.5.1.4.1.1.481.2` | Dose units, dose type, normalization, dose grid scaling, DVH sequences, referenced RT Plan UIDs. |
| RT Structure Set | `1.2.840.10008.5.1.4.1.1.481.3` | Structure Set ROI Sequence (ROI name, number, generation algorithm), Contour Sequences (per ROI: contour geometric type, point count, image references), RT ROI Observations. |
| RT Plan | `1.2.840.10008.5.1.4.1.1.481.5` | Prescription, Fraction Group Sequence (fractions × beams × meterset), Beam Sequence (per beam: machine, energy, control points, MLC leaf positions, MU). |
| RT Treatment Summary Record | `1.2.840.10008.5.1.4.1.1.481.7` | Per-fraction delivered MU, treatment session details. |
| RT Ion Plan | `1.2.840.10008.5.1.4.1.1.481.8` | Same shape as RT Plan, with ion-beam-specific fields (range shifters, snouts, scan spots). |
| RT Ion Beams Treatment Record | `1.2.840.10008.5.1.4.1.1.481.9` | Delivered ion-beam fractions. |

Other RT SOP classes (e.g. RT Brachy records, the newer Supplement-147
radiation objects) are accepted by the parser but rendered with the
generic-DICOM fallback, similar to `dcmdump`.

### Synopsis

```
drtdump [options] drtfile-in...
```

Multiple input files allowed. Use `-` for stdin.

### Essential flags

| Flag | Effect |
|------|--------|
| `+Pf`, `--print-filename` | Print a header line with the filename before each file's dump. Required when piping multiple files to a single output stream. |
| `+f` / `+fo` / `-f` | Input file format selection — see [common-options.md](common-options.md). |
| `-t=` / `-td` / `-te` / `-tb` / `-ti` | Input transfer-syntax override — see [common-options.md](common-options.md). |
| `-v`, `--verbose` / `-d`, `--debug` | Normal DCMTK logging levels. `-v` adds per-file progress; `-d` adds parser-level traces (useful when the file fails to parse). |

No write options — `drtdump` only emits text to stdout.

### Examples

Dump a single RT Plan:

```
drtdump rtplan.dcm | less
```

Inspect every RT object in a directory, with filename headers:

```
fd -t f -e dcm . /path/to/rt-fixtures | xargs drtdump +Pf | less
```

Save a structured dump alongside the source file (one per file):

```
for f in /path/to/rt/*.dcm; do
  drtdump "$f" > "${f%.dcm}.txt"
done
```

Pipe a stream through `drtdump` (e.g. straight out of a network capture
that was post-processed with `dcmconv`):

```
dcmconv input.dcm - | drtdump -
```

### Gotchas

- **`drtdump` is read-only and semantic.** If the file is malformed in a
  way that breaks the RT module loader (missing required sequence, bad
  reference UID), `drtdump` will refuse to dump it cleanly. Fall back to
  `dcmdump` to see the raw bytes.
- **Output is not machine-stable across DCMTK versions.** It's a
  human-oriented hierarchical view; don't grep it as a structured
  interchange format. For programmatic access, parse the DICOM directly
  (pydicom, the DCMTK `drt*` C++ API, etc.).
- **No filtering / selection options.** You get the entire object dump.
  Combine with `grep`, `awk`, or `rg` to extract specific sections (beams,
  ROIs, …).
- **RT Image objects look more like generic image objects** in the dump
  than RT Plan / RT Structure Set objects do. The RT-specific value-add
  is largest for Plan / Structure Set / Dose.
- **Use `dcmdump` for non-RT objects.** `drtdump` will still load them but
  the RT-specific output paths are skipped, so you get nothing
  `dcmdump --print` wouldn't already give you.

---

## See also

- [common-options.md](common-options.md) — input/output file format, transfer
  syntax, logging, `DCMDICTPATH`, `@command-files`.
- `dcmdump` — generic byte-level DICOM dump. Use alongside `drtdump` when
  diagnosing parsing issues.
- `dcmconv` — convert between transfer syntaxes (e.g. before signing /
  verifying when the input encoding is ambiguous).
- DICOM Part 15 (Security and System Management Profiles) and Supplement 41
  for the digital-signature framework, signature profiles, and the
  normalized-serialization rules `dcmsign` implements.
- DICOM Part 3 §A.8 / Supplement 11 for the RT object information modules
  `drtdump` knows how to render.
