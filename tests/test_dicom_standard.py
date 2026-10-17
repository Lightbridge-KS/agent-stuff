#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer>=0.12", "lxml>=5"]
# ///
"""Contract tests for the dicom-standard skill's dicom_std.py CLI.

Offline by default: the module is imported in-process, the network seam (FETCHER) is replaced
by a fake that serves the hand-made DocBook fixtures with real HEAD / Range / 206 / 416
semantics, and the cache lives in a temp DICOM_STD_HOME. These pin the ref grammar, the
index shape, the DocBook → Markdown renderer, the table grid (colspan / rowspan), every verb's
output and exit code, resumable pull, and the schema-bump reindex.

    uv run tests/test_dicom_standard.py
    DICOM_STD_LIVE=1 uv run tests/test_dicom_standard.py     # + real pull of PS3.15 (3.4 MB) and PS3.6 (9 MB)
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = REPO_ROOT / "plugins" / "radiology" / "skills" / "dicom-standard"
SCRIPT = SKILL / "scripts" / "dicom_std.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "dicom-standard"

spec = importlib.util.spec_from_file_location("dicom_std", SCRIPT)
ds = importlib.util.module_from_spec(spec)
sys.modules["dicom_std"] = ds
spec.loader.exec_module(ds)

runner = CliRunner()

PART15 = (FIXTURES / "part15.xml").read_bytes()
PART06 = (FIXTURES / "part06.xml").read_bytes()
URL15 = ds.part_url(15, None)
URL06 = ds.part_url(6, None)


class FakeFetcher:
    """Serves bytes per URL with HEAD / Range semantics; `fail_after` drops the connection mid-body."""

    def __init__(self, files: dict[str, bytes], fail_after: int | None = None, chunk: int = 500):
        self.files = files
        self.fail_after = fail_after
        self.chunk = chunk
        self.calls: list[tuple] = []

    def _headers(self, body: bytes) -> dict[str, str]:
        return {
            "etag": '"' + hashlib.sha1(body).hexdigest()[:12] + '"',
            "content-length": str(len(body)),
            "last-modified": "Sun, 20 Sep 2026 12:20:10 GMT",
            "accept-ranges": "bytes",
        }

    def head(self, url):
        self.calls.append(("HEAD", url))
        if url not in self.files:
            raise ds.FetchError(404, f"HTTP 404 for {url}")
        return self._headers(self.files[url])

    def get(self, url, start=None):
        self.calls.append(("GET", url, start))
        if url not in self.files:
            raise ds.FetchError(404, f"HTTP 404 for {url}")
        body = self.files[url]
        if start:
            if start >= len(body):
                return 416, self._headers(body), iter(())
            return 206, self._headers(body), self._body(body[start:])
        return 200, self._headers(body), self._body(body)

    def _body(self, data: bytes):
        sent = 0
        for i in range(0, len(data), self.chunk):
            piece = data[i : i + self.chunk]
            if self.fail_after is not None and sent + len(piece) > self.fail_after:
                yield piece[: self.fail_after - sent]
                raise ds.FetchError(None, "connection dropped: simulated")
            sent += len(piece)
            yield piece


class NoNetwork:
    def head(self, url):
        raise AssertionError(f"unexpected network call HEAD {url}")

    def get(self, url, start=None):
        raise AssertionError(f"unexpected network call GET {url}")


def invoke(*args: str):
    return runner.invoke(ds.app, list(args))


class CacheCase(unittest.TestCase):
    """A temp cache per test class, fixtures pulled through the fake fetcher."""

    pull_parts: tuple[str, ...] = ("15", "6")

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls._env = mock.patch.dict(os.environ, {ds.HOME_ENV: cls._tmp.name})
        cls._env.start()
        cls.fetcher = FakeFetcher({URL15: PART15, URL06: PART06})
        ds.FETCHER = cls.fetcher
        if cls.pull_parts:
            r = invoke("pull", *cls.pull_parts)
            assert r.exit_code == 0, r.output
        ds.FETCHER = NoNetwork()

    @classmethod
    def tearDownClass(cls):
        ds.FETCHER = ds.Fetcher()
        cls._env.stop()
        cls._tmp.cleanup()

    def db(self) -> sqlite3.Connection:
        c = sqlite3.connect(ds.db_path())
        c.row_factory = sqlite3.Row
        self.addCleanup(c.close)
        return c


# ---------------------------------------------------------------------------


class TestRefNormalizer(unittest.TestCase):
    def test_parse_ref_forms(self):
        self.assertEqual(ds.parse_ref("15:E.1.1"), (15, "E.1.1"))
        self.assertEqual(ds.parse_ref("PS3.15:table_E.1-1"), (15, "table_E.1-1"))
        self.assertEqual(ds.parse_ref("6:6-1"), (6, "6-1"))

    def test_bad_ref_exits_2(self):
        for bad in ("E.1.1", "99:E.1", "15:"):
            with self.subTest(bad=bad):
                r = invoke("show", bad)
                self.assertEqual(r.exit_code, 2, r.output)

    def test_parse_part(self):
        self.assertEqual(ds.parse_part("PS3.6"), 6)
        self.assertEqual(ds.parse_part("15"), 15)
        r = invoke("toc", "9")
        self.assertEqual(r.exit_code, 2)
        self.assertIn("unknown part", r.output)


class TestIndex(CacheCase):
    def test_nodes_shape(self):
        c = self.db()
        kinds = dict(c.execute("SELECT kind, count(*) FROM nodes WHERE part = 15 GROUP BY kind").fetchall())
        self.assertEqual(kinds["chapter"], 3)
        self.assertEqual(kinds["table"], 3)
        self.assertEqual(kinds["figure"], 1)
        self.assertEqual(kinds["glossary"], 1)
        self.assertEqual(kinds["bibliography"], 1)
        self.assertGreaterEqual(kinds["section"], 5)
        e11 = c.execute("SELECT * FROM nodes WHERE part = 15 AND id = 'sect_E.1.1'").fetchone()
        self.assertEqual((e11["parent_id"], e11["chapter_id"], e11["depth"], e11["label"]), ("sect_E.1", "chapter_E", 2, "E.1.1"))
        tbl = c.execute("SELECT * FROM nodes WHERE part = 15 AND id = 'table_E.1-1'").fetchone()
        self.assertEqual((tbl["kind"], tbl["parent_id"], tbl["title"]), ("table", "sect_E.1", "Application Level Confidentiality Profile Attributes"))

    def test_docs_per_kind_and_edition(self):
        c = self.db()
        kinds = dict(c.execute("SELECT kind, count(*) FROM docs WHERE part = 15 GROUP BY kind").fetchall())
        self.assertEqual(kinds["table"], 3)
        self.assertEqual(kinds["row"], 6 + 3 + 3)
        self.assertGreaterEqual(kinds["section"], 8)
        parts = {r["part"]: r for r in c.execute("SELECT * FROM parts")}
        self.assertEqual(parts[15]["edition"], "2026d")
        self.assertEqual(parts[15]["schema_version"], ds.SCHEMA_VERSION)

    def test_dict_rows(self):
        c = self.db()
        rows = {r["tag"]: r for r in c.execute("SELECT * FROM dict WHERE part = 6")}
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows["(0010,0010)"]["keyword"], "PatientName")  # zero-width spaces stripped
        self.assertEqual(rows["(0008,0001)"]["retired"], 1)
        self.assertEqual(rows["(0008,0050)"]["retired"], 0)
        self.assertIn("(60xx,0010)", rows)
        self.assertEqual(rows["(0002,0000)"]["source_table"], "table_7-1")

    def test_manifest_fields(self):
        manifest = ds.load_manifest()
        e = manifest["parts"]["15"]
        self.assertEqual(e["edition"], "2026d")
        self.assertEqual(e["path"], "editions/2026d/part15.xml")
        self.assertEqual(e["url"], URL15)
        self.assertEqual(e["sha256"], hashlib.sha256(PART15).hexdigest())
        self.assertEqual(e["bytes"], len(PART15))
        self.assertTrue(e["etag"].startswith('"'))
        self.assertTrue((ds.home() / e["path"]).is_file())


class TestRender(CacheCase):
    def test_section_markdown(self):
        r = invoke("show", "15:E.1")
        self.assertEqual(r.exit_code, 0, r.output)
        out = r.output
        self.assertIn("# E.1 Application Level Confidentiality Profile", out)
        self.assertIn("**data confidentiality**", out)
        self.assertIn("PS3.6 sect_6 (6:sect_6)", out)  # cross-part placeholder, PS3.6 cached but id absent in fixture
        self.assertIn("1. Remove identifying Attributes.\n  - Replace with a dummy value where Type 1.\n2. Record the profile applied.", out)
        self.assertIn("- **D**: replace with a non-zero length dummy value", out)
        self.assertIn("```\n(0010,0010) PN [Anonymous^Patient]\n```", out)
        self.assertIn("[example.org](https://example.org/ihe)", out)
        self.assertIn("[Figure E.1-1: De-identification Flow — image not cached]", out)
        # small table inlined, big table becomes a pointer
        self.assertIn("| Code | Meaning |", out)
        self.assertIn("| U | replace with a consistent UID |", out)
        self.assertIn("(6 rows × 15 cols) → `table 15:table_E.1-1`", out)
        self.assertNotIn("| Accession Number |", out)
        self.assertIn("Subsections:\n- E.1.1 De-identifier  (15:sect_E.1.1)\n- E.1.2 Re-identifier  (15:sect_E.1.2)", out)
        self.assertTrue(
            out.rstrip().endswith("source: DICOM PS3.15 2026d — https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_E.html#sect_E.1")
        )

    def test_intra_part_refs_resolve(self):
        r = invoke("show", "15:E.1.1")
        self.assertIn("listed in Table E.1-1 (15:table_E.1-1)", r.output)
        self.assertIn("options in §E.1.2 Re-identifier (15:sect_E.1.2)", r.output)
        self.assertIn("Values that are *not* listed are kept.", r.output)

    def test_chapter_refs_note_and_depth(self):
        r = invoke("show", "15:1")
        self.assertIn("See §E.1 Application Level Confidentiality Profile (15:sect_E.1) and PS3.3.", r.output)
        self.assertIn("Subsections:\n- 1.1 Scope  (15:sect_1.1)", r.output)
        r = invoke("show", "15:1", "--depth", "1")
        self.assertIn("## 1.1 Scope", r.output)
        self.assertIn("- Secure transport connections\n- Attribute confidentiality", r.output)
        self.assertIn("> **Note:** Nothing here is normative in the fixture.", r.output)
        self.assertNotIn("Subsections:", r.output)

    def test_glossary_and_bibliography(self):
        r = invoke("show", "15:glossary", "--depth", "1")
        self.assertIn("**De-identification**: Removal of identifying information.", r.output)
        r = invoke("show", "15:bibliography")
        self.assertIn("[biblio_IHE_RAD_TF] IHE RAD TF. IHE Radiology Technical Framework. 2024", r.output)

    def test_truncation_and_json(self):
        r = invoke("show", "15:E.1", "--max-chars", "300")
        self.assertIn("[truncated at 300 chars; --max-chars 0 for all]", r.output)
        self.assertIn("source: DICOM PS3.15 2026d", r.output)
        r = invoke("show", "15:E.1.1", "--json")
        data = json.loads(r.output)
        self.assertEqual(data["ref"], "15:sect_E.1.1")
        self.assertEqual(
            data["source"],
            {"part": "PS3.15", "edition": "2026d", "url": "https://dicom.nema.org/medical/dicom/current/output/chtml/part15/chapter_E.html#sect_E.1.1"},
        )
        self.assertFalse(data["truncated"])
        self.assertEqual(data["children"], [])

    def test_show_table_node_describes_columns(self):
        r = invoke("show", "15:table_E.1-1")
        self.assertEqual(r.exit_code, 0)
        self.assertIn("(6 rows × 15 cols)", r.output)
        self.assertIn("basicprof (Basic Prof.)", r.output)
        self.assertIn("retdfromps36 (Retd. (from PS3.6))", r.output)

    def test_inline_block_overlap_and_mathml(self):
        # `term` is both inline and block; `math` nests; neither may recurse or count as unknown
        from lxml import etree

        idx = ds.PartIndex(3, "2026d")
        rd = ds.Renderer(idx)
        ns = 'xmlns="http://docbook.org/ns/docbook" xmlns:m="http://www.w3.org/1998/Math/MathML"'
        el = etree.fromstring(
            f"<para {ns}>Use <term>Type 1</term> here: <inlineequation><m:math><m:mrow><m:mi>x</m:mi><m:mo>=</m:mo><m:mn>2</m:mn></m:mrow></m:math></inlineequation>.</para>"
        )
        self.assertEqual(rd.block(el), "Use Type 1 here: x=2.")
        td = etree.fromstring(
            f"<td {ns}><para>a</para><itemizedlist><listitem><para>b</para></listitem><listitem><para>c</para></listitem></itemizedlist></td>"
        )
        self.assertEqual(ds.cell_text(rd, td), "a - b - c")
        self.assertEqual(idx.unknown, {})

    def test_unknown_element_passthrough_and_count(self):
        from lxml import etree

        idx = ds.PartIndex(15, "2026d")
        rd = ds.Renderer(idx)
        el = etree.fromstring('<para xmlns="http://docbook.org/ns/docbook">A <weird>strange</weird> element</para>')
        self.assertEqual(rd.block(el), "A strange element")
        self.assertEqual(idx.unknown, {"weird": 1})


class TestGrid(CacheCase):
    def test_spans_expand_to_dense_grid(self):
        c = self.db()
        cols = json.loads(c.execute("SELECT columns_json FROM tables WHERE part = 15 AND id = 'table_E.2-1'").fetchone()[0])
        self.assertEqual([x["name"] for x in cols], ["Group", "Action / Basic", "Action / Option"])
        self.assertEqual([x["key"] for x in cols], ["group", "actionbasic", "actionoption"])
        rows = [json.loads(r[0]) for r in c.execute("SELECT cells_json FROM rows WHERE part = 15 AND table_id = 'table_E.2-1' ORDER BY ord")]
        self.assertEqual(rows, [["Dates", "X", "K"], ["Dates", "Z", "C"], ["All UIDs", "All UIDs", "All UIDs"]])

    def test_empty_cells_and_width(self):
        c = self.db()
        rows = [json.loads(r[0]) for r in c.execute("SELECT cells_json FROM rows WHERE part = 15 AND table_id = 'table_E.1-1' ORDER BY ord")]
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(len(r) == 15 for r in rows))
        self.assertEqual(rows[0][:5], ["Accession Number", "(0008,0050)", "N", "Y", "Z"])
        self.assertEqual(rows[0][5:], [""] * 10)
        self.assertEqual(rows[1][12], "C")  # Clean Desc. Opt.

    def test_header_cells_are_plain_text(self):
        c = self.db()
        cols = json.loads(c.execute("SELECT columns_json FROM tables WHERE part = 15 AND id = 'table_E.1-1'").fetchone()[0])
        self.assertEqual(cols[0], {"name": "Attribute Name", "key": "attributename"})
        self.assertEqual(cols[2]["name"], "Retd. (from PS3.6)")
        self.assertEqual(cols[2]["key"], "retdfromps36")

    def test_column_matching(self):
        cols = [
            {"name": "Basic Prof.", "key": "basicprof"},
            {"name": "Rtn. UIDs Opt.", "key": "rtnuidsopt"},
            {"name": "Rtn. Dev. Id. Opt.", "key": "rtndevidopt"},
        ]
        self.assertEqual(ds.match_column(cols, "basicprof"), 0)
        self.assertEqual(ds.match_column(cols, "Basic Prof."), 0)
        self.assertEqual(ds.match_column(cols, "uids"), 1)
        r = invoke("table", "15:E.1-1", "--where", "rtn=K")
        self.assertEqual(r.exit_code, 2)
        self.assertIn("ambiguous", r.output)
        r = invoke("table", "15:E.1-1", "--where", "nope=K")
        self.assertEqual(r.exit_code, 2)
        self.assertIn("no column matches 'nope'", r.output)


class TestVerbs(CacheCase):
    def test_help_lists_every_verb(self):
        r = invoke("--help")
        for verb in ("status", "pull", "toc", "show", "table", "search", "tag"):
            self.assertIn(verb, r.output)

    def test_toc(self):
        r = invoke("toc", "15")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("PS3.15 2026d — Security and System Management Profiles", r.output)
        self.assertIn("E  Attribute Confidentiality Profiles (Normative)  (15:chapter_E)", r.output)
        self.assertIn("  E.1  Application Level Confidentiality Profile  (15:sect_E.1)", r.output)
        self.assertNotIn("sect_E.1.1", r.output)  # default depth 2
        r = invoke("toc", "15", "--under", "E.1", "--depth", "0")
        self.assertIn("E.1-1  Application Level Confidentiality Profile Attributes  (15:table_E.1-1)  [table 6×15]", r.output)
        self.assertIn("(15:figure_E.1-1)  [figure]", r.output)
        self.assertIn("E.1.1  De-identifier  (15:sect_E.1.1)", r.output)
        r = invoke("toc", "15", "--json")
        data = json.loads(r.output)
        self.assertEqual(data["edition"], "2026d")
        self.assertIn({"id": "sect_1.1", "ref": "15:sect_1.1", "kind": "section", "label": "1.1", "title": "Scope", "level": 2}, data["nodes"])

    def test_toc_missing_under_exits_1(self):
        r = invoke("toc", "15", "--under", "Q.9")
        self.assertEqual(r.exit_code, 1)
        self.assertIn("no node 'Q.9'", r.output)

    def test_table_where_columns_formats_limit(self):
        r = invoke("table", "15:E.1-1", "--where", "tag=(0010,0010)")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("| Patient's Name | (0010,0010) | N | Y | Z |", r.output)
        self.assertIn("1 of 1 matching rows (table has 6 rows × 15 cols)", r.output)
        self.assertTrue(r.output.rstrip().endswith("chapter_E.html#table_E.1-1"))

        r = invoke("table", "15:E.1-1", "--where", "basicprof~^X", "--columns", "attributename,tag,basic", "--format", "csv")
        self.assertEqual(r.output.splitlines()[0], "Attribute Name,Tag,Basic Prof.")
        self.assertIn('Institution Name,"(0008,0080)",X/Z/D', r.output)
        self.assertEqual(len(r.output.splitlines()), 4)

        r = invoke("table", "15:E.1-1", "--where", "basicprof~X", "--where", "rtninstidopt=k", "--json")
        data = json.loads(r.output)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["rows"][0]["attributename"], "Institution Name")
        self.assertEqual(data["rows"][0]["rtninstidopt"], "K")
        self.assertEqual(data["all_rows"], 6)
        self.assertEqual(data["source"]["edition"], "2026d")

        r = invoke("table", "15:E.1-1", "--limit", "2")
        self.assertIn("2 of 6 rows — --limit 0 for all", r.output)
        r = invoke("table", "6:6-1", "--where", "keyword=patientname", "--columns", "tag,vr")
        self.assertIn("| (0010,0010) | PN |", r.output)

    def test_table_errors(self):
        r = invoke("table", "15:E.1.1")
        self.assertEqual(r.exit_code, 1)
        self.assertIn("(section)", r.output)
        r = invoke("table", "15:E.1-1", "--where", "tag~[")
        self.assertEqual(r.exit_code, 2)
        self.assertIn("bad regex", r.output)
        r = invoke("table", "15:E.1-1", "--format", "xml")
        self.assertEqual(r.exit_code, 2)
        r = invoke("table", "15:E.1-1", "--where", "tag")
        self.assertEqual(r.exit_code, 2)

    def test_search(self):
        r = invoke("search", "accession")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("15:table_E.1-1#row1", r.output)
        self.assertIn("6:table_6-1#row2", r.output)
        self.assertIn("[Accession] Number", r.output)
        r = invoke("search", "dummy", "--part", "15", "--kind", "section")
        self.assertIn("15:sect_E.1 ", r.output)
        self.assertNotIn("#row", r.output)
        self.assertNotIn("\n  -", r.output)  # snippet squashed to one line
        r = invoke("search", "(0010,0010)", "--json")  # FTS syntax error → quoted retry
        data = json.loads(r.output)
        refs = {h["ref"] for h in data["hits"]}
        self.assertIn("15:table_E.1-1#row4", refs)
        self.assertIn("6:table_6-1#row3", refs)
        self.assertTrue(all(h["url"] for h in data["hits"]))
        r = invoke("search", "zzzzqqq")
        self.assertEqual(r.exit_code, 1)
        self.assertIn("no hits", r.output)
        r = invoke("search", "x", "--kind", "para")
        self.assertEqual(r.exit_code, 2)

    def test_tag(self):
        r = invoke("tag", "(0008,0050)")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("(0008,0050)  AccessionNumber  VR SH  VM 1  — Accession Number", r.output)
        self.assertIn("PS3.15 Table E.1-1: Retd. (from PS3.6): N · In Std. Comp. IOD (from PS3.3): Y · Basic Prof.: Z", r.output)
        self.assertIn("source: DICOM PS3.6 2026d — https://dicom.nema.org/medical/dicom/current/output/chtml/part06/chapter_6.html#table_6-1", r.output)
        self.assertIn("source: DICOM PS3.15 2026d", r.output)
        r = invoke("tag", "patientname", "--json")
        data = json.loads(r.output)
        self.assertEqual(data["tag"], "(0010,0010)")
        self.assertEqual(data["deidentification"]["actions"]["Basic Prof."], "Z")
        r = invoke("tag", "(0008,0001)")
        self.assertIn("RETIRED", r.output)
        self.assertIn("not listed", r.output)
        r = invoke("tag", "(6002,0010)")  # wildcard group
        self.assertIn("(60xx,0010)  OverlayRows", r.output)
        r = invoke("tag", "NoSuchKeyword")
        self.assertEqual(r.exit_code, 1)
        self.assertIn("search", r.output)

    def test_status(self):
        r = invoke("status")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("PS3.15 2026d", r.output)
        self.assertIn("edition: 2026d (all 2 cached parts)", r.output)
        r = invoke("status", "--max-age-days", "-1")
        self.assertEqual(r.exit_code, 1)
        self.assertIn("STALE", r.output)
        r = invoke("status", "--json")
        data = json.loads(r.output)
        self.assertEqual(data["editions"], ["2026d"])
        self.assertFalse(data["mixed"])
        self.assertEqual({p["part"] for p in data["parts"]}, {6, 15})

    def test_read_verbs_never_fetch(self):
        # FETCHER is NoNetwork here — any network call raises inside the command
        for args in (("toc", "15"), ("show", "15:E.1"), ("table", "15:E.1-1"), ("search", "dummy"), ("tag", "PatientName"), ("status",)):
            with self.subTest(args=args):
                r = invoke(*args)
                self.assertEqual(r.exit_code, 0, r.output)
                self.assertIsNone(r.exception if not isinstance(r.exception, SystemExit) else None)


class TestUncached(unittest.TestCase):
    """Fresh empty cache per test (the --pull test fills its own)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {ds.HOME_ENV: self.tmp.name})
        self.env.start()
        ds.FETCHER = NoNetwork()

    def tearDown(self):
        ds.FETCHER = ds.Fetcher()
        self.env.stop()
        self.tmp.cleanup()

    def test_status_empty_is_ok(self):
        r = invoke("status")
        self.assertEqual(r.exit_code, 0)
        self.assertIn("no parts cached", r.output)

    def test_read_verb_missing_part_exits_1_naming_pull(self):
        r = invoke("show", "15:E.1")
        self.assertEqual(r.exit_code, 1)
        self.assertIn("PS3.15 not cached — run: dicom_std.py pull 15", r.output)
        r = invoke("search", "anything")
        self.assertEqual(r.exit_code, 1)
        self.assertIn("nothing cached", r.output)
        r = invoke("pull")
        self.assertEqual(r.exit_code, 2)
        self.assertIn("nothing to pull", r.output)

    def test_pull_flag_fetches_then_answers(self):
        ds.FETCHER = FakeFetcher({URL15: PART15})
        r = invoke("table", "15:E.1-1", "--where", "tag=(0008,0050)", "--pull")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("| Accession Number |", r.output)
        self.assertTrue((ds.home() / "editions" / "2026d" / "part15.xml").is_file())


class TestPull(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {ds.HOME_ENV: self.tmp.name})
        self.env.start()

    def tearDown(self):
        ds.FETCHER = ds.Fetcher()
        self.env.stop()
        self.tmp.cleanup()

    def test_fresh_pull_and_up_to_date(self):
        ds.FETCHER = f = FakeFetcher({URL15: PART15})
        r = invoke("pull", "15")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("PS3.15 2026d", r.output)
        self.assertIn("indexed: 3 chapters", r.output)
        self.assertEqual([c[0] for c in f.calls], ["HEAD", "GET"])
        r = invoke("pull", "15")
        self.assertIn("up to date", r.output)
        self.assertEqual([c[0] for c in f.calls], ["HEAD", "GET", "HEAD"])
        r = invoke("pull", "15", "--force", "--json")
        self.assertEqual(json.loads(r.output)[0]["action"], "fetched")
        self.assertFalse(list(ds.incoming_dir().glob("*.meta.json")))

    def test_resume_appends_with_range(self):
        ds.FETCHER = f = FakeFetcher({URL15: PART15}, fail_after=1200)
        r = invoke("pull", "15")
        self.assertEqual(r.exit_code, 3, r.output)
        self.assertIn("rerun `pull 15` to resume", r.output)
        part_file = ds.incoming_dir() / "part15.xml.part"
        self.assertTrue(part_file.exists())
        self.assertEqual(part_file.stat().st_size, 1200)
        ds.FETCHER = f = FakeFetcher({URL15: PART15})
        r = invoke("pull", "15")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn(("GET", URL15, 1200), f.calls)
        self.assertFalse(part_file.exists())
        self.assertEqual(ds.load_manifest()["parts"]["15"]["sha256"], hashlib.sha256(PART15).hexdigest())

    def test_etag_change_restarts(self):
        ds.FETCHER = FakeFetcher({URL15: PART15}, fail_after=800)
        invoke("pull", "15")
        changed = PART15.replace(b"2026d", b"2027a")
        ds.FETCHER = f = FakeFetcher({URL15: changed})
        r = invoke("pull", "15")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn(("GET", URL15, None), f.calls)
        self.assertEqual(ds.load_manifest()["parts"]["15"]["edition"], "2027a")
        self.assertTrue((ds.home() / "editions" / "2027a" / "part15.xml").is_file())

    def test_check(self):
        ds.FETCHER = FakeFetcher({URL15: PART15, URL06: PART06})
        invoke("pull", "15")
        r = invoke("pull", "15", "6", "--check")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("PS3.15 up to date", r.output)
        self.assertIn("PS3.6  not cached", r.output)
        ds.FETCHER = FakeFetcher({URL15: PART15 + b"\n"})
        r = invoke("pull", "--check", "--json")
        self.assertEqual(r.exit_code, 1)
        self.assertEqual(json.loads(r.output)[0]["state"], "changed")
        self.assertFalse((ds.home() / "incoming" / "part15.xml.part").exists())

    def test_pinned_edition_404_and_superseded_kept(self):
        url_old = ds.part_url(15, "2025b")
        ds.FETCHER = FakeFetcher({URL15: PART15, url_old: PART15.replace(b"2026d", b"2025b")})
        r = invoke("pull", "15", "--edition", "2025b")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertEqual(ds.load_manifest()["parts"]["15"]["url"], url_old)
        r = invoke("show", "15:E.1.1")
        self.assertIn("source: DICOM PS3.15 2025b — https://dicom.nema.org/medical/dicom/2025b/output/chtml/part15/chapter_E.html#sect_E.1.1", r.output)
        r = invoke("pull", "15")  # move to current; the old edition's XML stays
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertTrue((ds.home() / "editions" / "2025b" / "part15.xml").is_file())
        self.assertTrue((ds.home() / "editions" / "2026d" / "part15.xml").is_file())
        r = invoke("pull", "15", "--edition", "2026d")
        self.assertEqual(r.exit_code, 1)
        self.assertIn("not published at its pinned path", r.output)
        r = invoke("pull", "15", "--edition", "nope")
        self.assertEqual(r.exit_code, 2)

    def test_network_error_exits_3(self):
        class Down:
            def head(self, url):
                raise ds.FetchError(None, "network error: unreachable")

            def get(self, url, start=None):
                raise AssertionError

        ds.FETCHER = Down()
        r = invoke("pull", "15")
        self.assertEqual(r.exit_code, 3)
        self.assertIn("unreachable", r.output)

    def test_mixed_editions_reported(self):
        ds.FETCHER = FakeFetcher({URL15: PART15, URL06: PART06.replace(b"2026d", b"2026c")})
        invoke("pull", "15", "6")
        r = invoke("status")
        self.assertEqual(r.exit_code, 1)
        self.assertIn("editions mixed: 2026c, 2026d", r.output)


class TestReindex(CacheCase):
    def test_schema_bump_rebuilds_from_cached_xml_offline(self):
        before = ds.db_path().stat().st_size
        self.assertGreater(before, 0)
        bumped = ds.SCHEMA_VERSION + 1
        with mock.patch.object(ds, "SCHEMA_VERSION", bumped):
            r = invoke("show", "15:E.1.1")  # FETCHER is NoNetwork
            self.assertEqual(r.exit_code, 0, r.output)
            self.assertIn("reindexing 2 part(s)", r.output)
            c = self.db()
            self.assertEqual({row[0] for row in c.execute("SELECT schema_version FROM parts")}, {bumped})
        r = invoke("show", "15:E.1.1")
        self.assertIn("reindexing 2 part(s)", r.output)  # back to the real version → rebuilt again
        r = invoke("show", "15:E.1.1")
        self.assertNotIn("reindexing", r.output)

    def test_missing_xml_names_force_pull(self):
        manifest = ds.load_manifest()
        path = ds.home() / manifest["parts"]["6"]["path"]
        backup = path.read_bytes()
        path.unlink()
        try:
            with mock.patch.object(ds, "SCHEMA_VERSION", ds.SCHEMA_VERSION + 5):
                r = invoke("toc", "6")
                self.assertEqual(r.exit_code, 1)
                self.assertIn("pull 6 --force", r.output)
        finally:
            path.write_bytes(backup)


@unittest.skipUnless(os.environ.get("DICOM_STD_LIVE") == "1", "set DICOM_STD_LIVE=1 for the real-network pull (~1–3 min)")
class TestLive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {ds.HOME_ENV: self.tmp.name})
        self.env.start()
        ds.FETCHER = ds.Fetcher()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_head_has_etag(self):
        h = ds.FETCHER.head(URL15)
        self.assertIn("etag", h)
        self.assertTrue(h["content-length"].isdigit())

    def test_pull_15_and_e11_shape(self):
        r = invoke("pull", "15")
        self.assertEqual(r.exit_code, 0, r.output)
        r = invoke("show", "15:table_E.1-1", "--json")
        data = json.loads(r.output)
        self.assertGreaterEqual(data["rows"], 600)
        self.assertEqual(len(data["columns"]), 15)
        r = invoke("table", "15:E.1-1", "--where", "tag=(0010,0010)", "--json")
        self.assertEqual(json.loads(r.output)["rows"][0]["basicprof"], "Z")


if __name__ == "__main__":
    unittest.main(verbosity=1)
