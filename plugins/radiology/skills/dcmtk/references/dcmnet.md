# DCMTK Network Tools (dcmnet)

The `dcmnet` module ships DCMTK's DIMSE command-line tools — every program
that speaks DICOM over a TCP/IP association. Each tool sits at one corner of
the DIMSE service map:

```
Tool         Service Class    DIMSE      Role
─────────────────────────────────────────────────────────────────────────
echoscu      Verification     C-ECHO     SCU
storescu     Storage          C-STORE    SCU
storescp     Storage          C-STORE    SCP
dcmsend      Storage          C-STORE    SCU  (simpler, batch-oriented)
dcmrecv      Storage          C-STORE    SCP  (simpler, modern)
findscu      Q/R + MWL        C-FIND     SCU
movescu     Q/R              C-MOVE     SCU  (peer pushes to a 3rd AE)
getscu      Q/R              C-GET      SCU  (peer pushes back same assoc)
termscu      DCMTK-private    N-ACTION   SCU  (graceful shutdown of DCMTK SCPs)
```

**SCU vs SCP.** Every DICOM service is split into a User (SCU, the client
that *requests* the operation) and a Provider (SCP, the server that *performs*
it). A single program may play both roles in one workflow — `movescu` is the
canonical example: it acts as an SCU when sending the C-MOVE request to the
PACS, then immediately switches hats and acts as a Storage SCP to receive the
images the PACS pushes back. The same goes for `getscu`, which uses C-STORE
sub-operations *over the same association* it opened for the C-GET.

**Association negotiation and presentation contexts.** Before any DIMSE
message flies, the two AEs negotiate an *association*: AE titles, max PDU
size, and a list of *presentation contexts*. Each presentation context binds
an abstract syntax (SOP Class UID — e.g. CT Image Storage) to one or more
transfer syntaxes (encoding UIDs — e.g. JPEG 2000 Lossless). The peer picks
**at most one** TS per PC and rejects the rest. If you propose only JPEG-LS
and the PACS only accepts uncompressed LE, every C-STORE will fail with
"no presentation context found". The `-x*` (propose) and `+x*` (prefer)
families control this dance — see
[common-options.md](common-options.md#transfer-syntax-negotiation-storescu-dcmsend-movescu)
for the full list.

For shared flags — `-aet`, `-aec`, `-aem`, timeouts, `--max-pdu`, IP-version
selection, `+x*`/`-x*` TS negotiation, TLS, logging — see
[common-options.md](common-options.md). Those flags are not redocumented
here.

---

## echoscu

> Sends a single DICOM C-ECHO. The fastest way to ask "is that PACS reachable
> and willing to talk to me?".

### Synopsis
```
echoscu [options] peer port
```

### Essential flags
| Flag | Effect |
|------|--------|
| `-aet`, `--aetitle AET` | Calling AE title. Default `ECHOSCU`. |
| `-aec`, `--call AET` | Called AE title (the peer's). Default `ANY-SCP`. Most real PACS reject mismatches. |
| `-pts`, `--propose-ts N` | Propose `N` transfer syntaxes (default: only Implicit VR LE). Use to probe what the SCP accepts. |
| `-ppc`, `--propose-pc N` | Propose `N` *presentation contexts*. Useful for stress-testing PC slot limits. |
| `--repeat N` | Do the C-ECHO `N` times back-to-back. Cheap connectivity smoke test. |
| `--abort` | A-ABORT the association instead of A-RELEASE. Use when testing the peer's abort handling. |
| `-d`, `--debug` | Show the actual A-ASSOCIATE-RQ/AC PDUs — invaluable when the peer rejects you. |

For `-to`/`-ta`/`-td`, IP-version flags, and TLS, see
[common-options.md](common-options.md).

### Examples
```bash
# 1) Bare connectivity check (uses default AE titles).
echoscu PACS_HOST PACS_PORT

# 2) Strict check: the peer's AE title and our identity must match what the
#    PACS has configured.
echoscu -aet MY_AET -aec PACS_AET -v PACS_HOST PACS_PORT

# 3) Diagnose a rejected association — show the PDU trace.
echoscu -aet MY_AET -aec PACS_AET -d PACS_HOST PACS_PORT
```

### Gotchas
- A successful echo only proves the *Verification* SOP class works. It does
  **not** prove the peer will accept your C-STORE — those negotiate completely
  different presentation contexts. Always echo *and* try a real C-STORE with
  one file before declaring victory.
- Many PACS log every association attempt. Hammering `--repeat 10000` on a
  production system will earn you angry mail.
- The default proposed TS is Implicit VR LE only. If a peer rejects you saying
  "no acceptable TS", try `-pts 53` to propose the whole catalog and see which
  one it likes.

---

## storescu

> The battle-tested C-STORE SCU. Reach for it when you need fine control over
> what transfer syntaxes you propose, or are testing a PACS's negotiation
> behavior. For "send this big tree of files and move on with my life", use
> `dcmsend` instead.

### Synopsis
```
storescu [options] peer port dcmfile-in...
```

### Essential flags
| Flag | Effect |
|------|--------|
| `+sd`, `--scan-directories` | Treat directory args as directories to scan (otherwise they're ignored). |
| `+r`, `--recurse` | With `+sd`, recurse into subdirectories. |
| `+sp`, `--scan-pattern P` | Wildcard filter for `+sd` (e.g. `+sp "*.dcm"`). |
| `+rn`, `--rename` | Rename each file `.done` (success) or `.bad` (failure). Crude but useful for resume-on-restart. |
| `-xf`, `--config-file F P` | Read association negotiation profile `P` from `asconfig`-format file `F`. The right way to propose custom SOP-class / TS combos. |
| `+C`, `--combine` | One PC per abstract syntax with multiple TS, instead of one PC per TS. Saves PC slots (max 128 per association). |
| `-R`, `--required` | Only propose PCs the input files actually need. Cuts negotiation overhead on big runs. |
| `-nh`, `--no-halt` | Keep going after a failed C-STORE. Default is to halt on first failure. |
| `+II`, `--invent-instance` | Replace SOP Instance UID with a fresh one for every send. (Plus `+IR`/`+IS`/`+IP` to invent series/study/patient at intervals.) Used for synthetic load tests. |
| `-up`, `--uid-padding` | Silently fix space-padded UIDs from non-conformant sources. |
| `--max-send-pdu N` | Cap *outgoing* PDU size if the peer can't handle the negotiated max. |

For `-x*` TS proposal flags, `-aet`/`-aec`, timeouts, `--max-pdu`, IP-version,
and TLS, see [common-options.md](common-options.md).

### Examples
```bash
# 1) Send one file with explicit AE titles and verbose output.
storescu -v -aet MY_AET -aec PACS_AET PACS_HOST PACS_PORT image.dcm

# 2) Send a whole tree, recursive, mark sent files with .done.
storescu -v +sd +r +rn -aec PACS_AET PACS_HOST PACS_PORT ./studies/

# 3) Propose only JPEG-2000 Lossless (matching pre-compressed inputs so
#    DCMTK does not transparently transcode).
storescu -v -xv +C -R -aec PACS_AET PACS_HOST PACS_PORT *.dcm

# 4) Use a custom negotiation profile (e.g. to add Private SOP classes).
storescu -v -xf myprofile.cfg Default -aec PACS_AET \
         PACS_HOST PACS_PORT *.dcm
```

### Gotchas
- **storescu does not scan directories by default.** A bare
  `storescu peer port ./dir` ignores `./dir`. Add `+sd` (`--scan-directories`)
  and usually `+r` (`--recurse`).
- "Association rejected: too many presentation contexts" → you have more
  than 128 distinct (SOP class × TS) pairs. Add `+C` or `-R`.
- Default behavior is **halt on first failure**. In a batch send that means
  one bad file kills the rest. Pass `-nh`.
- If your inputs are already compressed (e.g. JPEG-2000) and you don't pass
  the matching `-x*` flag, DCMTK will propose uncompressed contexts and the
  SCP may accept them — at which point storescu silently **transcodes**.
  Pass `-xv`/`-xs`/etc. to keep the original encoding.
- `+IS`/`+IP` change patient identifiers. Never use against production PACS.

---

## storescp

> The classic C-STORE SCP. A receiver/listener that writes incoming DICOM
> objects to disk, with rich knobs for directory layout, file naming, and
> post-receive triggers (exec a script when a study finishes).

### Synopsis
```
storescp [options] [port]
```

`port` is required unless `--inetd` is given.

### Essential flags

**Concurrency / lifecycle**

| Flag | Effect |
|------|--------|
| `--fork` | Spawn a child process per association (good for parallel receives). |
| `--single-process` | Default — handle one association at a time. |
| `--max-associations N` | Cap concurrent associations (with `--fork`). |
| `-id`, `--inetd` | Run under inetd / xinetd. The socket is passed in. |
| `-aet`, `--aetitle AET` | Listener AE title. Default `STORESCP`. |
| `+ac`, `--access-control` | Enforce `/etc/hosts.allow` & `/etc/hosts.deny` (TCP wrappers). |

**TS preference (what we accept)**

| Flag | Effect |
|------|--------|
| `+x=`, `--prefer-uncompr` | Prefer explicit VR local-byte-order (default). |
| `+xa`, `--accept-all` | Accept everything DCMTK supports including all compressed TS. The right default for a generic test receiver. |
| `+xs` / `+xv` / `+xy` / `+xr` / ... | Prefer a specific lossy/lossless TS (analogous to storescu's `-x*` set). |
| `-xf`, `--config-file F P` | Use negotiation profile `P` from `asconfig` file `F` — required for SOP classes outside the built-in list. |
| `-pm`, `--promiscuous` | Accept unknown SOP classes. Useful for capturing private objects. |

**Where files go**

| Flag | Effect |
|------|--------|
| `-od`, `--output-directory D` | Write to `D` (default `.`). |
| `-ss`, `--sort-conc-studies P` | Group each study into `P_YYYYMMDD_HHMMSSPPP/`. |
| `-su`, `--sort-on-study-uid P` | Group each study into `P_<StudyInstanceUID>/`. |
| `-sp`, `--sort-on-patientname` | Group into `<PatientName>_<timestamp>/`. |
| `-uf`, `--default-filenames` | Filename from SOP Instance UID (default). |
| `+uf`, `--unique-filenames` | Always-unique filename, never overwrite. |
| `-tn`, `--timenames` | Filename from reception timestamp. |
| `-fe`, `--filename-extension EXT` | Append `EXT` (no leading dot added). |

**Receive-side behavior**

| Flag | Effect |
|------|--------|
| `+B`, `--bit-preserving` | Write bytes exactly as received — no transcoding, no group-length recalc. Essential when you must preserve the on-wire encoding. |
| `--ignore` | Accept and discard. Bandwidth/timing tests. |
| `+t=` / `+te` / `+ti` / `+td` | Recode incoming objects to a specific output TS (cannot combine with `+B`). |
| `+v`, `--verbose-pc` | With `-v`, also print the accepted presentation contexts. |

**Hooks**

| Flag | Effect |
|------|--------|
| `-xcr`, `--exec-on-reception CMD` | Run `CMD` after each C-STORE. Placeholders: `#p` (path), `#f` (filename), `#a` (calling AET), `#c` (called AET), `#r` (remote host/IP). |
| `-xcs`, `--exec-on-eostudy CMD` | Run `CMD` after a complete study has arrived (`#f` not available). |
| `-tos`, `--eostudy-timeout SEC` | How long to wait after the last object before declaring a study "done". |
| `-rns`, `--rename-on-eostudy` | At end-of-study, rename files to a clean numbered pattern. |
| `-xs`, `--exec-sync` | Run the hook synchronously in the foreground (default: async). |

### Examples
```bash
# 1) Plain receiver in current dir.
storescp -v -aet MY_AET PACS_PORT

# 2) Accept everything, sort each study into its own directory by Study UID,
#    name files with .dcm extension, write under /data/incoming.
storescp -v +xa -aet MY_AET \
         -od /data/incoming \
         -su study_ \
         -fe .dcm \
         PACS_PORT

# 3) Fork-per-association receiver with a post-study hook.
storescp -v --fork +xa -aet MY_AET \
         -od /data/incoming \
         -ss study_ \
         --exec-on-eostudy "/usr/local/bin/notify.sh #p #a" \
         -tos 30 \
         PACS_PORT
```

### Gotchas
- Built-in default proposal **only** accepts uncompressed TS. To accept JPEG,
  RLE, MPEG, etc., pass `+xa` (`--accept-all`) or write a config file. Many
  "PACS rejected my C-STORE" reports trace to a vanilla `storescp` without
  `+xa`.
- `--fork` is **incompatible** with `--exec-on-eostudy`, `--rename-on-eostudy`,
  and `--sort-conc-studies` because each child process loses the cross-
  association state needed to detect end-of-study.
- `--exec-on-reception` runs **asynchronously** by default. If your hook
  needs the file to still be there (e.g. moves it), pair with `--exec-sync`,
  or your hook can race with the next incoming object.
- `+B` (bit-preserving) bypasses VR/length normalization. Files are byte-
  identical to what came off the wire — including any peer quirks.
- Filenames generated from SOP Instance UID can collide if the same instance
  is sent twice. Default behavior: silently overwrite. Use `+uf` to keep both.

---

## dcmsend

> The "simpler storescu". Same job (C-STORE SCU) with fewer knobs, sensible
> defaults for bulk sends, and built-in handling of multi-association runs
> (auto-reassociate when you exceed 128 PCs). Prefer this for production
> batch transfers; use `storescu` when you need fine-grained TS proposal
> control or `asconfig`-driven profiles.

### Synopsis
```
dcmsend [options] peer port dcmfile-in...
```

### Essential flags
| Flag | Effect |
|------|--------|
| `+sd`, `--scan-directories` | Treat directory args as scan roots. |
| `+r`, `--recurse` | Recurse into subdirectories (with `+sd`). |
| `+sp`, `--scan-pattern P` | Wildcard filter for `+sd`. |
| `+rd`, `--read-from-dicomdir` | Read the file list from a DICOMDIR (no need to pre-enumerate). |
| `-nh`, `--no-halt` | Skip bad input files and continue past failed C-STOREs. |
| `+ma`, `--multi-associations` | When the run needs >128 PCs, open further associations in sequence (default). |
| `-ma`, `--single-association` | Force a single association even if too few PCs. |
| `+dls`, `--decompress-lossless` | Decompress lossless TS if the peer can't handle the original (default). |
| `+dly`, `--decompress-lossy` | Also decompress lossy TS for the peer. |
| `-dn`, `--decompress-never` | Never transcode. If peer doesn't accept the on-wire TS, that file fails. |
| `-nip`, `--no-illegal-proposal` | Strict DICOM: do not propose any PC missing the default TS. |
| `-nuc`, `--no-uid-checks` | Skip SOP-class-UID validation; allows private SOP classes through. |
| `+crf`, `--create-report-file F` | Write a transfer summary report to `F` at the end. |

For `-aet`/`-aec`, timeouts, `--max-pdu`/`--max-send-pdu`, and IP-version,
see [common-options.md](common-options.md). Note: `dcmsend` does **not**
have the storescu `-x*` propose family — its proposal logic is automatic.
Also note: `dcmsend` does **not** have TLS support in current builds.

### Examples
```bash
# 1) Send every .dcm in the current directory.
dcmsend -v -aet MY_AET -aec PACS_AET PACS_HOST PACS_PORT *.dcm

# 2) Recurse through a study tree, skip bad files, write a report.
dcmsend -v +sd +r -nh -aec PACS_AET \
        +crf /var/log/dcmsend-$(date +%F).txt \
        PACS_HOST PACS_PORT /data/studies

# 3) Send everything referenced from a DICOMDIR.
dcmsend -v +rd -aec PACS_AET PACS_HOST PACS_PORT /mnt/cd/DICOMDIR
```

### Gotchas
- `dcmsend` defaults to `--read-file-only` (the file must have a valid
  Part-10 meta header). `storescu` defaults to `--read-file` (auto-detect).
  If you have raw datasets, switch to `+f` (`--read-file`) or `-f`.
- No `-x*` flags. If you need to *force* a specific proposed TS — say, to
  test peer behavior — drop down to `storescu`.
- No `--config-file`. For `asconfig`-based negotiation profiles, use
  `storescu`.
- Default decompression policy is `+dls` (lossless only). If your peer
  refuses the on-wire lossy TS *and* you don't pass `+dly`, those files
  fail rather than getting transcoded.
- A "successful" `dcmsend` return doesn't mean every C-STORE response was
  status 0000 — the report file (or `-v`) is where you check per-instance
  status.

---

## dcmrecv

> The "simpler storescp". Modern C-STORE receiver with fewer flags and an
> opinionated directory layout. Less powerful than `storescp` (no `--fork`,
> no post-study hooks, fewer TS-preference knobs), but the right choice for
> straightforward "drop files in this folder" workloads. Requires an
> `asconfig` config file to accept anything beyond Verification.

### Synopsis
```
dcmrecv [options] port
```

### Essential flags
| Flag | Effect |
|------|--------|
| `-xf`, `--config-file F P` | **Almost always required** — without it, dcmrecv only accepts C-ECHO. Use the shipped `storescp.cfg` with profile `default` (or `Default`) as a starting point. |
| `-aet`, `--aetitle AET` | Listener AE title. With this set, incoming associations whose `-aec` doesn't match are rejected. |
| `-uca`, `--use-called-aetitle` | Default — respond as whatever called AET the SCU used (accept any). |
| `-od`, `--output-directory D` | Where files land. Default `.`. |
| `+ssd`, `--series-date-subdir` | Auto-tree as `<D>/data/YYYY/MM/DD/<file>` from Series Date (0008,0021). Falls back to today's date under `undef/`. |
| `-s`, `--no-subdir` | Flat layout in `-od` (default). |
| `+fd`, `--default-filenames` | Filename from SOP Instance UID (default). |
| `+fu`, `--unique-filenames` | Always-unique filename based on a new UID. |
| `+fsu`, `--short-unique-names` | Short pseudo-random 16-hex filename. |
| `+fst`, `--system-time-names` | Filename from current system time. |
| `-fe`, `--filename-extension EXT` | Append `EXT` to generated names. |
| `+B`, `--bit-preserving` | Write exactly as received (cannot combine with `+ssd`). |
| `--ignore` | Receive and discard. |
| `-dhl`, `--disable-host-lookup` | Skip reverse-DNS on incoming connections. Speeds up association setup on slow-DNS networks. |

For TLS and timeouts see [common-options.md](common-options.md).

### Examples
```bash
# 1) Minimal receiver — accepts only Verification without a profile.
#    Almost never what you want.
dcmrecv -v PACS_PORT

# 2) Real receiver: shipped storescp.cfg profile, files under .dcm.
dcmrecv -v -xf /path/to/storescp.cfg default \
        -od /data/incoming \
        -fe .dcm \
        PACS_PORT

# 3) Auto-tree by Series Date, short random filenames.
dcmrecv -v -xf storescp.cfg default \
        -od /data/incoming \
        +ssd +fsu -fe .dcm \
        PACS_PORT
```

### Gotchas
- **Without `-xf`, dcmrecv only supports Verification.** It will accept
  associations and respond to C-ECHO, then reject every C-STORE as
  "no presentation context". This is by design — but a frequent
  first-run surprise. The shipped `storescp.cfg` profile is the
  standard answer.
- No `--fork`. dcmrecv handles one association at a time. For high-
  throughput parallel receives, fall back to `storescp --fork`.
- No `--exec-on-reception` / `--exec-on-eostudy`. If you need post-receive
  hooks, use `storescp`.
- `+ssd` and `+B` are mutually exclusive — bit-preserving writes the file
  before the dataset is parsed, so Series Date isn't yet available.

---

## findscu

> C-FIND SCU for Patient-Root / Study-Root Query/Retrieve **and** Modality
> Worklist (MWL). Used to query a PACS or worklist server and either dump
> the matching identifiers to your log, or extract them as DICOM/XML files.

### Synopsis
```
findscu [options] peer port [dcmfile-in...]
```

A query file is a DICOM dataset (made with `dump2dcm` or `dcmodify
--create-file`) carrying the matching keys. Alternatively, build the whole
query from `-k` options on the command line.

### Essential flags

**Information model — pick exactly one**

| Flag | Effect |
|------|--------|
| `-P`, `--patient` | Patient Root Q/R (`1.2.840.10008.5.1.4.1.2.1.1`). Hierarchy: Patient → Study → Series → Instance. |
| `-S`, `--study` | Study Root Q/R (`...2.2.1`). Most PACS implement this; queries at Study level upward don't need PatientID. |
| `-O`, `--psonly` | Patient/Study-Only Q/R (`...2.3.1`). Rarely used. |
| `-W`, `--worklist` | **Default**. Modality Worklist Information Model (`1.2.840.10008.5.1.4.31`) — for talking to RIS/MWL servers, not PACS. |

**Building the query**

| Flag | Effect |
|------|--------|
| `-k`, `--key KEY` | Add/override one matching key. May be repeated. Forms: `-k "(0008,0052)=STUDY"` (with parens, recommended), `-k "0010,0020=PAT001"` (legacy syntax, still works), or `-k PatientName="HEWETT*"` (dictionary keyword). Sequence/item path: `-k "(0040,0100)[0].Modality=CT"`. A key with no `=value` ("return") is a *requested* attribute the SCP should return. |

**Output**

| Flag | Effect |
|------|--------|
| `+sr`, `--show-responses` | Always log response identifiers (default on without `-X*`). |
| `-sr`, `--hide-responses` | Don't print responses to the log. |
| `-X`, `--extract` | Write each response as `rsp0001.dcm`, `rsp0002.dcm`, ... |
| `-Xx`, `--extract-xml` | Same, but as `rsp0001.xml` (per the `dcm2xml.dtd`). |
| `-Xs`, `--extract-xml-single F` | Bundle all responses into one XML file `F`. UTF-8 by default. |
| `-Xlo`, `--limit-output N` | Cap extracted files at `N`. |
| `-od`, `--output-directory D` | Where to put `-X*` output. |
| `--cancel N` | Send a C-CANCEL after the first `N` responses (load-test the SCP's cancel handling). |

For `-aet`/`-aec`, `-x*` propose flags, timeouts, IP-version, and TLS, see
[common-options.md](common-options.md).

### How `-k` queries work

A C-FIND request is one DICOM dataset that mixes two kinds of attributes:

1. **Matching keys** — attributes *with* values. The SCP returns only
   instances that match. Wildcards (`*`, `?`), range matching (`20240101-`),
   list matching (`CT\MR`), etc. are defined per VR by PS3.4 C.2.2.2.
2. **Return keys** — attributes *without* values (empty). The SCP must
   include these in every matching response.

Both go through `-k`. The required attribute on every query is
`(0008,0052) QueryRetrieveLevel`, set to `PATIENT`, `STUDY`, `SERIES`, or
`IMAGE`.

```
# A canonical Study-level query:
-k "(0008,0052)=STUDY"        # the query level (required)
-k "(0010,0020)=PAT001"       # match key: PatientID
-k "(0008,0020)"              # return key: StudyDate (empty value)
-k "(0020,000D)"              # return key: StudyInstanceUID
```

If no query file is given on the command line, the entire request is
assembled from `-k` flags alone.

### Examples
```bash
# 1) MWL query — what's scheduled today on CT modality? (default -W)
findscu -v -aec MWL_AET \
        -k "(0040,0100)[0].Modality=CT" \
        -k "(0040,0100)[0].ScheduledProcedureStepStartDate=$(date +%Y%m%d)" \
        PACS_HOST PACS_PORT

# 2) Study-root: find all studies for PatientID=PAT001, return StudyInstanceUID
#    plus a few descriptive attrs.
findscu -v -S -aec PACS_AET \
        -k "(0008,0052)=STUDY" \
        -k "(0010,0020)=PAT001" \
        -k "(0020,000D)" \
        -k "(0008,0020)" \
        -k "(0008,1030)" \
        PACS_HOST PACS_PORT

# 3) Series-level query, extract each response as XML for downstream parsing.
findscu -v -S -aec PACS_AET \
        -k "(0008,0052)=SERIES" \
        -k "(0020,000D)=1.2.840.113619.2.55.3.1234567" \
        -k "(0020,000E)" \
        -k "(0008,103E)" \
        -Xx -od ./responses \
        PACS_HOST PACS_PORT
```

### Gotchas
- **Default model is Worklist (`-W`)**, not Study Root. Forgetting `-S` /
  `-P` and pointing at a PACS gives "abstract syntax not supported" because
  most PACS don't expose MWL.
- `QueryRetrieveLevel` must match the kind of attributes you're matching/
  returning. STUDY-level can return Study* attributes; mixing in
  SeriesInstanceUID on a STUDY query is conformant only if you also raise
  the level.
- Wildcards (`*`, `?`) only work on VRs that support them (mostly PN, LO,
  SH, CS, UI). Numeric VRs use range matching with `-`.
- The DICOM standard requires the SCP to support `*` in `PatientName` —
  many real PACS only do prefix matching (`HEWETT*` works, `*ETT` doesn't).
- `-Xs` (single XML) requires character set conversion compiled in,
  otherwise non-ASCII characters in responses can produce invalid XML.

---

## movescu

> C-MOVE SCU. Tells the PACS "send this study to AE title X". The PACS
> opens a *new* association back to X and pushes the images via C-STORE.
> "Move" is a misnomer — nothing is deleted from the PACS.

### Synopsis
```
movescu [options] peer port [dcmfile-in...]
```

### The destination-AE handshake (read this before using movescu)

C-MOVE has a three-party setup:

```
   1. movescu  ──C-MOVE-RQ───►  PACS (Q/R SCP)
                                  │
                                  │ 2. PACS looks up "destination AET"
                                  │    in its own configured AE table
                                  │
                                  ▼
                       (looks up AET → host:port)
                                  │
   3. PACS ──C-STORE-RQ (new association)──►  destination SCP
```

The destination AE title is set with `-aem` (`--move`). It defaults to
`MOVESCU`. Critically:

- The PACS must **already know** the AET → host:port mapping for whatever
  you pass to `-aem`. movescu can't tell it. You configure this on the
  PACS, usually under "DICOM modalities" / "AE table" / "remote AEs".
- The destination is typically **a separate process**: a `storescp` or
  `dcmrecv` you started somewhere reachable by the PACS.
- *Optionally*, movescu itself can play the role of destination: pass
  `+P PORT` (`--port`) and it'll open a Storage SCP on that port on the
  same machine, ready to receive what the PACS sends. In that mode the
  PACS still needs to be configured to send to movescu's host:port — but
  you don't need a separate storescp running.

### Essential flags
| Flag | Effect |
|------|--------|
| `-aem`, `--move AET` | **The destination AE title.** The PACS will C-STORE to whatever it has registered under this AET. Default `MOVESCU`. |
| `+P`, `--port N` | Start an internal Storage SCP on port `N` to receive the images movescu just asked for. |
| `--no-port` | Don't open an internal SCP (default — assumes a separate storescp/dcmrecv handles the storage side). |
| `-P`, `--patient` | Patient Root Q/R (default). |
| `-S`, `--study` | Study Root Q/R. |
| `-O`, `--psonly` | Patient/Study Only Q/R. |
| `-k`, `--key KEY` | Same syntax as findscu. C-MOVE queries should only contain QueryRetrieveLevel + one or more *unique* keys (PatientID / StudyInstanceUID / SeriesInstanceUID / SOPInstanceUID). |
| `-od`, `--output-directory D` | When using `+P`, where received files go. |
| `+B`, `--bit-preserving` | Internal SCP writes received objects exactly as received. |
| `-pi`, `--pending-ignore` | Default — assume no dataset in pending C-MOVE responses. |
| `-pr`, `--pending-read` | Read and discard any dataset present in pending responses (for non-conformant SCPs that ship one). |
| `+x*` | Preferred TS for the *incoming* storage association (when `+P` is used). |
| `-x*` | Proposed TS for the *outgoing* Q/R association. |
| `--cancel N` | Send C-CANCEL after `N` responses. |

For other shared flags see [common-options.md](common-options.md).

### Examples
```bash
# 1) Classic: a separate storescp is already listening on MY_HOST:MY_PORT,
#    pre-registered on the PACS under AE title MY_AET. movescu just sends
#    the C-MOVE-RQ and exits — the PACS pushes images directly to your
#    storescp.
movescu -v -S \
        -aet MOVE_CLIENT -aec PACS_AET -aem MY_AET \
        -k "(0008,0052)=STUDY" \
        -k "(0020,000D)=1.2.840.113619.2.55.3.1234567" \
        PACS_HOST PACS_PORT

# 2) movescu acts as its own subordinate storage SCP on port 11112.
#    The PACS must still be configured to send to <this-host>:11112
#    under AE title MY_AET.
movescu -v -S \
        -aet MOVE_CLIENT -aec PACS_AET -aem MY_AET \
        +P 11112 -od ./retrieved \
        -k "(0008,0052)=STUDY" \
        -k "(0020,000D)=1.2.840.113619.2.55.3.1234567" \
        PACS_HOST PACS_PORT

# 3) Series-level retrieve.
movescu -v -S -aem MY_AET +P 11112 -od ./series \
        -k "(0008,0052)=SERIES" \
        -k "(0020,000D)=1.2.840.113619.2.55.3.1234567" \
        -k "(0020,000E)=1.2.840.113619.2.55.3.1234567.1" \
        PACS_HOST PACS_PORT
```

### Gotchas
- **"Move destination unknown"** (DIMSE status `A801`) — the PACS doesn't
  know your `-aem` AE title. Fix on the PACS side, not on movescu.
- **C-MOVE-RQ succeeds but no images arrive** — the PACS *has* the AET
  registered but the host:port it's configured to is unreachable, wrong, or
  blocked by a firewall. Check the PACS's connection log. The destination
  port must be reachable *from the PACS*, not from your laptop.
- C-MOVE queries should carry **only** the QueryRetrieveLevel and unique
  keys (StudyInstanceUID, SeriesInstanceUID, ...). Adding match keys like
  `PatientName=*` is technically conformant but most PACS reject or ignore.
  Use `findscu` to discover UIDs, then C-MOVE on the UID.
- With `+P`, if the SCU peer hangs on the storage association,
  `movescu` waits forever. Pair with `-td` (DIMSE timeout).
- The default `-aet` (calling AET on the Q/R association) is `MOVESCU`. The
  default `-aem` (destination AET) is **also** `MOVESCU`. They're independent
  — set both.

---

## getscu

> C-GET SCU. Like C-MOVE, but the storage sub-operations happen *on the same
> association* the SCU opened. No third-party AE table, no firewall ordeals
> — but C-GET is far less widely supported than C-MOVE.

### Synopsis
```
getscu [options] peer port [dcmfile-in...]
```

### Essential flags
| Flag | Effect |
|------|--------|
| `-P`, `--patient` | Patient Root Q/R (default). |
| `-S`, `--study` | Study Root Q/R. |
| `-O`, `--psonly` | Patient/Study Only Q/R. |
| `-k`, `--key KEY` | Same query-building syntax as findscu/movescu. |
| `-od`, `--output-directory D` | Where received instances are stored. |
| `+B`, `--bit-preserving` | Write each instance directly to disk as received. |
| `--ignore` | Receive but discard. |
| `+x*` | Preferred TS for incoming storage sub-ops. |
| `-x*` | Proposed TS for the outgoing Q/R association. |

For other shared flags see [common-options.md](common-options.md).

### Examples
```bash
# 1) Retrieve a study by UID, store into ./retrieved.
getscu -v -S -aet MY_AET -aec PACS_AET \
       -od ./retrieved \
       -k "(0008,0052)=STUDY" \
       -k "(0020,000D)=1.2.840.113619.2.55.3.1234567" \
       PACS_HOST PACS_PORT

# 2) Retrieve a single SOP instance.
getscu -v -S -aec PACS_AET -od ./instance \
       -k "(0008,0052)=IMAGE" \
       -k "(0020,000D)=<study uid>" \
       -k "(0020,000E)=<series uid>" \
       -k "(0008,0018)=<sop instance uid>" \
       PACS_HOST PACS_PORT

# 3) Prefer to receive in original lossless JPEG (no decompression by the SCP).
getscu -v -S -aec PACS_AET +xs -od ./out \
       -k "(0008,0052)=STUDY" \
       -k "(0020,000D)=<study uid>" \
       PACS_HOST PACS_PORT
```

### Gotchas
- **Many PACS don't support C-GET.** Commercial Q/R SCPs overwhelmingly
  implement C-MOVE only — Orthanc, dcm4che, conquest do support C-GET, but
  most vendor PACS will reject the abstract syntax. Try `echoscu -pts 53`
  or `findscu` first to confirm.
- The SCP must accept the storage SOP classes for whatever it's about to
  send — and the negotiation happens *up front* in the same association
  as the C-GET request. If the SCP refuses, e.g., RT Plan Storage, no
  C-STORE for it can occur.
- No `-aem` — there's no third-party destination concept in C-GET.
- The "pending" / "completed" / "failed" / "warning" sub-counters in the
  final response are critical: a C-GET can complete with status 0000 yet
  have a "Failed Sub-operations" count > 0.

---

## termscu

> Tells a DCMTK-built SCP to shut itself down by negotiating a private
> Shutdown SOP class. The SCP refuses the association and terminates.
> Diagnostic / shutdown helper for test harnesses — does nothing useful
> against non-DCMTK SCPs.

### Synopsis
```
termscu [options] peer port
```

### Essential flags
| Flag | Effect |
|------|--------|
| `-aet`, `--aetitle AET` | Calling AE title. Default `ECHOSCU` (yes, really — the source uses the echoscu default). |
| `-aec`, `--call AET` | Called AE title. Default `ANY-SCP`. |
| `-pdu`, `--max-pdu N` | Max receive PDU. |

(termscu has no timeout, TLS, or IP-version flags in the current build —
it's a deliberately minimal tool.)

### Examples
```bash
# 1) Stop a test storescp listening on PACS_PORT.
termscu -aec MY_AET PACS_HOST PACS_PORT

# 2) Verbose, to see exactly what handshake happens.
termscu -v -aec MY_AET PACS_HOST PACS_PORT
```

### Gotchas
- Only DCMTK servers that explicitly enable the private Shutdown SOP class
  in their build / config will obey this. A vendor PACS will just reject
  the association and keep running.
- Anyone with network access can shut down your test SCP by running
  `termscu` at it. Never expose a Shutdown-aware SCP outside trusted
  networks.
- The Shutdown SOP class UID is `1.2.276.0.7230010.3.4.1915765545.18030.917282194.0`
  — note that it's a DCMTK-private UID under OFFIS's root, not a DICOM
  standard one.

---

## Cross-tool patterns

**Pick by use case.**

| You want to... | Use |
|----------------|------|
| Smoke-test "is the PACS up?" | `echoscu` |
| Send a few files with fine TS control / test PACS negotiation | `storescu` |
| Bulk-send a directory tree in production | `dcmsend` |
| Run a long-lived receiver with hooks per study | `storescp` |
| Run a simple receiver into a sorted directory | `dcmrecv` |
| Discover what's on the PACS (UIDs, MWL entries) | `findscu` |
| Pull a study by UID with PACS-side AE config | `movescu` (peer pushes) |
| Pull a study by UID, no AE config on PACS | `getscu` (if SCP supports it) |
| Stop a DCMTK test SCP cleanly | `termscu` |

**Typical Q/R workflow.**

```
1. echoscu  PACS_HOST PACS_PORT -aec PACS_AET
   └─► confirm connectivity

2. findscu -S PACS_HOST PACS_PORT \
     -k "(0008,0052)=STUDY" -k "(0010,0020)=PAT001" -k "(0020,000D)"
   └─► get StudyInstanceUIDs

3. movescu -S PACS_HOST PACS_PORT -aem MY_AET +P 11112 \
     -k "(0008,0052)=STUDY" -k "(0020,000D)=<uid from step 2>"
   └─► pull images
```

**Debugging association failures.** Every dcmnet tool accepts `-d`. The
trace shows the A-ASSOCIATE-RQ (your proposed PCs), A-ASSOCIATE-AC/RJ
(what the peer accepted/rejected), and per-DIMSE message headers. 90% of
DICOM network problems show up here without needing Wireshark:

```bash
storescu -d -aet MY_AET -aec PACS_AET PACS_HOST PACS_PORT file.dcm 2>&1 \
  | grep -E "ASSOC|abstract|transfer|status"
```

**Common error mappings.**

| Error message | Likely cause |
|---------------|--------------|
| `Association Rejected: Called AE Title Not Recognized` | `-aec` doesn't match what the PACS expects. |
| `Association Rejected: Calling AE Title Not Recognized` | The PACS doesn't have your `-aet` in its allowed-AETs list. |
| `No presentation context for ...` | The peer accepted the association but not the SOP class / TS pair you needed. Adjust `-x*` flags or accept-side preference. |
| `Maximum PDU Length` abort | Drop `--max-pdu` (and add `--max-send-pdu` if needed). |
| `Move Destination Unknown` (C-MOVE A801) | PACS has no AE-table entry for `-aem`. |
| `Refused: Out of Resources` | PACS-side disk/queue limit. Not your bug. |
| `Cannot connect to host` | TCP-level — wrong host, wrong port, firewall. Try `nc -zv PACS_HOST PACS_PORT` to confirm before blaming DICOM. |
