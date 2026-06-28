# DCMTK Q/R Database and Worklist SCPs (`dcmqrscp`, `dcmqridx`, `wlmscpfs`)

These three tools turn a workstation into a *minimal* DICOM server: a small
Storage + Query/Retrieve SCP backed by the filesystem (`dcmqrscp`), the indexer
that registers files into that server's database (`dcmqridx`), and a Modality
Worklist SCP that serves one DICOM file per worklist item (`wlmscpfs`).

When to actually reach for them:

- **`dcmqrscp`** — you need a tiny test PACS for integration testing of a
  modality/SCU/viewer, or you want a known-good reference SCP to compare
  against. **Not for production.** It has no authentication beyond AE-title
  filtering, no audit trail, no HL7, no DICOMweb, no scheduling, and it will
  *delete* images when its per-AE quota is exceeded. The on-disk format is also
  unique to DCMTK and not portable.
- **`wlmscpfs`** — you need a worklist source for an end-to-end test, and you
  want to author each scheduled procedure step as a plain DICOM file you can
  edit by hand. Production worklist sources are almost always driven from a RIS
  through HL7 ORM messages, not from loose files on disk.
- **`dcmqridx`** — only meaningful in conjunction with `dcmqrscp`: it adds
  pre-existing DICOM files to `dcmqrscp`'s `index.dat`, so they become visible
  to C-FIND / C-MOVE / C-GET *without* re-sending them over the wire.

For a real PACS, use **Orthanc** (lightweight, REST API, plugin ecosystem),
**DCM4CHEE** (full archive with WADO/DICOMweb/HL7), or **ConQuest**. Pick
`dcmqrscp` only when you specifically want a DCMTK-conformant test peer.

For the flags shared with every DCMTK tool (logging, TLS, transfer-syntax
preferences, command files, `DCMDICTPATH`), see
[common-options.md](common-options.md).

---

## `dcmqrscp` — Q/R + Storage SCP test PACS

Acts as both a Storage SCP (receives images, writes them under a configured
storage area, indexes them) and a Q/R SCP (answers C-FIND, satisfies C-MOVE /
C-GET against that index). Forks one child per association by default.

### Synopsis

```
dcmqrscp [options] [port]
```

If `port` is omitted on the command line, the port from the config file is
used.

### Essential flags

| Flag | Effect |
|------|--------|
| `-c FILE`, `--config FILE` | Path to the `dcmqrscp.cfg` config file. Default is `<sysconfdir>/dcmtk-<VER>/dcmqrscp.cfg` (e.g. `/opt/homebrew/Cellar/dcmtk/3.7.0/etc/dcmtk-3.7.0/dcmqrscp.cfg` on Homebrew). |
| `-s`, `--single-process` | Don't fork — handle one association at a time in the parent process. **Use only inside a debugger.** Concurrent SCUs will queue. |
| `--fork` | Fork a child per association (default; not available on Windows). |
| `--allow-shutdown` | Accept a private "shutdown" SOP class (UID `1.2.276.0.7230010.3.4.1915765545.18030.917282194.0`). Lets you stop the server cleanly with an SCU instead of `kill`. **Off by default** — leave it off in any environment where the port is reachable by untrusted peers. |
| `--require-find` | Reject MOVE/GET presentation contexts unless the same association also negotiates the corresponding FIND. (RSNA'93 demo behavior; rarely needed today.) |
| `--no-parallel-store` | Reject parallel STORE PCs for the same AE title. Debug aid; the database backend already serializes via file locking. |
| `--disable-get` | Refuse C-GET. Useful when you want to force clients onto C-MOVE. |
| `-XF`, `--check-find` / `-XM`, `--check-move` | Strict DICOM identifier validation for FIND / MOVE. Default is permissive. Turn on when validating an SCU's conformance. |
| `--move-unrestricted` (default) | C-MOVE destination may be any AE title in the HostTable. |
| `-ZA`, `--move-aetitle` | Restrict C-MOVE destination to the *calling* AE title (move back to sender). |
| `-ZH`, `--move-host` | Restrict destination to the requesting host's IP. |
| `-ZV`, `--move-vendor` | Restrict destination to the calling AE's vendor (from `VendorTable`). |
| `-QP`, `--no-patient-root` / `-QS`, `--no-study-root` / `-QO`, `--no-patient-study` | Disable a specific Q/R information model. Default: all three are enabled. |
| `+ac`, `--access-control` | Enforce `/etc/hosts.allow` + `/etc/hosts.deny` (TCP wrapper). Off by default. |
| `--ignore` | Receive Storage requests but **do not** write/index the files. Useful for soaking up traffic from a misbehaving modality without filling disk. |
| `+xf FILE PROF_IN PROF_OUT`, `--assoc-config-file` | Override the default presentation-context profile with one from an association-configuration file. Required if you want C-GET to negotiate SCP/SCU role correctly, or to support TS / SOP classes outside the built-in defaults. |
| `-pdu N`, `--max-pdu N` | Max receive PDU. Defaults to value in config file. |

Network, TLS, IP-version and transfer-syntax preference flags (`+xe`, `+xs`,
`+tls`, …) follow the standard dcmnet convention — see
[common-options.md](common-options.md).

### Configuration file (`dcmqrscp.cfg`)

This file is mandatory. The default path is set at build time
(`<sysconfdir>/dcmtk-<VER>/dcmqrscp.cfg`); on Homebrew that's typically
`/opt/homebrew/Cellar/dcmtk/<VER>/etc/dcmtk-<VER>/dcmqrscp.cfg`. Override
with `-c FILE`.

The file has four sections — three named tables plus a header of global
parameters:

```
# 1. Global parameters (key = value, one per line)
NetworkTCPPort  = 11112
MaxPDUSize      = 16384
MaxAssociations = 16
# Optional character-set behavior, e.g.:
# SpecificCharacterSet = "ISO_IR 192", override, discard, transliterate

# 2. HostTable: symbolic name -> list of (AET, host, port) triples
HostTable BEGIN
  scanner1  = (CT01,  ct01.example.local,  11112)
  scanner2  = (MR01,  mr01.example.local,  11112)
  scanners  = scanner1, scanner2
HostTable END

# 3. VendorTable: optional grouping of HostTable entries by vendor
VendorTable BEGIN
  "Acme Imaging" = scanners
VendorTable END

# 4. AETable: per-AE storage area + access mode + quota + allowed peers
#    Format: AETitle  StorageDir  Access  (maxStudies, maxBytesPerStudy)  Peers
AETable BEGIN
  TESTSCP   /var/tmp/dcmqrscp/store  RW  (200, 1024mb)  scanners
  READONLY  /var/tmp/dcmqrscp/store  R   (200, 1024mb)  ANY
AETable END
```

Key rules:

- **`HostTable`** entries are `SymbolicName = (AET, hostname, port), ...`.
  `SymbolicName = otherSymbolic, ...` lets you compose groups. **Hostnames
  only — the current implementation will not accept a literal IP address in
  place of a hostname.** Use `/etc/hosts` or DNS aliases if you really need
  to pin a peer to an IP.
- **`AETable`** access flags:
  - `R` — peer may FIND/MOVE/GET only.
  - `W` — peer may STORE only.
  - `RW` — both.
- **Quota** is `(maxStudies, maxBytesPerStudy)`. Sizes accept `kb`, `mb`, `gb`
  suffixes. When the quota is exceeded `dcmqrscp` will **delete the oldest
  study** to make room — never point its storage at a directory you also use
  for anything else.
- **Peers** column: either a HostTable symbolic name, an inline `(host, AET,
  port)` triple list, or the literal `ANY` (no AE-based restriction). Peers
  not in this list are rejected at association time.
- The storage directory must exist *and contain an `index.dat` file* (even an
  empty one — `dcmqrscp` will write to it). On first setup:
  `mkdir -p /var/tmp/dcmqrscp/store && touch /var/tmp/dcmqrscp/store/index.dat`.
- Index-format note: the `index.dat` binary format changed on 2013-07-05.
  Old indexes from pre-2013 builds will not work — re-create with `dcmqridx`
  or re-send all images.

A second config file, `dcmqrprf.cfg` (default in the same directory), holds
association profiles for `--assoc-config-file`.

### Examples

Run on a non-privileged port using a local config:

```
dcmqrscp -v -c ./dcmqrscp.cfg 11112
```

Inspect what's actually happening during a stuck C-MOVE:

```
dcmqrscp -d --single-process -c ./dcmqrscp.cfg 11112
```

(`--single-process` lets you set breakpoints / read logs without children
forking out from under you.)

Restrict C-MOVE so peers can only retrieve to themselves, and require
peers to negotiate FIND before MOVE:

```
dcmqrscp -v --move-aetitle --require-find -c ./dcmqrscp.cfg 11112
```

### Gotchas

- **`index.dat` is per storage area, not per server.** Each `AETable` row
  with its own `StorageArea` gets its own database. Two rows pointing at the
  same directory will fight over the index file.
- **AET filtering happens at association time.** A peer that's not listed
  under any `AETable` row's *Peers* column will see "Association Rejected" —
  not a per-operation error. Always check the peers list first when
  troubleshooting "connection refused"-style failures from your SCU.
- **C-GET requires role negotiation.** The built-in defaults propose Storage
  SOP classes with SCU role only. To make C-GET work you must point
  `--assoc-config-file` at a profile that negotiates SCP-role for the
  relevant Storage SOP classes.
- **Quota deletion is silent.** Setting a low quota during testing will cause
  files to vanish from the index without warning. Use a generous quota
  during development.
- **Default config path is build-time.** If you didn't install DCMTK from the
  same prefix you're running it from (common with multiple Homebrew Cellars
  or vendored builds), always pass `-c` explicitly — the default path
  embedded in the binary may not exist.
- **Not Windows-friendly for forking.** `--fork` is a no-op on Windows;
  expect one association at a time unless you launch multiple processes.
- **Character set handling** is governed by `SpecificCharacterSet` in
  `GlobalParameters` and by the `+Cr`/`-Cr` / `+U8` / `+L1` / `+C` options.
  Without explicit configuration, non-ASCII patient names from a foreign
  modality may come back transliterated or mangled.

---

## `dcmqridx` — register existing files into the dcmqrscp index

`dcmqrscp` does not auto-scan its storage area on startup. Files appear in the
Q/R index only when they arrived over the network *or* you registered them
with `dcmqridx`. Use this after copying a fixture set into a fresh storage
directory.

### Synopsis

```
dcmqridx [options] index-out [dcmfile-in...]
```

- `index-out` — the *storage area directory* (the same path used in the
  `StorageArea` column of the `AETable` row). The tool creates / updates
  `index.dat` inside this directory.
- `dcmfile-in...` — one or more DICOM files to register.

### Essential flags

| Flag | Effect |
|------|--------|
| `-p`, `--print` | List the contents of the existing index file instead of registering new files. |
| `-n`, `--not-new` | Mark registered instances as already-reviewed (instance reviewed status = "NO" → "YES"). Affects the `InstanceAvailability` / new-instance bookkeeping that some SCUs use. |
| `-v`, `--verbose` | Print one line per file as it's registered. Useful during bulk imports. |
| `-d`, `--debug` | Dump every parsed attribute. Use to diagnose "file silently not registered" issues. |

No quota enforcement happens during `dcmqridx` — it temporarily disables the
quota system so no files get deleted while you're indexing.

### Examples

Register a single file into the storage area:

```
dcmqridx -v /var/tmp/dcmqrscp/store /path/to/instance.dcm
```

Bulk-register every DICOM file under a directory (use the shell, not the
tool — `dcmqridx` itself does not recurse):

```
fd -t f -e dcm . /path/to/fixtures | xargs dcmqridx -v /var/tmp/dcmqrscp/store
```

Or with POSIX `find`:

```
find /path/to/fixtures -type f -name '*.dcm' \
  -exec dcmqridx /var/tmp/dcmqrscp/store {} +
```

Inspect what's in the index:

```
dcmqridx --print /var/tmp/dcmqrscp/store
```

### Gotchas

- **No recursion.** Bulk-import requires `find` / `fd` / `xargs`. Forgetting
  this and pointing `dcmqridx` at a directory will silently do nothing useful
  (the directory itself is not a DICOM file).
- **File paths are stored as given.** Relative paths get registered relative
  to the current working directory; the index then breaks the moment
  `dcmqrscp` is run from elsewhere. **Always pass absolute paths.**
- **Files should already be inside the storage area** if you want
  `dcmqrscp`'s quota deletion to actually find and delete them later. If you
  register files outside the storage area, the index points at external
  files that quota cleanup will not touch.
- **Re-registering the same file is not idempotent in all DCMTK versions.**
  Duplicate index entries can appear for the same SOPInstanceUID, with
  unpredictable retrieval behavior. Always start from a clean `index.dat`
  when re-doing a bulk import.
- **Stop `dcmqrscp` before bulk indexing.** The locking is cooperative; a
  live SCP and a `dcmqridx` run against the same `index.dat` can race.

---

## `wlmscpfs` — Modality Worklist SCP backed by files

A Worklist Management SCP (DIMSE C-FIND on the *Modality Worklist Information
Model*, SOP class UID `1.2.840.10008.5.1.4.31`). Each scheduled procedure step
is one DICOM file on disk in a per-AET subdirectory.

### Synopsis

```
wlmscpfs [options] port
```

The port is **required** as a positional argument — there is no config file
default like `dcmqrscp` has.

### Directory layout

`wlmscpfs` looks for worklist files in `<data-files-path>/<CalledAET>/*.dcm`
(or `*.wl`). The `CalledAET` is whatever the SCU put in its "called AE" field
— each modality gets its own subdirectory of worklist items.

```
/var/tmp/wlmscpfs/
├── CT01/
│   ├── 20260601_0900_acc12345.wl
│   └── 20260601_1030_acc12346.wl
└── MR01/
    └── 20260601_1100_acc12347.wl
```

### Essential flags

| Flag | Effect |
|------|--------|
| `-dfp PATH`, `--data-files-path PATH` | Root directory holding the `AETITLE/*.dcm` subtree. Default `.` (current dir — almost never what you want). |
| `-efr`, `--enable-file-reject` | Skip worklist files missing any DICOM Type-1 return key (default). Keeps malformed items out of responses. |
| `-dfr`, `--disable-file-reject` | Include incomplete files anyway. Useful when authoring partial fixtures. |
| `-cs0`, `--return-no-char-set` (default) / `-cs1`, `--return-iso-ir-100` / `-csk`, `--keep-char-set` | What `(0008,0005) SpecificCharacterSet` to put in the response. `--keep-char-set` echoes whatever each file's own header had. |
| `-nse`, `--no-sq-expansion` | Don't auto-fill empty sequences in the C-FIND request. Some SCUs send sparse sequences expecting the SCP to populate keys; this disables that behavior. |
| `-s`, `--single-process` / `--fork` (default) | Same semantics as `dcmqrscp`. |
| `--max-associations N` | Cap on parallel associations (default 50). |
| `-rfp PATH`, `--request-file-path PATH` | Also dump each incoming C-FIND request to `PATH` (in `dcmdump` text format). Useful for capturing what a modality actually sends. |
| `-rff FMT`, `--request-file-format FMT` | Filename template for `-rfp`. Default `#t.dump`. Placeholders: `#a` calling AET, `#c` called AET, `#i` PID, `#p` patient ID, `#t` timestamp. |
| `--no-fail` | Don't error out on a malformed query — return an empty result instead. |
| `--sleep-before SEC` / `--sleep-during SEC` / `--sleep-after SEC` | Inject artificial delay around the matching step. Pair with `-rfp` to "interactively" author a worklist response while the SCU waits. |
| `+ac`, `--access-control` | Enforce `/etc/hosts.allow` + `/etc/hosts.deny`. |

### Authoring a worklist item

A worklist item is just a DICOM file containing the matching + return keys
listed in the man page. The conventional way to create one is to write a
text dump and feed it through `dump2dcm`:

```
# worklist_item.dump  (one tag per line)
(0008,0005) CS [ISO_IR 100]                  # SpecificCharacterSet
(0008,0050) SH [ACC12345]                    # AccessionNumber
(0010,0010) PN [Doe^Jane]                    # PatientName
(0010,0020) LO [PID12345]                    # PatientID
(0010,0030) DA [19800101]                    # PatientBirthDate
(0010,0040) CS [F]                           # PatientSex
(0040,1001) SH [REQ001]                      # RequestedProcedureID
(0040,1003) SH [ROUTINE]                     # RequestedProcedurePriority
(0040,0100) SQ (Sequence with explicit length #=1)
  (fffe,e000) na (Item with explicit length #=5)
    (0008,0060) CS [CT]                      # Modality
    (0040,0001) AE [CT01]                    # ScheduledStationAETitle
    (0040,0002) DA [20260601]                # ScheduledProcedureStepStartDate
    (0040,0003) TM [090000]                  # ScheduledProcedureStepStartTime
    (0040,0009) SH [SPS001]                  # ScheduledProcedureStepID
  (fffe,e00d) na (ItemDelimitationItem)
(fffe,e0dd) na (SequenceDelimitationItem)
```

```
dump2dcm worklist_item.dump /var/tmp/wlmscpfs/CT01/20260601_0900_acc12345.wl
```

The list of matching keys, return keys, and which fields are Type-1
(required) is in the man page's *DICOM Conformance* section — keep that
table handy when authoring fixtures.

### Examples

Run on port 11113 serving items from `/var/tmp/wlmscpfs`:

```
wlmscpfs -v -dfp /var/tmp/wlmscpfs 11113
```

Capture every incoming query while serving — useful for reverse-engineering
what a real modality sends:

```
mkdir -p /var/tmp/wlmscpfs-requests
wlmscpfs -v -dfp /var/tmp/wlmscpfs \
  -rfp /var/tmp/wlmscpfs-requests \
  -rff 'req_#a_#t.dump' \
  11113
```

Interactive authoring loop — wait 30 s before each match so you can drop a
new `.wl` file into the AE directory in response to the request file that
just appeared:

```
wlmscpfs -v -dfp /var/tmp/wlmscpfs \
  -rfp /var/tmp/wlmscpfs-requests \
  --sleep-before 30 \
  11113
```

Smoke-test from another shell with `findscu`:

```
findscu -v -W -aec WLSCP -aet TEST WLM_HOST 11113 query.dump
```

(`-W` selects the Modality Worklist information model.)

### Gotchas

- **Subdirectory per called AE title is mandatory.** A query coming in with
  `-aec WLSCP` only sees files under `<data-files-path>/WLSCP/`. Files placed
  directly under `<data-files-path>` are *not* matched. This is the most
  common "my worklist is empty" cause.
- **No recursion below the AET directory.** Subdirectories of
  `<data-files-path>/<AET>/` are ignored.
- **Type-1 attribute rejection is on by default.** A `.wl` file missing any
  required return key is silently skipped. Add `-dfr` while authoring, then
  remove it once your files are valid.
- **Matching is case-sensitive and uses DICOM VR matching rules.** PN-style
  wildcards (`*`, `?`) work, but only if the SCU sends them; the SCP does
  not "fuzz" matches itself.
- **The SCP never modifies your `.wl` files.** Completed/cancelled steps stay
  visible until you delete the file. There is no MPPS (Modality Performed
  Procedure Step) feedback loop — `wlmscpfs` is read-only.
- **`-rfp` request files are not auto-cleaned.** Combine with `logrotate` or
  a cron job if you leave the server running.
- **Patient ID `#p` placeholder is used verbatim.** A non-ASCII or empty
  Patient ID will produce a broken / empty filename. Stick to safer
  placeholders (`#t`, `#i`, `#a`) in production scripts.
- **Character set:** by default `wlmscpfs` returns no
  `SpecificCharacterSet`. If your `.wl` files contain non-ASCII names, pass
  `-csk` to echo each file's own setting, or `-cs1` to force ISO IR 100.

---

## See also

- [common-options.md](common-options.md) — logging, TLS, IP version,
  transfer-syntax preferences, `DCMDICTPATH`, `@command-files`.
- `findscu` / `movescu` / `getscu` — the SCU side of Q/R, useful for
  exercising `dcmqrscp` end-to-end.
- `storescu` / `dcmsend` — for pushing test data into a fresh `dcmqrscp`
  storage area (alternative to `dcmqridx` when the server is already
  running).
- `dump2dcm` / `dcmdump` — round-trip text format used when authoring
  worklist `.wl` files.
