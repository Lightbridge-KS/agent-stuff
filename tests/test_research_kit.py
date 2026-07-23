#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for the research skill's research_kit.py machinery.

Each test builds a throwaway research-session fixture in a temp dir and drives
the CLI as `uv run` (so its pyyaml inline dep resolves), asserting on exit codes,
stdout, and the written sources.yaml.

    uv run tests/test_research_kit.py
"""

from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = (
    REPO_ROOT / "plugins" / "research" / "skills" / "research" / "scripts" / "research_kit.py"
)

PLAN_MD = textwrap.dedent(
    """\
    ---
    phase: executing
    shape: narrative
    topic: "uv vs pipx"
    created: 2026-07-05
    language: en
    output: markdown
    backends: [websearch]
    modules: [general-web]
    execution:
      wave_size: 4
      max_waves: 3
      searcher_model: sonnet
      verifier_model: sonnet
    progress:
      waves_done: 1
      sub_questions_done: ["01"]
    ---

    # Research plan: uv vs pipx

    ## Scope (from conversation)
    - light depth, markdown output

    ## Sub-questions
    1. How does uv manage CLI tools?
    2. How does pipx manage CLI tools?
    3. Migration story between the two?
    """
)


def fragment(entries: str) -> str:
    return textwrap.dedent(entries)


def make_session(
    base: Path,
    *,
    plan: str | None = PLAN_MD,
    fragments: dict[str, str] | None = None,
    notes: dict[str, str] | None = None,
    ledger: str | None = None,
    report: str | None = None,
    report_qmd: str | None = None,
    bib: str | None = None,
    verification: str | None = None,
) -> Path:
    session = base / "session"
    session.mkdir()
    if plan is not None:
        (session / "plan.md").write_text(plan)
    for name, content in (fragments or {}).items():
        (session / "sources").mkdir(exist_ok=True)
        (session / "sources" / name).write_text(content)
    for name, content in (notes or {}).items():
        (session / "notes").mkdir(exist_ok=True)
        (session / "notes" / name).write_text(content)
    if ledger is not None:
        (session / "sources.yaml").write_text(ledger)
    if report is not None:
        (session / "report.md").write_text(report)
    if report_qmd is not None:
        (session / "report.qmd").write_text(report_qmd)
    if bib is not None:
        (session / "references.bib").write_text(bib)
    if verification is not None:
        (session / "verification.md").write_text(verification)
    return session


def run_kit(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8"
    )


class MergeSourcesTest(unittest.TestCase):
    def test_merge_happy(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                fragments={
                    "01.yaml": fragment(
                        """\
                        - id: S01-1
                          url: https://docs.astral.sh/uv/
                          title: uv docs
                          type: docs
                          accessed: 2026-07-05
                        - id: S01-2
                          url: https://pipx.pypa.io/stable/
                          title: pipx docs
                          type: docs
                          accessed: 2026-07-05
                        """
                    ),
                    "02.yaml": fragment(
                        """\
                        - id: S02-1
                          url: https://github.com/astral-sh/uv
                          title: uv repo
                          type: repo
                          accessed: 2026-07-05
                        """
                    ),
                },
            )
            result = run_kit("merge-sources", str(session))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("merged 2 fragments -> 3 sources (0 duplicates)", result.stdout)
            ledger = (session / "sources.yaml").read_text()
            self.assertIn("id: S1", ledger)
            self.assertIn("id: S3", ledger)
            self.assertIn("fragment_ids:", ledger)
            self.assertIn("S02-1", ledger)

    def test_merge_dedup_url_normalization(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                fragments={
                    "01.yaml": fragment(
                        """\
                        - id: S01-1
                          url: https://Example.com/a/
                          title: Article A
                        """
                    ),
                    "02.yaml": fragment(
                        """\
                        - id: S02-1
                          url: http://example.com/a?utm_source=x
                          title: Article A again
                        """
                    ),
                },
            )
            result = run_kit("merge-sources", str(session))
            self.assertEqual(result.returncode, 0)
            self.assertIn("-> 1 sources (1 duplicates)", result.stdout)
            ledger = (session / "sources.yaml").read_text()
            self.assertIn("S01-1", ledger)
            self.assertIn("S02-1", ledger)
            self.assertNotIn("id: S2\n", ledger)

    def test_merge_dedup_doi_over_url(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                fragments={
                    "01.yaml": fragment(
                        """\
                        - id: S01-1
                          url: https://journal-a.org/paper
                          title: Paper
                          doi: 10.1000/XYZ123
                        """
                    ),
                    "02.yaml": fragment(
                        """\
                        - id: S02-1
                          url: https://mirror-b.org/other-path
                          title: Paper (mirror)
                          doi: 10.1000/xyz123
                        """
                    ),
                },
            )
            result = run_kit("merge-sources", str(session))
            self.assertEqual(result.returncode, 0)
            self.assertIn("-> 1 sources (1 duplicates)", result.stdout)

    def test_merge_id_stability_on_rerun(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                fragments={
                    "01.yaml": fragment(
                        """\
                        - id: S01-1
                          url: https://a.org/1
                          title: One
                        """
                    ),
                },
            )
            run_kit("merge-sources", str(session))
            first = (session / "sources.yaml").read_text()
            self.assertIn("id: S1", first)

            # No-change re-run must be byte-identical.
            run_kit("merge-sources", str(session))
            self.assertEqual(first, (session / "sources.yaml").read_text())

            # A later fragment appends; S1 keeps its id.
            (session / "sources" / "02.yaml").write_text(
                fragment(
                    """\
                    - id: S02-1
                      url: https://b.org/2
                      title: Two
                    """
                )
            )
            run_kit("merge-sources", str(session))
            merged = (session / "sources.yaml").read_text()
            self.assertLess(merged.index("id: S1"), merged.index("id: S2"))
            self.assertIn("https://a.org/1", merged)

    def test_merge_malformed_fragment_exits_1(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                fragments={
                    "01.yaml": fragment(
                        """\
                        - id: S01-1
                          title: no url here
                        """
                    ),
                },
                ledger="[]\n",
            )
            before = (session / "sources.yaml").read_text()
            result = run_kit("merge-sources", str(session))
            self.assertEqual(result.returncode, 1)
            self.assertIn("malformed: sources/01.yaml entry 1: missing url", result.stdout)
            self.assertEqual(before, (session / "sources.yaml").read_text(), "ledger mutated")

    def test_merge_empty_fragments_ok(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(Path(dir_))
            result = run_kit("merge-sources", str(session))
            self.assertEqual(result.returncode, 0)
            self.assertIn("merged 0 fragments -> 0 sources", result.stdout)


GOOD_LEDGER = textwrap.dedent(
    """\
    - id: S1
      url: https://a.org/1
      title: One
      fragment_ids: [S01-1]
    - id: S2
      url: https://b.org/2
      title: Two
      fragment_ids: [S01-2]
    """
)


class CheckCitationsTest(unittest.TestCase):
    def test_gate_pass(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                ledger=GOOD_LEDGER,
                report="Claim one [S1]. Claim two [S1, S2].\n",
            )
            result = run_kit("check-citations", str(session))
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("citations OK: 2 sources", result.stdout)

    def test_gate_unresolved_citation(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                ledger=GOOD_LEDGER,
                report="Claim [S1] and [S2] and bogus [S99].\n",
            )
            result = run_kit("check-citations", str(session))
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL resolve: [S99]", result.stdout)

    def test_gate_orphan_source(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                ledger=GOOD_LEDGER,
                report="Only cites [S1].\n",
            )
            result = run_kit("check-citations", str(session))
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL orphan: S2", result.stdout)

    def test_gate_uncertain_leak_in_report(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                ledger=GOOD_LEDGER,
                report="Cites [S1] [S2] but leaks [uncertain U01-1].\n",
            )
            result = run_kit("check-citations", str(session))
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL leak:", result.stdout)

    def test_gate_uncertain_without_verification_file(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                ledger=GOOD_LEDGER,
                report="Cites [S1] [S2].\n",
                notes={"01-topic.md": "Maybe true [uncertain U01-1].\n"},
            )
            result = run_kit("check-citations", str(session))
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL verify: verification.md missing", result.stdout)

    def test_gate_uncertain_covered_passes(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                ledger=GOOD_LEDGER,
                report="Cites [S1] [S2].\n",
                notes={"01-topic.md": "Maybe true [uncertain U01-1].\n"},
                verification="- [U01-1] confirmed — source states it directly\n",
            )
            result = run_kit("check-citations", str(session))
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertIn("1 uncertain claims all verified", result.stdout)

    def test_gate_uncertain_partially_covered(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                ledger=GOOD_LEDGER,
                report="Cites [S1] [S2].\n",
                notes={
                    "01-topic.md": "Maybe [uncertain U01-1]. Also [uncertain U01-2].\n"
                },
                verification="- [U01-1] unsupported — no source found\n",
            )
            result = run_kit("check-citations", str(session))
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL verify: U01-2", result.stdout)

    def test_gate_missing_report(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(Path(dir_), ledger=GOOD_LEDGER)
            result = run_kit("check-citations", str(session))
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL presence: no report.md or report.qmd", result.stdout)


GOOD_BIB = textwrap.dedent(
    """\
    @misc{S1,
      title = {One},
      url = {https://a.org/1}
    }

    @misc{S2,
      title = {Two},
      url = {https://b.org/2}
    }
    """
)


class CheckCitationsQmdTest(unittest.TestCase):
    def test_gate_qmd_pass(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                ledger=GOOD_LEDGER,
                report_qmd="Claim one [@S1]. Both agree [@S1; @S2].\n",
                bib=GOOD_BIB,
            )
            result = run_kit("check-citations", str(session))
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_gate_qmd_unresolved_citation(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                ledger=GOOD_LEDGER,
                report_qmd="Cites [@S1] [@S2] and bogus @S99.\n",
                bib=GOOD_BIB,
            )
            result = run_kit("check-citations", str(session))
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL resolve: [S99] cited in report.qmd", result.stdout)

    def test_gate_qmd_requires_bib(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                ledger=GOOD_LEDGER,
                report_qmd="Cites [@S1] and [@S2].\n",
            )
            result = run_kit("check-citations", str(session))
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL presence: references.bib missing", result.stdout)

    def test_gate_qmd_bib_out_of_sync(self):
        with tempfile.TemporaryDirectory() as dir_:
            stale_bib = "@misc{S1,\n  title = {One}\n}\n\n@misc{S9,\n  title = {Gone}\n}\n"
            session = make_session(
                Path(dir_),
                ledger=GOOD_LEDGER,
                report_qmd="Cites [@S1] and [@S2].\n",
                bib=stale_bib,
            )
            result = run_kit("check-citations", str(session))
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL bib: S2 in sources.yaml but not references.bib", result.stdout)
            self.assertIn("FAIL bib: S9 in references.bib but not sources.yaml", result.stdout)

    def test_gate_both_reports_orphan_is_union(self):
        # S2 cited only in the qmd — not an orphan, since orphan = uncited everywhere.
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                ledger=GOOD_LEDGER,
                report="Only cites [S1].\n",
                report_qmd="Cites [@S1] and [@S2].\n",
                bib=GOOD_BIB,
            )
            result = run_kit("check-citations", str(session))
            self.assertEqual(result.returncode, 0, result.stdout)


class ToBibtexTest(unittest.TestCase):
    def test_bibtex_happy(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                ledger=textwrap.dedent(
                    """\
                    - id: S1
                      url: https://a.org/paper
                      title: "Results & findings"
                      type: paper
                      accessed: 2026-07-05
                      doi: 10.1000/xyz
                      pmid: 12345
                      fragment_ids: [S01-1]
                    - id: S2
                      url: https://b.org/2
                      title: Two
                      type: docs
                      accessed: 2026-07-05
                      fragment_ids: [S01-2]
                    """
                ),
            )
            result = run_kit("to-bibtex", str(session))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("wrote references.bib (2 entries)", result.stdout)
            bib = (session / "references.bib").read_text()
            self.assertIn("@article{S1,", bib)
            self.assertIn("@misc{S2,", bib)
            self.assertIn("Results \\& findings", bib)
            self.assertIn("doi = {10.1000/xyz}", bib)
            self.assertIn("PMID: 12345", bib)
            self.assertIn("urldate = {2026-07-05}", bib)

    def test_bibtex_deterministic(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(Path(dir_), ledger=GOOD_LEDGER)
            run_kit("to-bibtex", str(session))
            first = (session / "references.bib").read_text()
            run_kit("to-bibtex", str(session))
            self.assertEqual(first, (session / "references.bib").read_text())

    def test_bibtex_missing_ledger(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(Path(dir_))
            result = run_kit("to-bibtex", str(session))
            self.assertEqual(result.returncode, 1)
            self.assertIn("no sources.yaml", result.stdout)


class StatusTest(unittest.TestCase):
    def test_status_digest(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(
                Path(dir_),
                notes={"01-uv.md": "done\n"},
                fragments={"01.yaml": "- {id: S01-1, url: https://a.org, title: A}\n"},
            )
            run_kit("merge-sources", str(session))
            result = run_kit("status", str(session))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("phase: executing", result.stdout)
            self.assertIn("sub-questions: 1/3 done (undone: 02 03)", result.stdout)
            self.assertIn("notes: 1", result.stdout)
            self.assertIn("ledger: 1 sources", result.stdout)
            self.assertIn("verification: absent", result.stdout)

    def test_status_missing_plan(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(Path(dir_), plan=None)
            result = run_kit("status", str(session))
            self.assertEqual(result.returncode, 1)
            self.assertIn("no plan.md", result.stdout)

    def test_status_malformed_frontmatter(self):
        with tempfile.TemporaryDirectory() as dir_:
            session = make_session(Path(dir_), plan="# no frontmatter here\n")
            result = run_kit("status", str(session))
            self.assertEqual(result.returncode, 1)
            self.assertIn("malformed plan.md frontmatter", result.stdout)


if __name__ == "__main__":
    unittest.main()
