# PHI leak paths — where the DICOM and inference stack writes identifiers

Rule PHI-06 puts third-party logging in scope. This file lists the leaks found, the exact
setting that stops each one, and a scan to catch the rest.

Verified 2026-11-15 with synthetic data on loopback. Grades: **R** = reproduced in a run;
**D** = read in the source code or official documentation; **U** = not verified.

Versions tested: pynetdicom 3.0.4, pydicom 3.0.2, DCMTK 3.7.0, Orthanc 1.13.0,
PostgreSQL 17, loguru 0.8.0, structlog 26.1.0, sentry-sdk 2.75.0, uvicorn 0.54.0,
FastAPI 0.163.1, httpx 0.28.1, urllib3 2.8.0, dicomweb-client 0.61.2. Defaults move
between versions: re-run the scan after every dependency upgrade.

## The five that leak with default settings

1. **pynetdicom** logs the full C-FIND, C-GET, and C-MOVE identifiers — requests and
   responses — at **INFO**. Any application that sets the root logger to INFO leaks
   name, patient ID, birth date, accession number, and UIDs. (R)
2. **DCMTK `findscu`** prints every C-FIND response data set with no flag at all. (R)
3. **Web access logs** (uvicorn, nginx) write the request line: QIDO query strings
   carry patient ID and name; WADO paths carry all three UIDs. (R / D)
4. **Error reporters and tracing** send data off the host: Sentry sends local variables,
   the query string, and the request body by default; tracing spans carry the full URL. (R)
5. **PostgreSQL** logs the conflicting key value on a unique violation, and the failing
   statement text. (R)

## Python DICOM libraries

| Leak | Written | Level | Default? | Fix | Grade |
|---|---|---|---|---|---|
| pynetdicom query identifiers | Full request and every pending response identifier | INFO | **Yes** | `from pynetdicom import _config`; set `_config.LOG_REQUEST_IDENTIFIERS = False` and `_config.LOG_RESPONSE_IDENTIFIERS = False` | R |
| pynetdicom DIMSE summaries | Affected SOP Instance UID, move destination | DEBUG | No | `_config.LOG_HANDLER_LEVEL = "none"`, or the `pynetdicom` logger at WARNING | R |
| `pynetdicom.debug_logger()` | All of the above plus association dumps | DEBUG | No | Never ship it | R |
| pynetdicom C-STORE at INFO | "Received Store Request", status | INFO | Yes | Safe as it is | R |
| `pydicom.config.debug(True)` | Every element value in hex and ASCII, and the file path | DEBUG | No | Never on real data | R |
| pydicom validation warnings | The **raw invalid value** in the message, through both `logging` and `warnings` | WARNING | **Yes** | A `logging.Filter` on the `pydicom` logger, and `warnings.filterwarnings("ignore", module="pydicom")`. Log the tag keyword and VR yourself | R |
| `str(ds)`, `repr(ds)`, `str(elem)` | The whole data set, or one element with its value | Wherever it is formatted | Code | A lint rule that bans `Dataset` and `DataElement` in log calls | R |
| Exceptions | `FileNotFoundError` carries the full path | Any | Yes | Log `type(e).__name__` and the event UUID, not `str(e)` | R |

## DCMTK command-line tools

| Tool and flag | Written | Default? | Fix | Grade |
|---|---|---|---|---|
| `findscu` | Every response data set | **Yes** | `-sr` (hide responses), or `-X` (responses to files) | R |
| `findscu -v`, `movescu -v` | The request identifiers; still printed with `-sr` | No | No `-v` in production; a log configuration at WARN | R |
| `storescp -v` | `storing DICOM file: <dir>/<modality>.<SOPInstanceUID>` | No | `+uf` or `-tn` for file names without UIDs | R |
| `storescp -sp` / `-su` | Creates a directory named from the **patient name** / the Study UID | No | Do not use them; `-ss <prefix>` | R |
| `storescp -xcr "cmd #p #f"` | Path with patient name and UID on the child's command line | No | Pass an opaque spool path | R |
| `-d` | AE titles, peer host name, SOP Instance UID. No data-set dump | No | `-ll warn` | R |
| `--log-config` at WARN | Nothing from a successful run | — | Ship this configuration | R |

## Orthanc

| Leak | Written | Level | Fix | Grade |
|---|---|---|---|---|
| Default level | Start-up lines only | WARNING | — | R |
| `--verbose`, DICOM | Peer AE title and IP; C-FIND tags **masked** (`*** POTENTIAL PHI ***`) | INFO | Keep `DeidentifyLogs: true` (the default) | R |
| `--verbose`, DICOMweb plugin | QIDO arguments and the internal find body **in clear text** | INFO | Keep the plugins log category at WARNING | R |
| `--verbose`, HTTP | Request paths with UIDs | INFO | Keep the HTTP category at WARNING | R |
| `--trace`, `--trace-dicom` | Raw C-FIND data sets. "DICOM logs at TRACE level are not deidentified" | TRACE | Never in production. The REST API can switch the level at run time: restrict it | R / D |
| **Resource IDs** | An **unkeyed SHA-1** of patient ID and UIDs. Reversible with a dictionary of patient IDs | Always | Treat as PHI. Never use as a log correlation token | R |

## Other DICOM stacks

| Stack | Leak | Fix | Grade |
|---|---|---|---|
| dcm4che | Category `org.dcm4che3.net.Dimse`: INFO gives AE pair and SOP Instance UID; DEBUG gives the response data set | Set that category to WARN | D |
| fo-dicom (.NET) | `LogDimseDatasets` and `LogDataPDUs` write data sets and PDUs. Both default `false` | Keep them false; filter the category to Warning | D |
| dcm4chee-arc defaults | Not checked | — | U |

## DICOMweb and HTTP

UIDs sit in URL paths. QIDO parameters (`PatientID`, `PatientName`, `AccessionNumber`) sit
in query strings. Anything that logs a URL logs PHI.

| Component | Written | Default? | Fix | Grade |
|---|---|---|---|---|
| uvicorn access log | Request line with path and query | **Yes** | `--no-access-log`; log the **route template** (`/studies/{study}/series`) from your own middleware | R |
| gunicorn access log | Request line when enabled | No | Avoid `%(r)s` and `%(q)s` | R |
| nginx | `combined` format uses `$request` | **Yes** | A custom `log_format` without `$request`, `$request_uri`, `$args`; a `map` that collapses UIDs in `$uri` | D (the map was not run) |
| Envoy | Default format includes the path with its query | Yes | `%PATH(NQ)%` drops the query; path UIDs remain, so log the route name | D |
| httpx | `HTTP Request: GET <full URL>` | **INFO** | `httpx` and `httpcore` loggers at WARNING | R |
| requests / urllib3 | Request line with query | DEBUG | `urllib3` logger at WARNING or above | R |
| dicomweb-client | Full URL and the request headers | DEBUG | Keep at INFO or above | R |

Where the server allows it, send query keys in a POST body, not in the query string.

## Tracebacks and local variables

| Mechanism | Leak | Default? | Fix | Grade |
|---|---|---|---|---|
| Standard `logging.exception` | Message and source lines; no locals | — | Safe unless the message embeds values | R |
| loguru | `diagnose=True` prints every variable value in each frame | **Yes** | `logger.add(sink, diagnose=False, backtrace=False)`, or `LOGURU_DIAGNOSE=NO` | R |
| structlog `ConsoleRenderer` | Traceback with locals | **Yes** | JSON renderer in production | R |
| structlog `dict_tracebacks` | `"locals"` per frame | **Yes** | `ExceptionRenderer(ExceptionDictTransformer(show_locals=False))` | R |
| rich traceback | Locals table | No | Do not enable `show_locals` | R |

## Error reporting and tracing — data leaves the host

| Agent | Sent | Default? | Fix | Grade |
|---|---|---|---|---|
| Sentry, frames | Local variables | **Yes** | `include_local_variables=False`, `include_source_context=False`, and a `before_send` scrubber | R |
| Sentry, requests | Query string and the JSON request body, even with `send_default_pii` unset | **Yes** | `max_request_body_size="never"`; strip URL and query in `before_send` | R |
| Sentry, logging | Records ≥ INFO become breadcrumbs; ≥ ERROR become events | **Yes** | `LoggingIntegration(level=None, event_level=None)` | R |
| OpenTelemetry HTTP client spans | `http.url` / `url.full` with the query | When instrumented | A `request_hook` that overwrites the attribute | R |
| FastAPI server spans | `url.query`; built-in redaction covers cloud-signature parameters only | When a tracer provider exists | Scrub at the collector | R (collector processors: U) |

An error reporter or tracing backend outside the hospital is a cross-border data
transfer when it carries PHI. Decide it with the data-protection owner (PHI-08).

## Inference servers

| Server | Default | Risk | Grade |
|---|---|---|---|
| Triton | Tracing off | `--trace-config level=TENSORS` writes input and output **tensor data** to the trace file | D |
| TorchServe | Access log holds method, path, status, size | A custom handler that logs its input | D |
| BentoML | Access log holds metadata | Body capture not documented | D / U |

## Linux platform

| Leak | Detail | Fix | Grade |
|---|---|---|---|
| Core dumps | `systemd-coredump` stores full process memory — pixel data, data sets — and journals the command line, environment, and open file paths | `Storage=none` and `ProcessSizeMax=0` in `coredump.conf.d`; `LimitCORE=0` in the unit | D |
| Command lines | Arguments are world-readable in `/proc` and appear in audit `proctitle` records | Never pass identifiers as arguments; use a file or stdin | R / D |
| Storage paths | A layout such as `/data/<PatientID>/<StudyUID>/` reappears in exception text, tracebacks, and audit `PATH` records | Random or content-addressed spool names; keep the map in the database | R |
| Shell history | An interactive `findscu -k PatientID=…` is saved | Runbooks read keys from a file | U |
| Docker `json-file` driver | Captures all stdout; no rotation by default | Size limits or the `journald` driver. Does not remove PHI | D |
| journald rate limit | A dump burst can push audit-relevant lines out | Stop the dump at the source | D |
| PostgreSQL, default | `DETAIL: Key (…)=(value) already exists.` and the failing statement | `log_error_verbosity = terse`; bind parameters | R |
| PostgreSQL, statement logging | `DETAIL: Parameters: $1 = '…'` | `log_parameter_max_length = 0` | R |
| pgAudit | Statement text by default; parameter values when `pgaudit.log_parameter` is on | Keep it off | D |

## Safe pattern for a DICOM service

Log: event UUID · DIMSE operation and status code · SOP Class UID and Transfer Syntax
UID · counts (instances, bytes, sub-operations) · durations · model name and version ·
route template · a keyed-hash token `HMAC-SHA256(key, StudyInstanceUID)[:16]` when a
study link is needed (PHI-03).

Never log: data sets, identifiers, raw paths, URLs with paths or queries, local
variables, unkeyed hashes.

AE titles and peer addresses are not PHI but are site network facts: acceptable in
on-site logs, removed from any excerpt that leaves the site.

Enforce at three points:

1. One logging function with an allow-listed field schema.
2. Library loggers at WARNING: `pynetdicom`, `pydicom`, `httpx`, `httpcore`, `urllib3`,
   `dicomweb_client`, `uvicorn.access`.
3. The scan below, in the automated tests.

## Leak scan (PHI-04)

**Canaries first.** Seed the test fixtures with unique synthetic values and fail on any
exact match in the captured output. This is the strongest gate:

```bash
rg --fixed-strings --file canaries.txt test-run.log && exit 1
```

Scan stdout, the journal, and the tracing exporter's output — not only the application log.

Then patterns, for leaks the canaries do not cover:

```
UID          (?<![\d.])[0-2](?:\.(?:0|[1-9]\d*)){2,}(?![\d.])      keep only matches of 16–64 characters
UID allow    ^1\.2\.840\.10008\.                                   SOP classes, transfer syntaxes
tag keyword  \b(PatientName|PatientID|PatientBirthDate|PatientAddress|AccessionNumber|ReferringPhysicianName|
             StudyInstanceUID|SeriesInstanceUID|SOPInstanceUID|AffectedSOPInstanceUID)\b|Patient's (Name|Birth Date)
tag number   \(?\b0010,?[0-9A-Fa-f]{4}\)?|\(0008,00(18|50|90)\)|\(0020,000[DdEe]\)
person name  (?<![\w^])[A-Za-z][A-Za-z' -]{0,63}\^[A-Za-z][A-Za-z' -]{0,63}
birth date   (?i)birth\W{0,40}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])
QIDO param   [?&](PatientID|PatientName|PatientBirthDate|AccessionNumber|00100020|00100010|00100030|00080050)=
```

In the verification run these matched every seeded leak, and gave zero hits on the logs
produced with the fixes applied.

Known false positives:

- IPv4 addresses and version strings match a naive UID pattern; the 16-character
  minimum removes them. A rule that demands four or more components **misses** `2.25.<n>` UIDs.
- Implementation Class UIDs are not under the DICOM root (DCMTK `1.2.276.0.7230010.3.`,
  pydicom `1.2.826.0.1.3680043.8.498.`, pynetdicom `1.2.826.0.1.3680043.9.3811.`).
  Allow-list them by root.
- Vendor-private SOP Class UIDs, and coding-scheme UIDs in structured reports.
- Traceback `^^^^` markers; the person-name pattern needs letters on both sides.

For free text, such as a support excerpt, use the `deidentify` skill; these patterns
cover DICOM-shaped data only.

## Not verified

- Every Linux platform row marked D: nothing was run on a Linux host.
- The pydicom validation-warning leak on the *read* path (only assignment was run).
- fo-dicom: whether DIMSE summaries print the SOP Instance UID.
- Triton `--log-verbose` content; TorchServe and BentoML body logging.
- The nginx `map` redaction and OpenTelemetry collector redaction processors.
- Whether the dicomweb-client debug output includes an `Authorization` header.
