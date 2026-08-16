#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Behavioral tests for the repo graph: the readers in `lb_resolve.py`, the document
model in `lb_graph.py`, and the `lb graph` verb family.

Each module is loaded the way its real consumer loads it (ADR 0001): the readers via
plain import of `lb_resolve` (the path-load protocol itself is exercised by
`test_lightbridge.py::ResolveModuleContractTest`, whose FROZEN_API includes the graph
trio), the CLI as a subprocess executing `lightbridge.py` directly. Every CLI test
isolates state through the `--graph FILE` seam — the graph's `--registry` equivalent.

    uv run tests/test_lb_graph.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LIGHTBRIDGE_DIR = REPO_ROOT / "scripts" / "lightbridge"
SCRIPT = LIGHTBRIDGE_DIR / "lightbridge.py"

sys.path.insert(0, str(LIGHTBRIDGE_DIR))

import lb_graph  # noqa: E402
import lb_resolve as lb  # noqa: E402


def script_argv(script: Path, *args: str) -> list[str]:
    """argv launching a PEP 723 script the way its real consumer does (see
    test_lightbridge.py for the Windows rationale)."""
    if os.name != "nt":
        return [str(script), *args]
    return ["uv", "run", str(script), *args]


# A small graph exercising every backlink mode and the per-edge override:
#   app -[live-test-service]-> pacs        (type full)
#   docs -[subject]-> app                  (type compact)
#   app -[oss-reference]-> clone           (type off)
#   fork -[upstream]-> app, edge backlink = "off"   (override beats type full)
GRAPH_BODY = """\
[types.live-test-service]
inverse = "consumer"
backlink = "full"

[types.subject]
inverse = "studied-by"
backlink = "compact"

[types.oss-reference]
inverse = "referenced-by"
backlink = "off"

[types.upstream]
inverse = "downstream"
backlink = "full"

[[edge]]
from = 'app'
to = 'pacs'
type = 'live-test-service'
from_note = 'test PACS for live gates'
to_note = 'the app this PACS exercises'

[[edge]]
from = 'docs'
to = 'app'
type = 'subject'

[[edge]]
from = 'app'
to = 'clone'
type = 'oss-reference'

[[edge]]
from = 'fork'
to = 'app'
type = 'upstream'
backlink = 'off'
"""


def write_graph(base: Path, body: str = GRAPH_BODY) -> Path:
    graph = base / "graph.toml"
    graph.write_text(body, encoding="utf-8")
    return graph


class LoadGraphTest(unittest.TestCase):
    """`load_graph`'s tri-state contract — the `load_registry` shape, applied to the graph."""

    def load(self, body: str):
        with tempfile.TemporaryDirectory() as d:
            return lb.load_graph(write_graph(Path(d), body))

    def test_absent_file_is_not_opted_in(self):
        graph, error = lb.load_graph(Path("/nonexistent/graph.toml"))
        self.assertIsNone(graph)
        self.assertIsNone(error)

    def test_bad_toml_is_an_error(self):
        graph, error = self.load("not = toml = at all")
        self.assertIsNone(graph)
        self.assertIn("unreadable", error)

    def test_malformed_types_table_is_an_error(self):
        graph, error = self.load('[types]\nupstream = "not a table"\n')
        self.assertIsNone(graph)
        self.assertIn("[types]", error)

    def test_edge_must_be_array_of_tables(self):
        graph, error = self.load('edge = "nope"\n')
        self.assertIsNone(graph)
        self.assertIn("array of tables", error)

    def test_edges_normalize_with_none_for_absent_optionals(self):
        graph, error = self.load(GRAPH_BODY)
        self.assertIsNone(error)
        self.assertEqual(len(graph["edges"]), 4)
        docs_edge = next(e for e in graph["edges"] if e["from"] == "docs")
        self.assertEqual(
            docs_edge,
            {
                "from": "docs",
                "to": "app",
                "type": "subject",
                "from_note": None,
                "to_note": None,
                "backlink": None,
            },
        )

    def test_edges_missing_identity_are_skipped_and_counted(self):
        """A thinned graph must be visible, never silent — callers surface `skipped`."""
        body = "[[edge]]\nfrom = 'a'\nto = 'b'\ntype = 'x'\n\n[[edge]]\nfrom = 'a'\nto = ''\n"
        graph, error = self.load(body)
        self.assertIsNone(error)
        self.assertEqual(len(graph["edges"]), 1)
        self.assertEqual(graph["skipped"], 1)

    def test_empty_file_is_usable_and_empty(self):
        graph, error = self.load("")
        self.assertIsNone(error)
        self.assertEqual((graph["types"], graph["edges"], graph["skipped"]), ({}, [], 0))


class ProjectNodeTest(unittest.TestCase):
    """The one projection rule: out / backlinks / mentions, modes and overrides."""

    def setUp(self):
        with tempfile.TemporaryDirectory() as d:
            self.graph, error = lb.load_graph(write_graph(Path(d)))
        self.assertIsNone(error)

    def test_outgoing_edges_carry_type_and_from_note(self):
        out = lb.project_node(self.graph, "app")["out"]
        self.assertEqual(
            [(e["other"], e["label"], e["note"]) for e in out],
            [("pacs", "live-test-service", "test PACS for live gates"),
             ("clone", "oss-reference", None)],
        )

    def test_full_backlink_uses_inverse_label_and_to_note(self):
        backlinks = lb.project_node(self.graph, "pacs")["backlinks"]
        self.assertEqual(
            [(e["other"], e["label"], e["note"]) for e in backlinks],
            [("app", "consumer", "the app this PACS exercises")],
        )

    def test_compact_backlink_lands_in_mentions(self):
        projection = lb.project_node(self.graph, "app")
        self.assertEqual(
            [(m["other"], m["label"]) for m in projection["mentions"]],
            [("docs", "studied-by")],
        )

    def test_off_type_and_per_edge_override_are_omitted(self):
        projection = lb.project_node(self.graph, "app")
        others = {e["other"] for e in projection["backlinks"]}
        self.assertNotIn("fork", others, "edge-level backlink='off' must beat the type's full")
        clone = lb.project_node(self.graph, "clone")
        self.assertEqual((clone["backlinks"], clone["mentions"]), ([], []))

    def test_per_edge_override_can_also_raise_visibility(self):
        for edge in self.graph["edges"]:
            if edge["from"] == "app" and edge["to"] == "clone":
                edge["backlink"] = "full"
        backlinks = lb.project_node(self.graph, "clone")["backlinks"]
        self.assertEqual([e["other"] for e in backlinks], ["app"])

    def test_undeclared_type_projects_visibly(self):
        """Rot surfaces: an edge with an unknown type still renders, marked undeclared."""
        self.graph["edges"].append(
            {"from": "x", "to": "app", "type": "mystery",
             "from_note": None, "to_note": None, "backlink": None}
        )
        backlinks = lb.project_node(self.graph, "app")["backlinks"]
        entry = next(e for e in backlinks if e["other"] == "x")
        self.assertEqual(entry["label"], "mystery")
        self.assertFalse(entry["declared"])

    def test_invalid_edge_mode_falls_back_to_the_types_mode(self):
        for edge in self.graph["edges"]:
            if edge["from"] == "docs":
                edge["backlink"] = "loud"  # not a mode — the type's compact must win
        projection = lb.project_node(self.graph, "app")
        self.assertIn("docs", [m["other"] for m in projection["mentions"]])


class GraphDocumentTest(unittest.TestCase):
    """`lb_graph`'s document model: seed, spans, rendering, surgical edits."""

    def test_seed_parses_and_names_match(self):
        seeded = tomllib.loads(lb_graph.SEED_TYPES_BLOCK)["types"]
        self.assertEqual(list(seeded), lb_graph.SEED_TYPE_NAMES)
        for name, spec in seeded.items():
            self.assertTrue(spec.get("inverse"), f"{name} lacks an inverse")
            self.assertIn(spec.get("backlink"), ("full", "compact", "off"), name)

    def test_edge_spans_and_fields(self):
        spans = lb_graph.edge_spans(GRAPH_BODY)
        self.assertEqual(len(spans), 4)
        fields = lb_graph.edge_fields(GRAPH_BODY, spans[0])
        self.assertEqual(
            fields,
            {"from": "app", "to": "pacs", "type": "live-test-service",
             "from_note": "test PACS for live gates", "to_note": "the app this PACS exercises"},
        )

    def test_find_edge_spans_filters_by_type(self):
        self.assertEqual(len(lb_graph.find_edge_spans(GRAPH_BODY, "app", "pacs")), 1)
        self.assertEqual(
            lb_graph.find_edge_spans(GRAPH_BODY, "app", "pacs", "oss-reference"), []
        )

    def test_append_edge_round_trips_through_tomllib(self):
        edge = {"from": "a", "to": "b", "type": "upstream",
                "from_note": "it's the \"origin\"", "backlink": "off"}
        text = lb_graph.append_edge(GRAPH_BODY, edge)
        parsed = tomllib.loads(text)["edge"][-1]
        self.assertEqual(parsed["from_note"], "it's the \"origin\"")
        self.assertEqual(parsed["backlink"], "off")
        self.assertNotIn("to_note", parsed)

    def test_set_edge_key_replaces_inserts_and_removes(self):
        span = lb_graph.find_edge_spans(GRAPH_BODY, "docs", "app")[0]
        text = lb_graph.set_edge_key(GRAPH_BODY, span, "from_note", "studies the app")
        self.assertEqual(
            tomllib.loads(text)["edge"][1]["from_note"], "studies the app"
        )
        span = lb_graph.find_edge_spans(text, "docs", "app")[0]
        text2 = lb_graph.set_edge_key(text, span, "from_note", None)
        self.assertNotIn("from_note", tomllib.loads(text2)["edge"][1])
        self.assertEqual(text2, GRAPH_BODY, "insert then remove must round-trip byte-identical")

    def test_remove_span_takes_the_separator_blank_line(self):
        span = lb_graph.find_edge_spans(GRAPH_BODY, "fork", "app")[0]
        text = lb_graph.remove_span(GRAPH_BODY, span)
        self.assertEqual(len(tomllib.loads(text)["edge"]), 3)
        self.assertFalse(text.endswith("\n\n"))

    def test_untargeted_lines_survive_byte_identical(self):
        span = lb_graph.find_edge_spans(GRAPH_BODY, "docs", "app")[0]
        edited = lb_graph.set_edge_key(GRAPH_BODY, span, "to_note", "noted")
        original_lines = GRAPH_BODY.splitlines(keepends=True)
        edited_lines = edited.splitlines(keepends=True)
        self.assertEqual([l for l in edited_lines if l != "to_note = 'noted'\n"], original_lines)

    def test_edge_sentence_states_both_directions(self):
        types = tomllib.loads(GRAPH_BODY)["types"]
        sentence = lb_graph.edge_sentence(
            {"from": "app", "to": "pacs", "type": "live-test-service"}, types
        )
        self.assertIn("pacs is app's live-test-service", sentence)
        self.assertIn("show app as (consumer)", sentence)
        off = lb_graph.edge_sentence(
            {"from": "app", "to": "clone", "type": "oss-reference"}, types
        )
        self.assertIn("will not show", off)


class GraphCliTest(unittest.TestCase):
    """The `lb graph` verbs as subprocesses, isolated via `--graph FILE`."""

    def run_graph(self, graph: Path, *args: str):
        return subprocess.run(
            script_argv(SCRIPT, "graph", *args, "--graph", str(graph)),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_init_seeds_the_vocabulary(self):
        with tempfile.TemporaryDirectory() as d:
            graph = Path(d) / "graph.toml"
            result = self.run_graph(graph, "init")
            self.assertEqual(result.returncode, 0, result.stderr)
            seeded = tomllib.loads(graph.read_text(encoding="utf-8"))["types"]
            self.assertEqual(list(seeded), lb_graph.SEED_TYPE_NAMES)

    def test_init_never_clobbers(self):
        with tempfile.TemporaryDirectory() as d:
            graph = write_graph(Path(d))
            before = graph.read_bytes()
            result = self.run_graph(graph, "init")
            self.assertEqual(result.returncode, 1)
            self.assertIn("never clobbers", result.stderr)
            self.assertEqual(graph.read_bytes(), before)

    def test_init_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            graph = Path(d) / "graph.toml"
            result = self.run_graph(graph, "init", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("[types.upstream]", result.stdout)
            self.assertFalse(graph.exists())

    def test_verbs_refuse_an_absent_graph_naming_init(self):
        with tempfile.TemporaryDirectory() as d:
            graph = Path(d) / "graph.toml"
            for args in (("types",), ("show",)):
                with self.subTest(verb=args[0]):
                    result = self.run_graph(graph, *args)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("graph init", result.stderr)

    def test_verbs_refuse_a_malformed_graph(self):
        with tempfile.TemporaryDirectory() as d:
            graph = write_graph(Path(d), "not = toml = at all")
            result = self.run_graph(graph, "show")
            self.assertEqual(result.returncode, 1)
            self.assertIn("unusable", result.stderr)

    def test_types_lists_every_declared_type(self):
        with tempfile.TemporaryDirectory() as d:
            graph = write_graph(Path(d))
            result = self.run_graph(graph, "types")
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in ("live-test-service", "subject", "oss-reference", "upstream"):
                self.assertIn(f"A -[{name}]-> B", result.stdout)

    def test_show_summary_counts(self):
        with tempfile.TemporaryDirectory() as d:
            graph = write_graph(Path(d))
            result = self.run_graph(graph, "show", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(
                set(data), {"graph", "types", "nodes", "edges", "by_type", "skipped"}
            )
            self.assertEqual(data["edges"], 4)
            self.assertEqual(sorted(data["nodes"]),
                             ["app", "clone", "docs", "fork", "pacs"])

    def test_show_node_renders_projection_tiers(self):
        with tempfile.TemporaryDirectory() as d:
            graph = write_graph(Path(d))
            result = self.run_graph(graph, "show", "app")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("(live-test-service)", result.stdout)
            self.assertIn("Also referenced by: docs (studied-by)", result.stdout)
            self.assertNotIn("fork", result.stdout, "backlink='off' override must hide it")

    def test_show_unknown_node_refuses_and_lists_nodes(self):
        with tempfile.TemporaryDirectory() as d:
            graph = write_graph(Path(d))
            result = self.run_graph(graph, "show", "nope")
            self.assertEqual(result.returncode, 1)
            self.assertIn("no edges", result.stderr)
            self.assertIn("app", result.stderr)

    def test_show_node_json_shape(self):
        with tempfile.TemporaryDirectory() as d:
            graph = write_graph(Path(d))
            result = self.run_graph(graph, "show", "pacs", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(set(data), {"graph", "node", "out", "backlinks", "mentions"})
            self.assertEqual(data["backlinks"][0]["label"], "consumer")
            self.assertIn("path", data["backlinks"][0])


def write_registry(base: Path, *names: str) -> Path:
    """A registry mapping every name to `base` (an existing dir) — endpoints resolve."""
    registry = base / "repos.toml"
    registry.write_text("[repos]\n" + "".join(f"{n} = '{base}'\n" for n in names))
    return registry


class GraphWriteCliTest(unittest.TestCase):
    """`lb graph link|unlink|set`: teaching refusals, idempotency, surgical writes."""

    def run_graph(self, graph: Path, registry: Path | None, *args: str):
        argv = ["graph", *args, "--graph", str(graph)]
        if registry is not None:
            argv += ["--registry", str(registry)]
        return subprocess.run(
            script_argv(SCRIPT, *argv),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def seeded(self, d: str) -> tuple[Path, Path]:
        base = Path(d)
        graph = base / "graph.toml"
        result = self.run_graph(graph, None, "init")
        self.assertEqual(result.returncode, 0, result.stderr)
        return graph, write_registry(base, "app", "svc", "other")

    def test_link_appends_a_parseable_block_and_echoes_the_direction(self):
        with tempfile.TemporaryDirectory() as d:
            graph, registry = self.seeded(d)
            before = graph.read_text(encoding="utf-8")
            result = self.run_graph(
                graph, registry, "link", "app", "svc", "--type", "tooling",
                "--from-note", "svc provisions keys",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("svc is app's tooling", result.stdout)
            self.assertIn("show app as (tool-user)", result.stdout)
            text = graph.read_text(encoding="utf-8")
            self.assertTrue(text.startswith(before), "existing lines must be byte-identical")
            (edge,) = tomllib.loads(text)["edge"]
            self.assertEqual(edge["from_note"], "svc provisions keys")
            self.assertNotIn("to_note", edge)

    def test_link_is_idempotent_on_the_identical_edge(self):
        with tempfile.TemporaryDirectory() as d:
            graph, registry = self.seeded(d)
            args = ("link", "app", "svc", "--type", "tooling")
            self.assertEqual(self.run_graph(graph, registry, *args).returncode, 0)
            before = graph.read_bytes()
            result = self.run_graph(graph, registry, *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("unchanged", result.stdout)
            self.assertEqual(graph.read_bytes(), before)

    def test_link_refuses_a_differing_duplicate_naming_set(self):
        with tempfile.TemporaryDirectory() as d:
            graph, registry = self.seeded(d)
            self.run_graph(graph, registry, "link", "app", "svc", "--type", "tooling")
            result = self.run_graph(
                graph, registry, "link", "app", "svc", "--type", "tooling",
                "--from-note", "different",
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("graph set", result.stderr)

    def test_link_refuses_the_reversed_edge(self):
        with tempfile.TemporaryDirectory() as d:
            graph, registry = self.seeded(d)
            self.run_graph(graph, registry, "link", "app", "svc", "--type", "upstream")
            result = self.run_graph(graph, registry, "link", "svc", "app", "--type", "upstream")
            self.assertEqual(result.returncode, 1)
            self.assertIn("REVERSED", result.stderr)
            self.assertIn("unlink app svc", result.stderr)

    def test_link_refuses_unregistered_names_and_undeclared_types(self):
        with tempfile.TemporaryDirectory() as d:
            graph, registry = self.seeded(d)
            ghost = self.run_graph(graph, registry, "link", "app", "ghost", "--type", "tooling")
            self.assertEqual(ghost.returncode, 1)
            self.assertIn("repos add ghost", ghost.stderr)
            typed = self.run_graph(graph, registry, "link", "app", "svc", "--type", "nope")
            self.assertEqual(typed.returncode, 1)
            self.assertIn("tooling", typed.stderr)  # the declared set is listed

    def test_parallel_edge_of_another_type_is_allowed_with_a_note(self):
        with tempfile.TemporaryDirectory() as d:
            graph, registry = self.seeded(d)
            self.run_graph(graph, registry, "link", "app", "svc", "--type", "contracts")
            result = self.run_graph(
                graph, registry, "link", "app", "svc", "--type", "live-test-service"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("parallel", result.stderr)
            self.assertEqual(len(tomllib.loads(graph.read_text())["edge"]), 2)

    def test_unlink_removes_only_its_block(self):
        with tempfile.TemporaryDirectory() as d:
            graph, registry = self.seeded(d)
            self.run_graph(graph, registry, "link", "app", "svc", "--type", "tooling")
            after_one = graph.read_text(encoding="utf-8")
            self.run_graph(graph, registry, "link", "app", "other", "--type", "upstream")
            result = self.run_graph(graph, None, "unlink", "app", "other")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(graph.read_text(encoding="utf-8"), after_one)

    def test_unlink_absent_edge_is_a_noop_that_flags_the_reverse(self):
        with tempfile.TemporaryDirectory() as d:
            graph, registry = self.seeded(d)
            self.run_graph(graph, registry, "link", "app", "svc", "--type", "tooling")
            before = graph.read_bytes()
            result = self.run_graph(graph, None, "unlink", "svc", "app")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("unchanged", result.stdout)
            self.assertIn("reverse direction exists", result.stderr)
            self.assertEqual(graph.read_bytes(), before)

    def test_unlink_parallel_edges_needs_type(self):
        with tempfile.TemporaryDirectory() as d:
            graph, registry = self.seeded(d)
            self.run_graph(graph, registry, "link", "app", "svc", "--type", "contracts")
            self.run_graph(graph, registry, "link", "app", "svc", "--type", "live-test-service")
            result = self.run_graph(graph, None, "unlink", "app", "svc")
            self.assertEqual(result.returncode, 1)
            self.assertIn("--type", result.stderr)
            typed = self.run_graph(graph, None, "unlink", "app", "svc", "--type", "contracts")
            self.assertEqual(typed.returncode, 0, typed.stderr)
            (edge,) = tomllib.loads(graph.read_text())["edge"]
            self.assertEqual(edge["type"], "live-test-service")

    def test_set_replaces_clears_and_overrides(self):
        with tempfile.TemporaryDirectory() as d:
            graph, registry = self.seeded(d)
            self.run_graph(
                graph, registry, "link", "app", "svc", "--type", "tooling",
                "--from-note", "old",
            )
            self.run_graph(graph, None, "set", "app", "svc", "--from-note", "new",
                           "--backlink", "off")
            (edge,) = tomllib.loads(graph.read_text())["edge"]
            self.assertEqual((edge["from_note"], edge["backlink"]), ("new", "off"))
            self.run_graph(graph, None, "set", "app", "svc", "--from-note", "",
                           "--backlink", "default")
            (edge,) = tomllib.loads(graph.read_text())["edge"]
            self.assertNotIn("from_note", edge)
            self.assertNotIn("backlink", edge)

    def test_set_refusals(self):
        with tempfile.TemporaryDirectory() as d:
            graph, registry = self.seeded(d)
            nothing = self.run_graph(graph, None, "set", "app", "svc")
            self.assertEqual(nothing.returncode, 2)
            absent = self.run_graph(graph, None, "set", "app", "svc", "--from-note", "x")
            self.assertEqual(absent.returncode, 1)
            self.assertIn("graph link", absent.stderr)

    def test_write_verbs_json_share_one_shape(self):
        with tempfile.TemporaryDirectory() as d:
            graph, registry = self.seeded(d)
            linked = self.run_graph(
                graph, registry, "link", "app", "svc", "--type", "tooling", "--json"
            )
            data = json.loads(linked.stdout)
            self.assertEqual(set(data), {"graph", "action", "edge"})
            self.assertEqual(data["action"], "linked")
            updated = self.run_graph(
                graph, None, "set", "app", "svc", "--to-note", "x", "--json"
            )
            self.assertEqual(json.loads(updated.stdout)["action"], "updated")
            unlinked = self.run_graph(graph, None, "unlink", "app", "svc", "--json")
            self.assertEqual(json.loads(unlinked.stdout)["action"], "unlinked")


if __name__ == "__main__":
    unittest.main(verbosity=2)
