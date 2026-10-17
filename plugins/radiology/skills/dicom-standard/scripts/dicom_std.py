#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12", "lxml>=5"]
# ///
"""Offline, citable DICOM standard (PS3.1–PS3.22) for agents — the deterministic shell.

Mirrors the per-part DocBook XML that NEMA publishes, indexes it into SQLite (structure +
FTS5 keyword search), and answers from the cache with an edition + canonical URL on every
output. Facts live in the cache, never in the skill text.

    status    cached parts, edition, age; exit 1 when stale or editions are mixed
    pull      fetch/refresh parts (conditional GET, resumable); --check = HEAD only
    toc       outline of a part (or of one node)
    show      a section rendered to Markdown, with a `source:` line
    table     rows of a table, filterable by column (--where "tag=(0010,0010)")
    search    FTS5 keyword search across cached parts
    tag       PS3.6 data-dictionary row (+ its PS3.15 E.1-1 de-identification actions)

Cache: $DICOM_STD_HOME or ~/.lightbridge/data/dicom-standard/ — manifest.json, editions/<ed>/
partNN.xml (raw, kept per edition), index.sqlite (derived; rebuilt without network when the
schema changes). Read verbs never touch the network: a missing part exits 1 naming the
`pull` to run (`--pull` opts in to fetching first).

Exit codes: 0 ok · 1 stale / not cached / not found (well-formed request) · 2 fix the
request (ref syntax, unknown column, bad regex) · 3 network or environment (FTS5 missing,
unwritable cache, download failed).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Iterator, NoReturn

import typer
from lxml import etree

__version__ = "0.1.0"

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help=__doc__,
)

EXIT_STALE = 1  # stale cache, part not cached, node not found
EXIT_PARAMS = 2  # request malformed — fix and rerun
EXIT_ENV = 3  # network, FTS5, unwritable cache

HOME_ENV = "DICOM_STD_HOME"  # override; exists so the tool is testable in isolation
DEFAULT_HOME = "~/.lightbridge/data/dicom-standard"
BASE_URL = "https://dicom.nema.org/medical/dicom"
USER_AGENT = f"dicom-std/{__version__} (+https://github.com/Lightbridge-KS/agent-stuff)"

SCHEMA_VERSION = 1
MANIFEST_VERSION = 1

PARTS: dict[int, str] = {
    1: "Introduction and Overview",
    2: "Conformance",
    3: "Information Object Definitions",
    4: "Service Class Specifications",
    5: "Data Structures and Encoding",
    6: "Data Dictionary",
    7: "Message Exchange",
    8: "Network Communication Support for Message Exchange",
    10: "Media Storage and File Format for Media Interchange",
    11: "Media Storage Application Profiles",
    12: "Media Formats and Physical Media for Media Interchange",
    14: "Grayscale Standard Display Function",
    15: "Security and System Management Profiles",
    16: "Content Mapping Resource",
    17: "Explanatory Information",
    18: "Web Services",
    19: "Application Hosting",
    20: "Imaging Reports using HL7 Clinical Document Architecture",
    21: "Transformations between DICOM and other Representations",
    22: "Real-Time Communication",
}

NS = "{http://docbook.org/ns/docbook}"
XL_HREF = "{http://www.w3.org/1999/xlink}href"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"

EDITION_RE = re.compile(r"DICOM PS3\.\d+ (\d{4}[a-e])")
TAG_RE = re.compile(r"\(\s*([0-9A-Fa-fxX]{4})\s*,\s*([0-9A-Fa-fxX]{4})\s*\)")
REF_PLACEHOLDER = re.compile(r"\[\[ref:(\d+):([^\]]+)\]\]")
NODE_PREFIXES = ("sect_", "table_", "figure_", "chapter_", "para_", "biblio_", "glossary", "bibliography")

INLINE_TABLE_MAX = (8, 4)  # (rows, cols) a table may have to be inlined by `show`
CHUNK = 64 * 1024
TIMEOUT = 60


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def fail(code: int, message: str) -> NoReturn:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code)


def note(message: str) -> None:
    typer.echo(message, err=True)


def emit(obj: Any) -> None:
    typer.echo(json.dumps(obj, ensure_ascii=False, indent=2))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def script_name() -> str:
    return "dicom_std.py"


# ---------------------------------------------------------------------------
# Paths and manifest
# ---------------------------------------------------------------------------


def home() -> Path:
    return Path(os.environ.get(HOME_ENV) or DEFAULT_HOME).expanduser()


def manifest_path() -> Path:
    return home() / "manifest.json"


def db_path() -> Path:
    return home() / "index.sqlite"


def editions_dir() -> Path:
    return home() / "editions"


def incoming_dir() -> Path:
    return home() / "incoming"


def ensure_home() -> Path:
    h = home()
    try:
        h.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        fail(EXIT_ENV, f"cannot create cache dir {h}: {exc} (set {HOME_ENV} to a writable path)")
    return h


def load_manifest() -> dict[str, Any]:
    p = manifest_path()
    if not p.is_file():
        return {"schema_version": SCHEMA_VERSION, "manifest_version": MANIFEST_VERSION, "updated_at": None, "parts": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(EXIT_ENV, f"manifest unreadable at {p}: {exc} — delete it and pull again")
    data.setdefault("parts", {})
    return data


def save_manifest(data: dict[str, Any]) -> None:
    ensure_home()
    data["schema_version"] = SCHEMA_VERSION
    data["manifest_version"] = MANIFEST_VERSION
    data["updated_at"] = now_iso()
    tmp = manifest_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, manifest_path())


def part_entry(manifest: dict[str, Any], part: int) -> dict[str, Any] | None:
    return manifest["parts"].get(str(part))


def part_xml_path(entry: dict[str, Any]) -> Path:
    return home() / entry["path"]


def part_url(part: int, edition: str | None) -> str:
    return f"{BASE_URL}/{edition or 'current'}/source/docbook/part{part:02d}/part{part:02d}.xml"


def chtml_url(entry: dict[str, Any], part: int, chapter_id: str, node_id: str | None) -> str:
    """Canonical web anchor for a node: the chapter page plus an id fragment."""
    url: str = entry.get("url") or part_url(part, None)
    base = url.split("/source/docbook/")[0]
    page = f"{base}/output/chtml/part{part:02d}/{chapter_id}.html"
    if node_id and node_id != chapter_id:
        page += f"#{node_id}"
    return page


def parse_part(value: str) -> int:
    m = re.fullmatch(r"(?:PS3\.)?(\d{1,2})", value.strip(), re.IGNORECASE)
    if not m or int(m.group(1)) not in PARTS:
        fail(EXIT_PARAMS, f"unknown part '{value}' — use one of: {', '.join(str(p) for p in PARTS)}")
    return int(m.group(1))


# ---------------------------------------------------------------------------
# Fetcher — the one seam to the network (tests replace FETCHER)
# ---------------------------------------------------------------------------


class FetchError(Exception):
    def __init__(self, status: int | None, message: str):
        super().__init__(message)
        self.status = status


class Fetcher:
    """HEAD / GET with Range over urllib. Headers come back lower-cased."""

    def head(self, url: str) -> dict[str, str]:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return {k.lower(): v for k, v in resp.headers.items()}
        except urllib.error.HTTPError as exc:
            raise FetchError(exc.code, f"HTTP {exc.code} for {url}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FetchError(None, f"network error for {url}: {exc}") from exc

    def get(self, url: str, start: int | None = None) -> tuple[int, dict[str, str], Iterator[bytes]]:
        headers = {"User-Agent": USER_AGENT}
        if start:
            headers["Range"] = f"bytes={start}-"
        req = urllib.request.Request(url, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        except urllib.error.HTTPError as exc:
            if exc.code == 416:
                return 416, {k.lower(): v for k, v in exc.headers.items()}, iter(())
            raise FetchError(exc.code, f"HTTP {exc.code} for {url}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise FetchError(None, f"network error for {url}: {exc}") from exc

        def body() -> Iterator[bytes]:
            try:
                while True:
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    yield chunk
            except (TimeoutError, OSError) as exc:
                raise FetchError(None, f"connection dropped: {exc}") from exc
            finally:
                resp.close()

        return resp.status, {k.lower(): v for k, v in resp.headers.items()}, body()


FETCHER = Fetcher()


# ---------------------------------------------------------------------------
# Pull: conditional, resumable download → editions/<ed>/partNN.xml
# ---------------------------------------------------------------------------


def detect_edition(xml_path: Path) -> str | None:
    """Edition string ('2026d') from the book subtitle — a cheap pre-pass before indexing."""
    for _, elem in etree.iterparse(str(xml_path), events=("end",), tag=(f"{NS}subtitle", f"{NS}title"), huge_tree=True):
        m = EDITION_RE.search("".join(elem.itertext()))
        if m:
            return m.group(1)
        if elem.tag == f"{NS}subtitle":
            break
    return None


class Progress:
    def __init__(self, part: int, total: int | None, done: int = 0):
        self.part, self.total, self.done = part, total, done
        self.t0 = self.last = time.monotonic()
        self.start = done

    def tick(self, n: int) -> None:
        self.done += n
        t = time.monotonic()
        if t - self.last < 1.0:
            return
        self.last = t
        rate = (self.done - self.start) / max(t - self.t0, 1e-6)
        if self.total:
            pct = 100 * self.done / self.total
            eta = (self.total - self.done) / rate if rate > 0 else 0
            note(
                f"part{self.part:02d}  {self.done / 1e6:.1f}/{self.total / 1e6:.1f} MB  {pct:3.0f}%  {rate / 1024:.0f} KB/s  eta {int(eta // 60)}:{int(eta % 60):02d}"
            )
        else:
            note(f"part{self.part:02d}  {self.done / 1e6:.1f} MB  {rate / 1024:.0f} KB/s")


def download(part: int, url: str, head: dict[str, str]) -> Path:
    """Download to incoming/partNN.xml.part with Range resume; returns the completed .part path."""
    inc = incoming_dir()
    inc.mkdir(parents=True, exist_ok=True)
    part_file = inc / f"part{part:02d}.xml.part"
    meta_file = inc / f"part{part:02d}.meta.json"
    etag = head.get("etag")
    length = int(head["content-length"]) if head.get("content-length", "").isdigit() else None

    start = 0
    if part_file.exists() and meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        if meta.get("url") == url and meta.get("etag") == etag and etag:
            start = part_file.stat().st_size
        else:
            part_file.unlink(missing_ok=True)
    meta_file.write_text(json.dumps({"url": url, "etag": etag, "length": length}), encoding="utf-8")

    if length is not None and start and start >= length:
        return part_file  # already complete from an earlier interrupted run

    status, headers, body = FETCHER.get(url, start or None)
    if status == 416:
        if length is not None and part_file.exists() and part_file.stat().st_size == length:
            return part_file
        part_file.unlink(missing_ok=True)
        status, headers, body = FETCHER.get(url, None)
        start = 0
    mode = "ab" if status == 206 else "wb"
    if status == 200:
        start = 0
    if start:
        note(f"part{part:02d}  resuming at {start / 1e6:.1f} MB")
    prog = Progress(part, length, start)
    with part_file.open(mode) as fh:
        for chunk in body:
            fh.write(chunk)
            prog.tick(len(chunk))
    size = part_file.stat().st_size
    if length is not None and size != length:
        if size > length:
            part_file.unlink(missing_ok=True)
            raise FetchError(None, f"download is {size} bytes but upstream announced {length} — discarded")
        raise FetchError(None, f"connection closed early: {size} of {length} bytes")
    return part_file


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pull_part(conn: sqlite3.Connection, manifest: dict[str, Any], part: int, edition: str | None, force: bool) -> dict[str, Any]:
    url = part_url(part, edition)
    try:
        head = FETCHER.head(url)
    except FetchError as exc:
        if exc.status == 404 and edition:
            fail(
                EXIT_STALE,
                f"PS3.{part} edition {edition} is not published at its pinned path — the live edition is only under `current`; drop --edition (or pick a superseded edition such as 2025b)",
            )
        if exc.status == 404:
            fail(EXIT_STALE, f"PS3.{part} not found upstream ({url})")
        fail(EXIT_ENV, str(exc))

    entry = part_entry(manifest, part)
    etag = head.get("etag")
    if entry and not force and etag and entry.get("etag") == etag and entry.get("url") == url and part_xml_path(entry).is_file():
        return {"part": part, "edition": entry["edition"], "action": "up to date", "bytes": entry["bytes"]}

    try:
        tmp = download(part, url, head)
    except FetchError as exc:
        fail(EXIT_ENV, f"{exc} — rerun `pull {part}` to resume")

    ed = detect_edition(tmp)
    if not ed:
        tmp.unlink(missing_ok=True)
        fail(EXIT_ENV, f"downloaded PS3.{part} has no recognizable edition in its subtitle — not DocBook from dicom.nema.org?")
    digest = sha256_of(tmp)
    dest = editions_dir() / ed / f"part{part:02d}.xml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and sha256_of(dest) != digest:
        note(f"part{part:02d}  edition {ed} already cached with different content — replacing (errata re-publication)")
    os.replace(tmp, dest)
    (incoming_dir() / f"part{part:02d}.meta.json").unlink(missing_ok=True)

    manifest["parts"][str(part)] = {
        "edition": ed,
        "path": str(dest.relative_to(home())),
        "url": url,
        "fetched_at": now_iso(),
        "etag": etag,
        "last_modified": head.get("last-modified"),
        "sha256": digest,
        "bytes": dest.stat().st_size,
    }
    # index before publishing the manifest entry, so a concurrent read verb never meets an
    # unindexed part and starts its own reindex of the same file
    stats = index_part(conn, dest, part, ed, digest)
    save_manifest(manifest)
    return {"part": part, "edition": ed, "action": "fetched", "bytes": dest.stat().st_size, **stats}


def check_part(manifest: dict[str, Any], part: int) -> dict[str, Any]:
    entry = part_entry(manifest, part)
    url = entry["url"] if entry else part_url(part, None)
    try:
        head = FETCHER.head(url)
    except FetchError as exc:
        fail(EXIT_ENV, str(exc))
    if not entry:
        return {"part": part, "state": "not cached", "upstream_last_modified": head.get("last-modified")}
    same = (head.get("etag") == entry.get("etag")) if head.get("etag") and entry.get("etag") else (head.get("last-modified") == entry.get("last_modified"))
    return {
        "part": part,
        "edition": entry["edition"],
        "state": "up to date" if same else "changed",
        "upstream_last_modified": head.get("last-modified"),
    }


# ---------------------------------------------------------------------------
# SQLite index
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS parts (
  edition TEXT NOT NULL, part INTEGER NOT NULL, sha256 TEXT NOT NULL,
  schema_version INTEGER NOT NULL, indexed_at TEXT NOT NULL,
  PRIMARY KEY (part));
CREATE TABLE IF NOT EXISTS nodes (
  edition TEXT NOT NULL, part INTEGER NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL,
  label TEXT NOT NULL, title TEXT NOT NULL, parent_id TEXT, chapter_id TEXT NOT NULL,
  ord INTEGER NOT NULL, depth INTEGER NOT NULL,
  PRIMARY KEY (part, id));
CREATE INDEX IF NOT EXISTS nodes_parent ON nodes(part, parent_id, ord);
CREATE INDEX IF NOT EXISTS nodes_label ON nodes(part, label);
CREATE TABLE IF NOT EXISTS blocks (
  part INTEGER NOT NULL, node_id TEXT NOT NULL, ord INTEGER NOT NULL, kind TEXT NOT NULL,
  text_md TEXT NOT NULL,
  PRIMARY KEY (part, node_id, ord));
CREATE TABLE IF NOT EXISTS tables (
  part INTEGER NOT NULL, id TEXT NOT NULL, caption TEXT NOT NULL, columns_json TEXT NOT NULL,
  nrows INTEGER NOT NULL,
  PRIMARY KEY (part, id));
CREATE TABLE IF NOT EXISTS rows (
  part INTEGER NOT NULL, table_id TEXT NOT NULL, ord INTEGER NOT NULL, cells_json TEXT NOT NULL,
  PRIMARY KEY (part, table_id, ord));
CREATE TABLE IF NOT EXISTS dict (
  part INTEGER NOT NULL, tag TEXT NOT NULL, name TEXT NOT NULL, keyword TEXT NOT NULL,
  vr TEXT NOT NULL, vm TEXT NOT NULL, retired INTEGER NOT NULL, source_table TEXT NOT NULL,
  PRIMARY KEY (part, tag));
CREATE INDEX IF NOT EXISTS dict_keyword ON dict(keyword);
CREATE TABLE IF NOT EXISTS docs (
  rowid INTEGER PRIMARY KEY, part INTEGER NOT NULL, node_id TEXT NOT NULL, kind TEXT NOT NULL,
  label TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS docs_part ON docs(part);
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
  title, body, part UNINDEXED, node_id UNINDEXED, kind UNINDEXED, label UNINDEXED,
  content='docs', content_rowid='rowid', tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS docs_ai AFTER INSERT ON docs BEGIN
  INSERT INTO docs_fts(rowid, title, body, part, node_id, kind, label)
  VALUES (new.rowid, new.title, new.body, new.part, new.node_id, new.kind, new.label);
END;
CREATE TRIGGER IF NOT EXISTS docs_ad AFTER DELETE ON docs BEGIN
  INSERT INTO docs_fts(docs_fts, rowid, title, body, part, node_id, kind, label)
  VALUES ('delete', old.rowid, old.title, old.body, old.part, old.node_id, old.kind, old.label);
END;
"""

PART_TABLES = ("parts", "nodes", "blocks", "tables", "rows", "dict", "docs")


def fts5_available(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE temp.__fts_probe USING fts5(x)")
        conn.execute("DROP TABLE temp.__fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


_CONN: tuple[Path, sqlite3.Connection] | None = None  # one connection per index path, reused in-process


def connect() -> sqlite3.Connection:
    global _CONN
    ensure_home()
    path = db_path()
    if _CONN and _CONN[0] == path:
        return _CONN[1]
    if _CONN:
        _CONN[1].close()
        _CONN = None
    try:
        conn = sqlite3.connect(path)
    except sqlite3.Error as exc:
        fail(EXIT_ENV, f"cannot open index {path}: {exc}")
    conn.row_factory = sqlite3.Row
    if not fts5_available(conn):
        fail(EXIT_ENV, "this Python's sqlite3 lacks FTS5 — run via `uv run` (uv-managed CPython ships FTS5)")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")  # a background pull may hold the write lock for a few seconds
    conn.executescript(SCHEMA)
    _CONN = (path, conn)
    return conn


def open_index(manifest: dict[str, Any]) -> sqlite3.Connection:
    """Open the index and reconcile it with the manifest — reindex from cached XML, no network."""
    conn = connect()
    indexed = {r["part"]: r for r in conn.execute("SELECT part, edition, sha256, schema_version FROM parts")}
    wanted = {int(k): v for k, v in manifest["parts"].items()}
    stale = [p for p, e in wanted.items() if p not in indexed or indexed[p]["sha256"] != e["sha256"] or indexed[p]["schema_version"] != SCHEMA_VERSION]
    orphans = [p for p in indexed if p not in wanted]
    for p in orphans:
        delete_part(conn, p)
    if stale:
        note(f"reindexing {len(stale)} part(s) from cached XML ({', '.join(f'PS3.{p}' for p in stale)})")
        for p in stale:
            e = wanted[p]
            path = part_xml_path(e)
            if not path.is_file():
                fail(EXIT_STALE, f"PS3.{p} is in the manifest but {path} is missing — run: {script_name()} pull {p} --force")
            index_part(conn, path, p, e["edition"], e["sha256"])
    if orphans:
        conn.commit()
    return conn


def delete_part(conn: sqlite3.Connection, part: int) -> None:
    for t in PART_TABLES:
        conn.execute(f"DELETE FROM {t} WHERE part = ?", (part,))


# ---------------------------------------------------------------------------
# DocBook → index (iterparse per chapter) and → Markdown
# ---------------------------------------------------------------------------

STRUCTURAL = {f"{NS}chapter", f"{NS}section", f"{NS}glossary", f"{NS}bibliography", f"{NS}glossdiv", f"{NS}bibliodiv", f"{NS}appendix", f"{NS}preface"}
SKIP_BLOCKS = {f"{NS}title", f"{NS}subtitle", f"{NS}info", f"{NS}remark", f"{NS}titleabbrev", f"{NS}caption"}
MATHML = {
    "math",
    "mi",
    "mn",
    "mo",
    "mrow",
    "msub",
    "msup",
    "msubsup",
    "mfrac",
    "msqrt",
    "mroot",
    "mtable",
    "mtr",
    "mtd",
    "mtext",
    "mspace",
    "mfenced",
    "mphantom",
    "munderover",
    "munder",
    "mover",
    "mstyle",
    "semantics",
    "annotation",
    "inlineequation",
    "informalequation",
    "mathphrase",
}
KNOWN_INLINE = {
    # bibliography / front-matter inlines rendered as plain text
    "authorgroup",
    "issuenum",
    "pagenums",
    "volumenum",
    "seriesvolnums",
    "biblioset",
    "bibliomisc",
    "copyright",
    "holder",
    "year",
    "title",
    "author",
    "editor",
    "orgname",
    "personname",
    "firstname",
    "surname",
    "date",
    "edition",
    "publisher",
    "publishername",
    "pubdate",
    "citation",
    "foreignphrase",
    "bibliosource",
    "biblioid",
    "abstract",
    "productname",
    "wordasword",
    "releaseinfo",
    "emphasis",
    "superscript",
    "subscript",
    "link",
    "xref",
    "olink",
    "literal",
    "code",
    "abbrev",
    "acronym",
    "para",
    "simpara",
    "phrase",
    "quote",
    "term",
    "glossterm",
    "citetitle",
    "footnote",
    "anchor",
    "varname",
    "filename",
    "replaceable",
    "userinput",
    "uri",
    "trademark",
    "firstterm",
    "inlinemediaobject",
    "indexterm",
    "sup",
    "sub",
}
KNOWN_BLOCKS = {
    "para",
    "simpara",
    "itemizedlist",
    "orderedlist",
    "listitem",
    "variablelist",
    "varlistentry",
    "term",
    "note",
    "warning",
    "caution",
    "important",
    "tip",
    "programlisting",
    "literallayout",
    "screen",
    "figure",
    "informalfigure",
    "mediaobject",
    "table",
    "informaltable",
    "glossentry",
    "glossdef",
    "glosssee",
    "glossseealso",
    "biblioentry",
    "bibliomixed",
    "simplelist",
    "member",
    "blockquote",
    "formalpara",
    "equation",
    "informalequation",
    "example",
    "sidebar",
    "procedure",
    "step",
    "substeps",
}


def local(tag: Any) -> str:
    return tag.split("}", 1)[1] if isinstance(tag, str) and "}" in tag else str(tag)


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u200b", "")).strip()


@dataclass
class Node:
    id: str
    kind: str
    label: str
    title: str
    parent_id: str | None
    chapter_id: str
    ord: int
    depth: int


@dataclass
class Table:
    id: str
    caption: str
    columns: list[dict[str, str]]
    rows: list[list[str]]


@dataclass
class PartIndex:
    part: int
    edition: str
    nodes: list[Node] = field(default_factory=list)
    blocks: list[tuple[str, int, str, str]] = field(default_factory=list)  # node_id, ord, kind, text
    tables: list[Table] = field(default_factory=list)
    unknown: dict[str, int] = field(default_factory=dict)
    _seq: int = 0

    def synth_id(self, kind: str) -> str:
        self._seq += 1
        return f"{kind}_ps3{self.part}_{self._seq}"


class Renderer:
    """DocBook → Markdown over a whitelist; unknown elements render their children (and are counted)."""

    def __init__(self, idx: PartIndex):
        self.idx = idx

    # -- inline --------------------------------------------------------------

    def inline(self, el: etree._Element, plain: bool = False) -> str:
        """Mixed content → Markdown; `plain` drops emphasis/code markers (table cells are data, not prose)."""
        out: list[str] = [el.text or ""]
        for child in el:
            if not isinstance(child.tag, str):  # comment / PI
                out.append(child.tail or "")
                continue
            out.append(self.inline_one(child, plain))
            out.append(child.tail or "")
        return "".join(out)

    def inline_one(self, el: etree._Element, plain: bool = False) -> str:
        name = local(el.tag)
        if name == "emphasis":
            inner = squash(self.inline(el, plain))
            if not inner or plain:
                return inner
            role = el.get("role", "")
            return f"**{inner}**" if "bold" in role else f"*{inner}*"
        if name in ("superscript", "sup"):
            return f"^{squash(self.inline(el, plain))}^"
        if name in ("subscript", "sub"):
            return f"~{squash(self.inline(el, plain))}~"
        if name in ("literal", "code", "varname", "filename", "userinput", "replaceable"):
            inner = squash(self.inline(el, plain))
            return inner if plain else f"`{inner}`"
        if name == "link":
            href = el.get(XL_HREF) or el.get("linkend") or ""
            text = squash(self.inline(el, plain)) or href
            if el.get("linkend") and not el.get(XL_HREF):
                return f"[[ref:{self.idx.part}:{el.get('linkend')}]]"
            if plain:
                return text
            return f"[{text}]({href})" if href else text
        if name == "xref":
            return f"[[ref:{self.idx.part}:{el.get('linkend', '')}]]"
        if name == "olink":
            doc = el.get("targetdoc", "")
            ptr = el.get("targetptr", "")
            m = re.fullmatch(r"PS3\.(\d+)", doc)
            if not m:
                return squash(self.inline(el, plain)) or ptr
            if ptr == doc or not ptr:
                return doc
            return f"[[ref:{m.group(1)}:{ptr}]]"
        if name == "footnote":
            return f" ({squash(self.inline(el, plain))})"
        if name in ("anchor", "indexterm", "remark"):
            return ""
        if name == "inlinemediaobject":
            return "[image]"
        if name in MATHML:
            return squash("".join(el.itertext()))
        if name in KNOWN_BLOCKS and name not in KNOWN_INLINE:
            # a list or note inside a table cell / paragraph: flatten to one line
            return " " + squash(self.block(el, 0).replace("\n", " ")) + " "
        if name not in KNOWN_INLINE:
            self.idx.unknown[name] = self.idx.unknown.get(name, 0) + 1
        return self.inline(el, plain)

    def text(self, el: etree._Element, plain: bool = False) -> str:
        return squash(self.inline(el, plain))

    # -- blocks --------------------------------------------------------------

    def block(self, el: etree._Element, depth: int = 0) -> str:
        """Render one block element to Markdown (may be several lines). Empty string = nothing."""
        name = local(el.tag)
        pad = "  " * depth
        if name in ("para", "simpara", "formalpara"):
            return self.para(el, pad)
        if name in ("itemizedlist", "orderedlist", "simplelist", "procedure", "substeps"):
            return self.list(el, depth)
        if name == "variablelist":
            return self.varlist(el, depth)
        if name in ("note", "warning", "caution", "important", "tip"):
            label = name.capitalize()
            inner = self.children(el, depth)
            lines = [ln for ln in inner.split("\n") if ln.strip()]
            if not lines:
                return ""
            return f"{pad}> **{label}:** " + lines[0].strip() + "".join(f"\n{pad}> {ln.strip()}" for ln in lines[1:])
        if name in ("programlisting", "literallayout", "screen"):
            code = "".join(el.itertext()).strip("\n")
            return f"{pad}```\n{code}\n{pad}```"
        if name in ("figure", "informalfigure"):
            return f"{pad}{self.figure_text(el)}"
        if name == "mediaobject":
            return f"{pad}[image — not cached]"
        if name in ("table", "informaltable"):
            return ""  # the walker turns tables into table-ref blocks
        if name == "glossentry":
            term = " ".join(self.text(t) for t in el.iterchildren(f"{NS}glossterm"))
            defs = [self.children(d, 0) for d in el.iterchildren(f"{NS}glossdef")]
            see = [self.text(s) for s in el.iterchildren(f"{NS}glosssee")]
            body = " ".join(x for x in defs if x) or (f"See {', '.join(see)}" if see else "")
            return f"{pad}**{term}**: {body}".rstrip(": ")
        if name in ("biblioentry", "bibliomixed"):
            ref = el.get(XML_ID, "")
            parts = [self.text(c) for c in el if isinstance(c.tag, str)]
            body = ". ".join(p for p in parts if p)
            return f"{pad}[{ref}] {body}" if ref else f"{pad}{body}"
        if name in ("blockquote", "example", "sidebar", "equation", "informalequation"):
            return self.children(el, depth)
        if name in ("step", "member", "listitem"):
            return self.children(el, depth)
        if el.tag in SKIP_BLOCKS or not isinstance(el.tag, str):
            return ""
        if (name in KNOWN_INLINE or name in MATHML) and name not in KNOWN_BLOCKS:
            inline = squash(self.inline_one(el))
            return f"{pad}{inline}" if inline else ""
        if name not in KNOWN_BLOCKS:
            self.idx.unknown[name] = self.idx.unknown.get(name, 0) + 1
        return self.children(el, depth)

    def para(self, el: etree._Element, pad: str) -> str:
        # A para may hold block children (lists, figures, tables) — split them out.
        head: list[str] = [el.text or ""]
        tail_blocks: list[str] = []
        for child in el:
            if not isinstance(child.tag, str):
                head.append(child.tail or "")
                continue
            cname = local(child.tag)
            if cname in KNOWN_BLOCKS and cname not in KNOWN_INLINE:
                rendered = self.block(child, 0)
                if cname in ("table", "informaltable"):
                    rendered = f"[[tableref:{child.get(XML_ID, '')}]]"
                if rendered:
                    tail_blocks.append(rendered)
                head.append(child.tail or "")
            else:
                head.append(self.inline_one(child))
                head.append(child.tail or "")
        first = squash("".join(head))
        out = [f"{pad}{first}"] if first else []
        out.extend(f"{pad}{b}" if not b.startswith(pad) else b for b in tail_blocks)
        return "\n".join(out)

    def list(self, el: etree._Element, depth: int) -> str:
        name = local(el.tag)
        ordered = name in ("orderedlist", "procedure", "substeps")
        pad = "  " * depth
        lines: list[str] = []
        n = 0
        for item in el:
            if not isinstance(item.tag, str) or local(item.tag) not in ("listitem", "member", "step"):
                continue
            n += 1
            marker = f"{n}." if ordered else "-"
            body = self.children(item, depth + 1)
            body_lines = [ln for ln in body.split("\n") if ln.strip()]
            if not body_lines:
                lines.append(f"{pad}{marker}")
                continue
            lines.append(f"{pad}{marker} {body_lines[0].strip()}")
            lines.extend(ln if ln.startswith("  " * (depth + 1)) else f"{'  ' * (depth + 1)}{ln.strip()}" for ln in body_lines[1:])
        return "\n".join(lines)

    def varlist(self, el: etree._Element, depth: int) -> str:
        pad = "  " * depth
        lines: list[str] = []
        for entry in el.iterchildren(f"{NS}varlistentry"):
            terms = ", ".join(self.text(t) for t in entry.iterchildren(f"{NS}term"))
            body = ""
            for item in entry.iterchildren(f"{NS}listitem"):
                body = self.children(item, depth + 1)
            body_lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
            first = body_lines[0] if body_lines else ""
            lines.append(f"{pad}- **{terms}**: {first}".rstrip(": "))
            lines.extend(f"{pad}  {ln}" for ln in body_lines[1:])
        return "\n".join(lines)

    def children(self, el: etree._Element, depth: int) -> str:
        out: list[str] = []
        lead = squash(el.text or "")
        if lead:
            out.append("  " * depth + lead)
        for child in el:
            if not isinstance(child.tag, str):
                continue
            if child.tag in SKIP_BLOCKS:
                continue
            r = self.block(child, depth)
            if r:
                out.append(r)
            tail = squash(child.tail or "")
            if tail:
                out.append("  " * depth + tail)
        return "\n".join(out)

    def figure_text(self, el: etree._Element) -> str:
        label = el.get("label", "")
        title = next((self.text(t) for t in el.iterchildren(f"{NS}title")), "")
        head = f"Figure {label}" if label else "Figure"
        return f"[{head}: {title} — image not cached]" if title else f"[{head} — image not cached]"


def cell_text(renderer: Renderer, td: etree._Element) -> str:
    """Plain text of a cell: paragraphs joined by a space, no Markdown markers (refs stay as placeholders)."""
    paras: list[str] = []
    for child in td:
        if not isinstance(child.tag, str):
            continue
        name = local(child.tag)
        if name in KNOWN_BLOCKS and name not in KNOWN_INLINE:  # a list or note in a cell → one line, markers kept
            paras.append(squash(renderer.block(child, 0).replace("\n", " ")))
        else:
            paras.append(renderer.text(child, plain=True))
    paras = [p for p in paras if p]
    if paras:
        return " ".join(paras)
    return squash(renderer.inline(td, plain=True))


def grid_rows(renderer: Renderer, trs: list[etree._Element]) -> list[list[str]]:
    """Expand an HTML-style row list into a dense grid: colspan repeats across, rowspan fills down."""
    rows: list[list[str]] = []
    pending: dict[int, tuple[str, int]] = {}
    for tr in trs:
        row: list[str] = []
        col = 0
        cells = [c for c in tr if isinstance(c.tag, str) and local(c.tag) in ("td", "th", "entry")]
        for cell in cells:
            while col in pending:
                val, rem = pending.pop(col)
                row.append(val)
                if rem > 1:
                    pending[col] = (val, rem - 1)
                col += 1
            text = cell_text(renderer, cell)
            cs = int(cell.get("colspan", "1") or 1)
            rs = int(cell.get("rowspan", "1") or 1)
            for _ in range(max(cs, 1)):
                row.append(text)
                if rs > 1:
                    pending[col] = (text, rs - 1)
                col += 1
        while col in pending:  # trailing spanned columns
            val, rem = pending.pop(col)
            row.append(val)
            if rem > 1:
                pending[col] = (val, rem - 1)
            col += 1
        rows.append(row)
    return rows


def column_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def parse_table(renderer: Renderer, el: etree._Element, idx: PartIndex) -> Table:
    tid = el.get(XML_ID) or idx.synth_id("table")
    caption = next((renderer.text(c) for c in el.iterchildren(f"{NS}caption")), "")
    if not caption:
        caption = next((renderer.text(c) for c in el.iterchildren(f"{NS}title")), "")
    head_trs: list[etree._Element] = []
    body_trs: list[etree._Element] = []
    for child in el.iter(f"{NS}thead", f"{NS}tbody", f"{NS}tfoot", f"{NS}tr"):
        if local(child.tag) == "tr":
            parent = child.getparent()
            if parent is not None and local(parent.tag) == "thead":
                head_trs.append(child)
            elif parent is not None and local(parent.tag) in ("tbody", "tfoot", "table", "informaltable", "tgroup"):
                body_trs.append(child)
    head = grid_rows(renderer, head_trs)
    body = grid_rows(renderer, body_trs)
    ncols = max([len(r) for r in head + body] or [0])
    body = [r + [""] * (ncols - len(r)) for r in body]
    head = [r + [""] * (ncols - len(r)) for r in head]
    names: list[str] = []
    for c in range(ncols):
        seen: list[str] = []
        for hr in head:
            v = hr[c]
            if v and v not in seen:
                seen.append(v)
        names.append(" / ".join(seen) or f"col{c + 1}")
    columns: list[dict[str, str]] = []
    used: dict[str, int] = {}
    for n in names:
        k = column_key(n) or "col"
        used[k] = used.get(k, 0) + 1
        if used[k] > 1:
            k = f"{k}_{used[k]}"
        columns.append({"name": n, "key": k})
    return Table(tid, caption, columns, body)


def walk_structure(el: etree._Element, idx: PartIndex, renderer: Renderer, parent: Node | None, chapter_id: str | None, depth: int, ord_: int) -> None:
    name = local(el.tag)
    nid = el.get(XML_ID) or idx.synth_id(name)
    label = el.get("label", "") or ""
    title = next((renderer.text(t) for t in el.iterchildren(f"{NS}title")), "")
    if not title and name in ("glossary", "bibliography"):
        title = name.capitalize()
    kind = {"chapter": "chapter", "appendix": "chapter", "preface": "chapter", "glossary": "glossary", "bibliography": "bibliography"}.get(name, "section")
    chap = chapter_id or nid
    node = Node(nid, kind, label, title, parent.id if parent else None, chap, ord_, depth)
    idx.nodes.append(node)
    block_ord = 0
    child_ord = 0
    for child in el:
        if not isinstance(child.tag, str) or child.tag in SKIP_BLOCKS:
            continue
        if child.tag in STRUCTURAL:
            child_ord += 1
            walk_structure(child, idx, renderer, node, chap, depth + 1, child_ord)
            continue
        cname = local(child.tag)
        if cname in ("table", "informaltable"):
            child_ord += 1
            block_ord += 1
            tbl = parse_table(renderer, child, idx)
            idx.tables.append(tbl)
            idx.nodes.append(Node(tbl.id, "table", child.get("label", "") or "", tbl.caption, nid, chap, child_ord, depth + 1))
            idx.blocks.append((nid, block_ord, "table-ref", f"[[tableref:{tbl.id}]]"))
            continue
        if cname in ("figure", "informalfigure"):
            child_ord += 1
            block_ord += 1
            fid = child.get(XML_ID) or idx.synth_id("figure")
            ftitle = next((renderer.text(t) for t in child.iterchildren(f"{NS}title")), "")
            idx.nodes.append(Node(fid, "figure", child.get("label", "") or "", ftitle, nid, chap, child_ord, depth + 1))
            idx.blocks.append((nid, block_ord, "figure-ref", renderer.figure_text(child)))
            continue
        kind_map = {
            "programlisting": "code",
            "literallayout": "code",
            "screen": "code",
            "note": "note",
            "warning": "note",
            "caution": "note",
            "important": "note",
            "tip": "note",
            "biblioentry": "biblio",
            "bibliomixed": "biblio",
            "glossentry": "gloss",
            "itemizedlist": "list",
            "orderedlist": "list",
            "variablelist": "list",
            "simplelist": "list",
            "procedure": "list",
        }
        text = renderer.block(child, 0)
        # tables nested inside a para surface as [[tableref:]] placeholders — register them too
        for tbl_el in child.iter(f"{NS}table", f"{NS}informaltable"):
            child_ord += 1
            tbl = parse_table(renderer, tbl_el, idx)
            idx.tables.append(tbl)
            idx.nodes.append(Node(tbl.id, "table", tbl_el.get("label", "") or "", tbl.caption, nid, chap, child_ord, depth + 1))
        for fig_el in child.iter(f"{NS}figure"):
            child_ord += 1
            fid = fig_el.get(XML_ID) or idx.synth_id("figure")
            ftitle = next((renderer.text(t) for t in fig_el.iterchildren(f"{NS}title")), "")
            idx.nodes.append(Node(fid, "figure", fig_el.get("label", "") or "", ftitle, nid, chap, child_ord, depth + 1))
        if text.strip():
            block_ord += 1
            idx.blocks.append((nid, block_ord, kind_map.get(cname, "para"), text))


def build_index(xml_path: Path, part: int, edition: str) -> PartIndex:
    idx = PartIndex(part, edition)
    renderer = Renderer(idx)
    top = (f"{NS}chapter", f"{NS}appendix", f"{NS}preface", f"{NS}glossary", f"{NS}bibliography")
    ord_ = 0
    ctx = etree.iterparse(str(xml_path), events=("end",), tag=top, huge_tree=True)
    for _, el in ctx:
        parent = el.getparent()
        if parent is None or local(parent.tag) != "book":
            continue  # nested glossary/bibliography inside a chapter is handled by the chapter walk
        ord_ += 1
        walk_structure(el, idx, renderer, None, None, 0, ord_)
        el.clear()
        while el.getprevious() is not None:
            del parent[0]
    del ctx
    return idx


def dict_rows(part: int, tables: list[Table]) -> list[tuple]:
    if part != 6:
        return []
    out: list[tuple] = []
    seen: set[str] = set()
    for t in tables:
        keys = [c["key"] for c in t.columns]
        if len(keys) < 5 or not keys[0].startswith("tag") or "keyword" not in keys or not any(k.startswith("vr") for k in keys):
            continue
        ki, vi, mi = (
            keys.index("keyword"),
            next(i for i, k in enumerate(keys) if k.startswith("vr")),
            next((i for i, k in enumerate(keys) if k.startswith("vm")), None),
        )
        for cells in t.rows:
            m = TAG_RE.search(cells[0])
            if not m:
                continue
            g, e = m.group(1), m.group(2)
            tag = f"({_norm_hex(g)},{_norm_hex(e)})"
            if tag in seen:
                continue
            seen.add(tag)
            rest = cells[max(ki, vi, mi or 0) + 1 :]
            retired = 1 if any(c.strip().upper().startswith("RET") for c in rest) else 0
            out.append((part, tag, cells[1], cells[ki], cells[vi], cells[mi] if mi is not None else "", retired, t.id))
    return out


def _norm_hex(s: str) -> str:
    return "".join(ch.lower() if ch in "xX" else ch.upper() for ch in s)


def index_part(conn: sqlite3.Connection, xml_path: Path, part: int, edition: str, sha256: str) -> dict[str, Any]:
    idx = build_index(xml_path, part, edition)
    with conn:
        delete_part(conn, part)
        conn.executemany(
            "INSERT INTO nodes(edition, part, id, kind, label, title, parent_id, chapter_id, ord, depth) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(edition, part, n.id, n.kind, n.label, n.title, n.parent_id, n.chapter_id, n.ord, n.depth) for n in _dedupe_nodes(idx.nodes)],
        )
        conn.executemany("INSERT INTO blocks(part, node_id, ord, kind, text_md) VALUES (?,?,?,?,?)", [(part, *b) for b in idx.blocks])
        conn.executemany(
            "INSERT OR REPLACE INTO tables(part, id, caption, columns_json, nrows) VALUES (?,?,?,?,?)",
            [(part, t.id, t.caption, json.dumps(t.columns, ensure_ascii=False), len(t.rows)) for t in idx.tables],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO rows(part, table_id, ord, cells_json) VALUES (?,?,?,?)",
            [(part, t.id, i, json.dumps(r, ensure_ascii=False)) for t in idx.tables for i, r in enumerate(t.rows, 1)],
        )
        conn.executemany("INSERT INTO dict(part, tag, name, keyword, vr, vm, retired, source_table) VALUES (?,?,?,?,?,?,?,?)", dict_rows(part, idx.tables))
        # FTS docs: one per section/chapter, one per table, one per table row
        bodies: dict[str, list[str]] = {}
        for node_id, _, kind, text in idx.blocks:
            if kind != "table-ref":
                bodies.setdefault(node_id, []).append(plain_ref(text))
        docs: list[tuple] = []
        for n in idx.nodes:
            if n.kind in ("chapter", "section", "glossary", "bibliography"):
                docs.append((part, n.id, "section", n.label, n.title, "\n".join(bodies.get(n.id, []))))
        for t in idx.tables:
            docs.append((part, t.id, "table", t.id.replace("table_", ""), t.caption, " | ".join(c["name"] for c in t.columns)))
            for i, r in enumerate(t.rows, 1):
                docs.append((part, t.id, "row", str(i), t.caption, plain_ref(" | ".join(c for c in r if c))))
        conn.executemany("INSERT INTO docs(part, node_id, kind, label, title, body) VALUES (?,?,?,?,?,?)", docs)
        conn.execute(
            "INSERT OR REPLACE INTO parts(edition, part, sha256, schema_version, indexed_at) VALUES (?,?,?,?,?)",
            (edition, part, sha256, SCHEMA_VERSION, now_iso()),
        )
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    stats = {
        "chapters": sum(1 for n in idx.nodes if n.kind == "chapter"),
        "sections": sum(1 for n in idx.nodes if n.kind == "section"),
        "tables": len(idx.tables),
        "blocks": len(idx.blocks),
    }
    if idx.unknown:
        note(f"part{part:02d}  unknown DocBook elements rendered as plain children: " + ", ".join(f"{k}×{v}" for k, v in sorted(idx.unknown.items())))
    return stats


def _dedupe_nodes(nodes: list[Node]) -> list[Node]:
    seen: set[str] = set()
    out: list[Node] = []
    for n in nodes:
        if n.id in seen:
            continue
        seen.add(n.id)
        out.append(n)
    return out


# ---------------------------------------------------------------------------
# Refs and lookups
# ---------------------------------------------------------------------------


def parse_ref(ref: str) -> tuple[int, str]:
    m = re.fullmatch(r"(?:PS3\.)?(\d{1,2}):(.+)", ref.strip(), re.IGNORECASE)
    if not m:
        fail(EXIT_PARAMS, f"bad ref '{ref}' — use PART:ID such as 15:E.1.1, 15:table_E.1-1, PS3.6:6-1, 15:E")
    part = int(m.group(1))
    if part not in PARTS:
        fail(EXIT_PARAMS, f"unknown part {part} in '{ref}' — parts: {', '.join(str(p) for p in PARTS)}")
    return part, m.group(2).strip()


def resolve_node(conn: sqlite3.Connection, part: int, tail: str) -> sqlite3.Row | None:
    def get(nid: str) -> sqlite3.Row | None:
        return conn.execute("SELECT * FROM nodes WHERE part = ? AND id = ?", (part, nid)).fetchone()

    if tail.startswith(NODE_PREFIXES):
        return get(tail)
    if re.fullmatch(r"[A-Z]|\d+", tail):
        return get(f"chapter_{tail}") or get(f"sect_{tail}")
    if "-" in tail:
        return get(f"table_{tail}") or get(f"figure_{tail}")
    if "." in tail:
        return get(f"sect_{tail}")
    for prefix in ("sect_", "table_", "figure_", "chapter_"):
        row = get(prefix + tail)
        if row:
            return row
    return conn.execute("SELECT * FROM nodes WHERE part = ? AND label = ? ORDER BY depth LIMIT 1", (part, tail)).fetchone()


def require_part(manifest: dict[str, Any], part: int, pull: bool, conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    entry = part_entry(manifest, part)
    if entry and part_xml_path(entry).is_file():
        return entry
    if pull and conn is not None:
        note(f"PS3.{part} not cached — pulling first (--pull)")
        pull_part(conn, manifest, part, None, False)
        return part_entry(manifest, part)  # type: ignore[return-value]
    fail(EXIT_STALE, f"PS3.{part} not cached — run: {script_name()} pull {part}   (or add --pull to this command)")


def source_line(entry: dict[str, Any], part: int, chapter_id: str, node_id: str | None) -> str:
    return f"source: DICOM PS3.{part} {entry['edition']} — {chtml_url(entry, part, chapter_id, node_id)}"


def source_obj(entry: dict[str, Any], part: int, chapter_id: str, node_id: str | None) -> dict[str, str]:
    return {"part": f"PS3.{part}", "edition": entry["edition"], "url": chtml_url(entry, part, chapter_id, node_id)}


def plain_ref(text: str) -> str:
    """Placeholders → readable labels without a DB lookup (used for the FTS bodies and snippets)."""

    def repl(m: re.Match) -> str:
        part, nid = m.group(1), m.group(2)
        for prefix, word in (("table_", "Table "), ("figure_", "Figure "), ("sect_", "Section "), ("chapter_", "Annex "), ("biblio_", "")):
            if nid.startswith(prefix):
                return f"{word}{nid[len(prefix) :]}"
        return f"PS3.{part} {nid}"

    return REF_PLACEHOLDER.sub(repl, text)


def resolve_placeholders(conn: sqlite3.Connection, manifest: dict[str, Any], text: str) -> str:
    def repl(m: re.Match) -> str:
        part, nid = int(m.group(1)), m.group(2)
        row = conn.execute("SELECT kind, label, title FROM nodes WHERE part = ? AND id = ?", (part, nid)).fetchone()
        if row is None:
            return f"PS3.{part} {nid} ({part}:{nid})"
        label = row["label"]
        if row["kind"] == "table":
            return f"Table {label} ({part}:{nid})" if label else f"table {nid} ({part}:{nid})"
        if row["kind"] == "figure":
            return f"Figure {label} ({part}:{nid})" if label else f"figure {nid} ({part}:{nid})"
        if row["kind"] == "chapter":
            head = f"Annex {label}" if label.isalpha() else f"Section {label}" if label else row["title"]
            return f"{head} {row['title']} ({part}:{nid})".replace("  ", " ")
        return f"§{label} {row['title']} ({part}:{nid})" if label else f"{row['title']} ({part}:{nid})"

    return REF_PLACEHOLDER.sub(repl, text)


def table_meta(conn: sqlite3.Connection, part: int, table_id: str) -> tuple[sqlite3.Row, list[dict[str, str]]]:
    t = conn.execute("SELECT * FROM tables WHERE part = ? AND id = ?", (part, table_id)).fetchone()
    return t, (json.loads(t["columns_json"]) if t else [])


def table_rows(conn: sqlite3.Connection, part: int, table_id: str) -> list[list[str]]:
    return [json.loads(r["cells_json"]) for r in conn.execute("SELECT cells_json FROM rows WHERE part = ? AND table_id = ? ORDER BY ord", (part, table_id))]


def md_table(columns: list[str], rows: list[list[str]]) -> str:
    esc = lambda s: s.replace("|", "\\|").replace("\n", " ")  # noqa: E731
    out = ["| " + " | ".join(esc(c) for c in columns) + " |", "|" + "---|" * len(columns)]
    out.extend("| " + " | ".join(esc(c) for c in r) + " |" for r in rows)
    return "\n".join(out)


def match_column(columns: list[dict[str, str]], want: str) -> int:
    key = column_key(want)
    keys = [c["key"] for c in columns]
    if key in keys:
        return keys.index(key)
    hits = [i for i, k in enumerate(keys) if key and key in k]
    if len(hits) == 1:
        return hits[0]
    listing = ", ".join(f"{c['key']} ({c['name']})" for c in columns)
    if not hits:
        fail(EXIT_PARAMS, f"no column matches '{want}' — columns: {listing}")
    fail(EXIT_PARAMS, f"'{want}' is ambiguous ({', '.join(keys[i] for i in hits)}) — columns: {listing}")


# ---------------------------------------------------------------------------
# Verbs
# ---------------------------------------------------------------------------

JsonOpt = Annotated[bool, typer.Option("--json", help="Machine-readable output.")]
PullOpt = Annotated[bool, typer.Option("--pull", help="Fetch the part first if it is not cached (read verbs are otherwise offline).")]


@app.command()
def status(
    max_age_days: Annotated[int, typer.Option("--max-age-days", help="Older cached parts count as stale (exit 1).")] = 90,
    as_json: JsonOpt = False,
) -> None:
    """Cached parts, their edition and age. Exit 1 when any part is stale or editions are mixed."""
    manifest = load_manifest()
    conn = open_index(manifest)
    rows: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    stale = False
    for key in sorted(manifest["parts"], key=int):
        e = manifest["parts"][key]
        age = (now - parse_iso(e["fetched_at"])).days
        is_stale = age > max_age_days
        stale = stale or is_stale
        indexed = conn.execute("SELECT 1 FROM parts WHERE part = ?", (int(key),)).fetchone() is not None
        rows.append(
            {
                "part": int(key),
                "title": PARTS.get(int(key), ""),
                "edition": e["edition"],
                "fetched_at": e["fetched_at"],
                "age_days": age,
                "bytes": e["bytes"],
                "indexed": indexed,
                "stale": is_stale,
            }
        )
    editions = sorted({r["edition"] for r in rows})
    mixed = len(editions) > 1
    report = {
        "home": str(home()),
        "cached_parts": len(rows),
        "editions": editions,
        "mixed": mixed,
        "stale": stale,
        "max_age_days": max_age_days,
        "parts": rows,
    }
    if as_json:
        emit(report)
    else:
        typer.echo(f"cache: {home()}")
        if not rows:
            typer.echo(f"no parts cached — pull what you need, e.g. `{script_name()} pull 15` (lazy by design)")
        else:
            typer.echo(f"{'part':<6}{'edition':<9}{'fetched':<12}{'age':>5}  {'size':>8}  {'index':<6} title")
            for r in rows:
                flag = " STALE" if r["stale"] else ""
                typer.echo(
                    f"PS3.{r['part']:<2} {r['edition']:<9}{r['fetched_at'][:10]:<12}{r['age_days']:>4}d  {r['bytes'] / 1e6:>6.1f}MB  {'ok' if r['indexed'] else 'MISSING':<6} {r['title']}{flag}"
                )
            if mixed:
                typer.echo(f"editions mixed: {', '.join(editions)} — `pull --all` (or pull the lagging parts) to align")
            else:
                typer.echo(f"edition: {editions[0]} (all {len(rows)} cached part{'s' if len(rows) != 1 else ''})")
    if stale or mixed:
        raise typer.Exit(EXIT_STALE)


@app.command()
def pull(
    parts: Annotated[list[str] | None, typer.Argument(help="Part numbers (15, PS3.6 …). Default: every cached part.")] = None,
    all_parts: Annotated[bool, typer.Option("--all", help="Every part of the standard (~124 MB; slow).")] = False,
    edition: Annotated[str | None, typer.Option("--edition", help="A superseded edition such as 2025b (the live edition is `current`).")] = None,
    check: Annotated[bool, typer.Option("--check", help="HEAD only: report up to date / changed / not cached; exit 1 if anything changed.")] = False,
    force: Annotated[bool, typer.Option("--force", help="Re-download even when the upstream ETag is unchanged.")] = False,
    as_json: JsonOpt = False,
) -> None:
    """Fetch or refresh parts (conditional GET, resumable), then index them. Network verb."""
    manifest = load_manifest()
    if all_parts:
        wanted = list(PARTS)
    elif parts:
        wanted = [parse_part(p) for p in parts]
    else:
        wanted = sorted(int(k) for k in manifest["parts"])
        if not wanted:
            fail(EXIT_PARAMS, "nothing to pull — name parts (e.g. `pull 15 6`) or pass --all")
    if edition and not re.fullmatch(r"\d{4}[a-e]", edition):
        fail(EXIT_PARAMS, f"bad edition '{edition}' — expected a year plus letter, e.g. 2025b")

    if check:
        results = [check_part(manifest, p) for p in wanted]
        if as_json:
            emit(results)
        else:
            for r in results:
                extra = f" (upstream Last-Modified {r['upstream_last_modified']})" if r["state"] != "up to date" and r.get("upstream_last_modified") else ""
                typer.echo(f"PS3.{r['part']:<3}{r['state']}{extra}")
        if any(r["state"] == "changed" for r in results):
            raise typer.Exit(EXIT_STALE)
        return

    conn = open_index(manifest)
    results = []
    for p in wanted:
        r = pull_part(conn, manifest, p, edition, force)
        results.append(r)
        if not as_json:
            if r["action"] == "fetched":
                typer.echo(
                    f"PS3.{p} {r['edition']}  {r['bytes'] / 1e6:.1f} MB  indexed: {r['chapters']} chapters, {r['sections']} sections, {r['tables']} tables, {r['blocks']} blocks"
                )
            else:
                typer.echo(f"PS3.{p} {r['edition']}  up to date")
    if as_json:
        emit(results)


@app.command()
def toc(
    part: Annotated[str, typer.Argument(help="Part number, e.g. 15 or PS3.15.")],
    under: Annotated[str | None, typer.Option("--under", help="Start at this node (id tail such as E, E.1, sect_E.1).")] = None,
    depth: Annotated[int, typer.Option("--depth", help="Levels below the start node; 0 = unlimited.")] = 2,
    pull_first: PullOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Outline of a part (or of one node): labels, titles, ids; tables marked with their size."""
    p = parse_part(part)
    manifest = load_manifest()
    conn = open_index(manifest)
    entry = require_part(manifest, p, pull_first, conn)
    root_id: str | None = None
    if under:
        node = resolve_node(conn, p, under)
        if node is None:
            fail(EXIT_STALE, f"no node '{under}' in PS3.{p} ({entry['edition']}) — try: {script_name()} toc {p}")
        root_id = node["id"]
    rows = conn.execute("SELECT * FROM nodes WHERE part = ? ORDER BY depth, ord", (p,)).fetchall()
    by_parent: dict[str | None, list[sqlite3.Row]] = {}
    for r in rows:
        by_parent.setdefault(r["parent_id"], []).append(r)
    sizes = {t["id"]: (t["nrows"], len(json.loads(t["columns_json"]))) for t in conn.execute("SELECT id, nrows, columns_json FROM tables WHERE part = ?", (p,))}

    out: list[dict[str, Any]] = []

    def visit(parent: str | None, level: int) -> None:
        if depth and level > depth:
            return
        for n in sorted(by_parent.get(parent, []), key=lambda r: r["ord"]):
            item = {"id": n["id"], "ref": f"{p}:{n['id']}", "kind": n["kind"], "label": n["label"], "title": n["title"], "level": level}
            if n["kind"] == "table" and n["id"] in sizes:
                item["rows"], item["cols"] = sizes[n["id"]]
            out.append(item)
            visit(n["id"], level + 1)

    if root_id:
        root = conn.execute("SELECT * FROM nodes WHERE part = ? AND id = ?", (p, root_id)).fetchone()
        out.append({"id": root["id"], "ref": f"{p}:{root['id']}", "kind": root["kind"], "label": root["label"], "title": root["title"], "level": 0})
        visit(root_id, 1)
    else:
        visit(None, 1)
    if as_json:
        emit({"part": f"PS3.{p}", "edition": entry["edition"], "nodes": out})
        return
    typer.echo(f"PS3.{p} {entry['edition']} — {PARTS[p]}" + (f" › {under}" if under else ""))
    for it in out:
        pad = "  " * max(it["level"] - (1 if not root_id else 0), 0)
        tag = ""
        if it["kind"] == "table":
            tag = f"  [table {it.get('rows', '?')}×{it.get('cols', '?')}]"
        elif it["kind"] == "figure":
            tag = "  [figure]"
        label = it["label"]
        typer.echo(f"{pad}{label + '  ' if label else ''}{it['title']}  ({it['ref']}){tag}")


@app.command()
def show(
    ref: Annotated[str, typer.Argument(help="PART:ID — 15:E.1.1, 15:sect_E.1, 15:E, 15:table_E.1-1.")],
    max_chars: Annotated[int, typer.Option("--max-chars", help="Truncate the body at a block boundary; 0 = no limit.")] = 12000,
    depth: Annotated[int, typer.Option("--depth", help="Inline subsections this many levels deep (default: list them only).")] = 0,
    pull_first: PullOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Render a section (or chapter) to Markdown. Big tables become pointers; the last line is the citation."""
    p, tail = parse_ref(ref)
    manifest = load_manifest()
    conn = open_index(manifest)
    entry = require_part(manifest, p, pull_first, conn)
    node = resolve_node(conn, p, tail)
    if node is None:
        hint = f"toc {p} --under {tail.split('.')[0]}" if "." in tail else f"toc {p}"
        fail(EXIT_STALE, f"no node '{tail}' in PS3.{p} ({entry['edition']}) — try: {script_name()} {hint}")
    if node["kind"] == "table":
        _show_table(conn, manifest, entry, p, node, as_json)
        return

    def render_node(n: sqlite3.Row, level: int) -> tuple[list[str], list[dict[str, Any]]]:
        lines: list[str] = []
        kids: list[dict[str, Any]] = []
        heading = "#" * min(level + 1, 6)
        label = n["label"]
        title_line = f"{heading} {label + ' ' if label else ''}{n['title']}".rstrip()
        lines.append(title_line)
        for b in conn.execute("SELECT kind, text_md FROM blocks WHERE part = ? AND node_id = ? ORDER BY ord", (p, n["id"])):
            text = b["text_md"]
            text = re.sub(r"\[\[tableref:([^\]]+)\]\]", lambda m: _table_inline_or_pointer(conn, p, m.group(1)), text)
            lines.append(resolve_placeholders(conn, manifest, text))
        children = conn.execute(
            "SELECT * FROM nodes WHERE part = ? AND parent_id = ? AND kind IN ('section','chapter','glossary','bibliography') ORDER BY ord", (p, n["id"])
        ).fetchall()
        for c in children:
            kids.append({"ref": f"{p}:{c['id']}", "label": c["label"], "title": c["title"]})
        if children:
            if level < depth:
                for c in children:
                    sub_lines, _ = render_node(c, level + 1)
                    lines.append("")
                    lines.extend(sub_lines)
            else:
                lines.append("")
                lines.append("Subsections:")
                lines.extend(f"- {c['label'] + ' ' if c['label'] else ''}{c['title']}  ({p}:{c['id']})" for c in children)
        return lines, kids

    lines, kids = render_node(node, 0)
    body = "\n\n".join(ln for ln in _join_blocks(lines))
    truncated = False
    if max_chars and len(body) > max_chars:
        cut = body.rfind("\n", 0, max_chars)
        body = body[: cut if cut > 0 else max_chars].rstrip() + f"\n\n… [truncated at {max_chars} chars; --max-chars 0 for all]"
        truncated = True
    src = source_line(entry, p, node["chapter_id"], node["id"])
    if as_json:
        emit(
            {
                "ref": f"{p}:{node['id']}",
                "kind": node["kind"],
                "label": node["label"],
                "title": node["title"],
                "markdown": body,
                "truncated": truncated,
                "children": kids,
                "source": source_obj(entry, p, node["chapter_id"], node["id"]),
            }
        )
        return
    typer.echo(body)
    typer.echo("")
    typer.echo(src)


def _join_blocks(lines: list[str]) -> list[str]:
    # headings and the Subsections list keep single newlines; blocks are separated by blank lines
    out: list[str] = []
    buf: list[str] = []
    for ln in lines:
        if ln == "":
            if buf:
                out.append("\n".join(buf))
                buf = []
            continue
        if ln.startswith("- ") and buf and (buf[-1].startswith("- ") or buf[-1] == "Subsections:"):
            buf.append(ln)
            continue
        if buf:
            out.append("\n".join(buf))
        buf = [ln]
    if buf:
        out.append("\n".join(buf))
    return out


def _table_inline_or_pointer(conn: sqlite3.Connection, part: int, table_id: str) -> str:
    t, columns = table_meta(conn, part, table_id)
    if t is None:
        return f"[table {table_id}]"
    label = table_id.replace("table_", "")
    head = f"Table {label}" + (f" — {t['caption']}" if t["caption"] else "")
    if t["nrows"] <= INLINE_TABLE_MAX[0] and len(columns) <= INLINE_TABLE_MAX[1]:
        return f"{head}\n\n" + md_table([c["name"] for c in columns], table_rows(conn, part, table_id))  # placeholders resolved by the caller
    return f"> {head} ({t['nrows']} rows × {len(columns)} cols) → `table {part}:{table_id}`"


def _show_table(conn: sqlite3.Connection, manifest: dict[str, Any], entry: dict[str, Any], part: int, node: sqlite3.Row, as_json: bool) -> None:
    t, columns = table_meta(conn, part, node["id"])
    info = {
        "ref": f"{part}:{node['id']}",
        "kind": "table",
        "label": node["label"],
        "caption": t["caption"],
        "rows": t["nrows"],
        "columns": columns,
        "source": source_obj(entry, part, node["chapter_id"], node["id"]),
    }
    if as_json:
        emit(info)
        return
    typer.echo(f"Table {node['label']} — {t['caption']}  ({t['nrows']} rows × {len(columns)} cols)")
    typer.echo("columns: " + ", ".join(f"{c['key']} ({c['name']})" for c in columns))
    typer.echo(f"rows: {script_name()} table {part}:{node['id']} [--where key=value] [--columns a,b] [--limit N]")
    typer.echo("")
    typer.echo(source_line(entry, part, node["chapter_id"], node["id"]))


@app.command()
def table(
    ref: Annotated[str, typer.Argument(help="PART:TABLE — 15:E.1-1, 15:table_E.1-1, 6:6-1.")],
    where: Annotated[list[str] | None, typer.Option("--where", help='Filter: "col=value" (exact, case-insensitive) or "col~regex". Repeat for AND.')] = None,
    columns: Annotated[str | None, typer.Option("--columns", help="Comma-separated column keys (or unique substrings) to print.")] = None,
    fmt: Annotated[str, typer.Option("--format", help="md | json | csv")] = "md",
    limit: Annotated[int, typer.Option("--limit", help="Rows to print; 0 = all.")] = 50,
    pull_first: PullOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """Rows of a table, filtered by column. Column keys are lowercase alnum (`Basic Prof.` → basicprof)."""
    if fmt not in ("md", "json", "csv"):
        fail(EXIT_PARAMS, f"--format must be md, json or csv (got '{fmt}')")
    if as_json:
        fmt = "json"
    p, tail = parse_ref(ref)
    manifest = load_manifest()
    conn = open_index(manifest)
    entry = require_part(manifest, p, pull_first, conn)
    node = resolve_node(conn, p, tail)
    if node is None or node["kind"] != "table":
        kind = f" ({node['kind']})" if node else ""
        fail(EXIT_STALE, f"no table '{tail}' in PS3.{p} ({entry['edition']}){kind} — list tables: {script_name()} toc {p} --depth 0 | grep table")
    t, cols = table_meta(conn, p, node["id"])
    rows = table_rows(conn, p, node["id"])

    filters: list[tuple[int, str, Any]] = []
    for w in where or []:
        m = re.fullmatch(r"\s*([^=~]+?)\s*(=|~)\s*(.*)", w)
        if not m:
            fail(EXIT_PARAMS, f"bad --where '{w}' — use col=value or col~regex")
        ci = match_column(cols, m.group(1))
        if m.group(2) == "~":
            try:
                filters.append((ci, "~", re.compile(m.group(3), re.IGNORECASE)))
            except re.error as exc:
                fail(EXIT_PARAMS, f"bad regex in --where '{w}': {exc}")
        else:
            filters.append((ci, "=", m.group(3).strip().lower()))
    selected = [r for r in rows if all((rx.search(r[ci]) if op == "~" else r[ci].strip().lower() == rx) for ci, op, rx in filters)]
    total = len(selected)
    if limit:
        selected = selected[:limit]
    col_idx = [match_column(cols, c.strip()) for c in columns.split(",")] if columns else list(range(len(cols)))
    names = [cols[i]["name"] for i in col_idx]
    keys = [cols[i]["key"] for i in col_idx]
    projected = [[resolve_placeholders(conn, manifest, r[i]) for i in col_idx] for r in selected]
    src = source_obj(entry, p, node["chapter_id"], node["id"])

    if fmt == "json":
        emit(
            {
                "ref": f"{p}:{node['id']}",
                "caption": t["caption"],
                "columns": [{"name": n, "key": k} for n, k in zip(names, keys)],
                "rows": [dict(zip(keys, r)) for r in projected],
                "shown": len(projected),
                "total": total,
                "all_rows": t["nrows"],
                "source": src,
            }
        )
        return
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(names)
        w.writerows(projected)
        typer.echo(buf.getvalue().rstrip("\n"))
        return
    typer.echo(f"Table {node['label']} — {t['caption']}")
    typer.echo("")
    typer.echo(md_table(names, projected))
    typer.echo("")
    footer = f"{len(projected)} of {total} matching rows" if filters else f"{len(projected)} of {total} rows"
    if total > len(projected):
        footer += " — --limit 0 for all"
    typer.echo(footer + f" (table has {t['nrows']} rows × {len(cols)} cols)")
    typer.echo(source_line(entry, p, node["chapter_id"], node["id"]))


@app.command()
def search(
    query: Annotated[str, typer.Argument(help='FTS5 query: words, "exact phrase", AND/OR/NOT, prefix*.')],
    part: Annotated[list[str] | None, typer.Option("--part", help="Restrict to these parts (repeatable).")] = None,
    kind: Annotated[str | None, typer.Option("--kind", help="section | table | row")] = None,
    limit: Annotated[int, typer.Option("--limit")] = 20,
    as_json: JsonOpt = False,
) -> None:
    """Keyword search over every cached part (sections, table captions, table rows), ranked by BM25."""
    if kind and kind not in ("section", "table", "row"):
        fail(EXIT_PARAMS, "--kind must be section, table or row")
    manifest = load_manifest()
    conn = open_index(manifest)
    if not manifest["parts"]:
        fail(EXIT_STALE, f"nothing cached — run: {script_name()} pull 15 (or any part)")
    parts = [parse_part(x) for x in part] if part else None
    for px in parts or []:
        require_part(manifest, px, False)
    sql = (
        "SELECT part, node_id, kind, label, title, snippet(docs_fts, 1, '[', ']', '…', 24) AS snip, bm25(docs_fts) AS rank FROM docs_fts WHERE docs_fts MATCH ?"
    )
    args: list[Any] = [query]
    if parts:
        sql += f" AND part IN ({','.join('?' * len(parts))})"
        args.extend(parts)
    if kind:
        sql += " AND kind = ?"
        args.append(kind)
    sql += " ORDER BY rank LIMIT ?"
    args.append(limit)
    try:
        hits = conn.execute(sql, args).fetchall()
    except sqlite3.OperationalError:
        # FTS syntax error (e.g. parentheses in a tag) → quote every token and retry
        args[0] = " ".join(f'"{tok}"' for tok in re.findall(r"\S+", query.replace('"', " ")))
        try:
            hits = conn.execute(sql, args).fetchall()
        except sqlite3.OperationalError as exc:
            fail(EXIT_PARAMS, f"FTS query rejected: {exc}")
    results = []
    for h in hits:
        entry = part_entry(manifest, h["part"])
        if h["kind"] == "row":
            ref = f"{h['part']}:{h['node_id']}#row{h['label']}"
        else:
            ref = f"{h['part']}:{h['node_id']}"
        chapter = conn.execute("SELECT chapter_id FROM nodes WHERE part = ? AND id = ?", (h["part"], h["node_id"])).fetchone()
        results.append(
            {
                "ref": ref,
                "part": h["part"],
                "kind": h["kind"],
                "label": h["label"],
                "title": h["title"],
                "snippet": plain_ref(squash(h["snip"])),
                "edition": entry["edition"] if entry else None,
                "url": chtml_url(entry, h["part"], chapter["chapter_id"], h["node_id"]) if entry and chapter else None,
            }
        )
    if as_json:
        emit({"query": query, "hits": results})
        return
    if not results:
        typer.echo(f"no hits for {query!r} in {', '.join(f'PS3.{p}' for p in (parts or sorted(int(k) for k in manifest['parts'])))}")
        raise typer.Exit(EXIT_STALE)
    for r in results:
        head = f"{r['ref']:<28} {r['kind']:<8}"
        if r["kind"] == "row":
            typer.echo(f"{head} {r['title']} — {r['snippet']}")
        else:
            typer.echo(f"{head} {r['label'] + ' ' if r['label'] else ''}{r['title']} — {r['snippet']}")


@app.command()
def tag(
    query: Annotated[str, typer.Argument(help="(gggg,eeee) or a Keyword such as PatientName.")],
    pull_first: PullOpt = False,
    as_json: JsonOpt = False,
) -> None:
    """PS3.6 data-dictionary entry for a tag or keyword, plus its PS3.15 Table E.1-1 de-identification actions when PS3.15 is cached."""
    manifest = load_manifest()
    conn = open_index(manifest)
    entry6 = require_part(manifest, 6, pull_first, conn)
    m = TAG_RE.search(query)
    if m:
        key = f"({_norm_hex(m.group(1))},{_norm_hex(m.group(2))})"
        row = conn.execute("SELECT * FROM dict WHERE part = 6 AND tag = ?", (key,)).fetchone()
        if row is None:  # try the wildcard patterns, e.g. (60xx,0010) for (6002,0010)
            for cand in conn.execute("SELECT * FROM dict WHERE part = 6 AND tag LIKE '%x%'"):
                pat = "^" + re.escape(cand["tag"]).replace("x", "[0-9A-F]") + "$"
                if re.match(pat, key):
                    row = cand
                    break
    else:
        row = conn.execute("SELECT * FROM dict WHERE part = 6 AND lower(keyword) = lower(?)", (query.strip(),)).fetchone()
    if row is None:
        fail(EXIT_STALE, f"no data element '{query}' in PS3.6 {entry6['edition']} — try: {script_name()} search \"{query}\" --part 6")
    tnode = conn.execute("SELECT chapter_id FROM nodes WHERE part = 6 AND id = ?", (row["source_table"],)).fetchone()
    result: dict[str, Any] = {
        "tag": row["tag"],
        "name": row["name"],
        "keyword": row["keyword"],
        "vr": row["vr"],
        "vm": row["vm"],
        "retired": bool(row["retired"]),
        "source": source_obj(entry6, 6, tnode["chapter_id"] if tnode else "chapter_6", row["source_table"]),
    }
    deid: dict[str, str] | None = None
    entry15 = part_entry(manifest, 15)
    if entry15 and conn.execute("SELECT 1 FROM tables WHERE part = 15 AND id = 'table_E.1-1'").fetchone():
        _, cols = table_meta(conn, 15, "table_E.1-1")
        keys = [c["key"] for c in cols]
        if "tag" in keys:
            ti = keys.index("tag")
            for r in table_rows(conn, 15, "table_E.1-1"):
                if TAG_RE.search(r[ti]) and f"({_norm_hex(TAG_RE.search(r[ti]).group(1))},{_norm_hex(TAG_RE.search(r[ti]).group(2))})" == row["tag"]:
                    deid = {cols[i]["name"]: r[i] for i in range(len(cols)) if r[i] and cols[i]["key"] not in ("attributename", "tag")}
                    break
        node15 = conn.execute("SELECT chapter_id FROM nodes WHERE part = 15 AND id = 'table_E.1-1'").fetchone()
        result["deidentification"] = (
            {"table": "15:table_E.1-1", "actions": deid, "source": source_obj(entry15, 15, node15["chapter_id"], "table_E.1-1")} if deid else None
        )
    if as_json:
        emit(result)
        return
    ret = "  RETIRED" if result["retired"] else ""
    typer.echo(f"{result['tag']}  {result['keyword']}  VR {result['vr']}  VM {result['vm']}  — {result['name']}{ret}")
    if deid:
        typer.echo("PS3.15 Table E.1-1: " + " · ".join(f"{k}: {v}" for k, v in deid.items()))
    elif entry15:
        typer.echo("PS3.15 Table E.1-1: not listed (no de-identification action for this element)")
    else:
        typer.echo(f"PS3.15 not cached — `{script_name()} pull 15` adds the E.1-1 de-identification actions")
    typer.echo("")
    typer.echo(f"source: DICOM PS3.6 {entry6['edition']} — {result['source']['url']}")
    if deid:
        typer.echo(f"source: DICOM PS3.15 {entry15['edition']} — {result['deidentification']['source']['url']}")


if __name__ == "__main__":
    app()
