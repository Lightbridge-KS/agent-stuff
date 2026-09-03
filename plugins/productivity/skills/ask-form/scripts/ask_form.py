#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""ask-form: an agent-driven local form for richer human input.

The agent writes a JSON *spec* (title, intro, a list of question elements drawn from a fixed
catalog of ten types); this tool validates it, serves a glass-styled page on 127.0.0.1, opens
the browser, blocks until the user submits or cancels (no timeout unless --timeout), and prints the
answers as one JSON document on stdout. Every question carries an optional note and the form
ends with optional comments; both return under `meta`. Every submitted form is also saved as a
markdown record under `~/.lightbridge/projects/<project-key>/asks/` (`--no-save` to skip; the
project key comes from the shared lightbridge resolver; saving is best-effort and never changes
the exit code or stdout). The agent supplies the judgment (what to ask); this tool stays
deterministic (what is rendered, how answers come back).

    uv run ask_form.py [SPEC] [--no-open] [--timeout S] [--no-save]   # SPEC = path, '-' or stdin
    uv run ask_form.py --example                              # a spec exercising all 10 types
    uv run ask_form.py --schema                               # JSON Schema of a spec
    uv run ask_form.py --validate [SPEC]                      # check only, nothing binds

stdout carries exactly one JSON document per run; human notes (the URL first, flushed) go to
stderr. The token in the URL gates the page, assets and the answer routes; `/static/*` is open.
Closing the tab does not end the run: the user must press Cancel, or the agent stops the process.
If the browser cannot be launched the URL is printed and the server keeps waiting (the Codex path).

Exit codes: 0 submitted · 1 no answers (`status` = cancelled | timeout) · 2 invalid spec or
usage (checked before anything binds; errors name the JSON path) · 3 environment (could not
bind loopback).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

SPEC_VERSION = 1
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
MAX_BODY = 5 * 1024 * 1024
ID_RE = re.compile(r"^[a-z0-9_-]+$")

DISPLAY_TYPES = {"section", "context"}
OPTION_TYPES = {"single_select", "multi_select", "ranking"}
ANSWER_TYPES = OPTION_TYPES | {"scale", "short_text", "long_text", "number", "matrix", "review"}
ALL_TYPES = DISPLAY_TYPES | ANSWER_TYPES
DEFAULT_DECISIONS = ["approve", "revise", "reject"]


# ── validation ─────────────────────────────────────────────────────────────────


class Compiled:
    """What the server needs from a valid spec: who can answer, who must, which files may be served."""

    def __init__(self) -> None:
        self.answerable: list[str] = []
        self.required: list[str] = []
        self.assets: list[Path] = []
        self.elements: dict[str, dict[str, Any]] = {}


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_options(opts: Any, path: str, errors: list[dict[str, str]], key: str = "options") -> list[str]:
    """Validate an option/item/row/column list; return its values."""
    if not isinstance(opts, list) or not opts:
        errors.append({"path": f"{path}.{key}", "message": f"{key} must be a non-empty list"})
        return []
    values: list[str] = []
    for j, o in enumerate(opts):
        p = f"{path}.{key}[{j}]"
        if not isinstance(o, dict):
            errors.append({"path": p, "message": "must be an object with value and label"})
            continue
        vkey = "id" if key == "items" else "value"
        v, label = o.get(vkey), o.get("label")
        if key != "items" and "recommended" in o and not isinstance(o["recommended"], bool):
            errors.append({"path": f"{p}.recommended", "message": "recommended must be a boolean"})
        if not isinstance(v, str) or not v:
            errors.append({"path": f"{p}.{vkey}", "message": f"{vkey} must be a non-empty string"})
        elif v in values:
            errors.append({"path": f"{p}.{vkey}", "message": f"duplicate {vkey} '{v}'"})
        else:
            values.append(v)
        if not isinstance(label, str) or not label:
            errors.append({"path": f"{p}.label", "message": "label must be a non-empty string"})
        if "description" in o and not isinstance(o["description"], str):
            errors.append({"path": f"{p}.description", "message": "description must be a string"})
    return values


def _check_range(el: dict[str, Any], path: str, errors: list[dict[str, str]], required: bool) -> None:
    lo, hi, step = el.get("min"), el.get("max"), el.get("step")
    for k, v in (("min", lo), ("max", hi)):
        if v is None:
            if required:
                errors.append({"path": f"{path}.{k}", "message": f"{k} is required"})
        elif not _is_num(v):
            errors.append({"path": f"{path}.{k}", "message": f"{k} must be a number"})
    if _is_num(lo) and _is_num(hi) and lo > hi:
        errors.append({"path": f"{path}.min", "message": "min must not exceed max"})
    if step is not None and (not _is_num(step) or step <= 0):
        errors.append({"path": f"{path}.step", "message": "step must be a positive number"})


def _check_asset(src: Any, path: str, errors: list[dict[str, str]], compiled: Compiled) -> None:
    if not isinstance(src, str) or not src:
        errors.append({"path": path, "message": "src must be a non-empty string"})
        return
    if src.startswith(("http://", "https://")):
        return
    p = Path(src).expanduser()
    try:
        real = p.resolve(strict=True)
    except (OSError, RuntimeError):
        errors.append({"path": path, "message": f"src is not a readable file: {src}"})
        return
    if not real.is_file() or real.suffix.lower() not in IMAGE_EXTS:
        errors.append({"path": path, "message": f"src must be an image file ({', '.join(sorted(IMAGE_EXTS))}) or an http(s) URL"})
        return
    compiled.assets.append(real)


def _check_recommended_number(el: dict[str, Any], path: str, errors: list[dict[str, str]]) -> None:
    if "recommended" not in el:
        return
    v, lo, hi = el["recommended"], el.get("min"), el.get("max")
    if not _is_num(v) or (_is_num(lo) and v < lo) or (_is_num(hi) and v > hi):
        errors.append({"path": f"{path}.recommended", "message": "recommended must be a number within min..max"})
    else:
        el["_recommended"] = v


def diverged_ids(answers: dict[str, Any], compiled: Compiled) -> list[str]:
    """Answered questions where a recommendation existed and the user chose otherwise."""
    out: list[str] = []
    for eid, val in answers.items():
        el = compiled.elements.get(eid)
        if el is None or "_recommended" not in el:
            continue
        rec = el["_recommended"]
        t = el["type"]
        if t == "multi_select":
            same = isinstance(val, list) and set(val) == set(rec)
        elif t == "review":
            same = isinstance(val, dict) and all(val.get(i, {}).get("decision") == d for i, d in rec.items())
        else:
            same = val == rec
        if not same:
            out.append(eid)
    return out


def validate_spec(spec: Any) -> tuple[list[dict[str, str]], Compiled]:
    """Return (errors, compiled). Empty errors means the spec is servable."""
    errors: list[dict[str, str]] = []
    compiled = Compiled()
    if not isinstance(spec, dict):
        return [{"path": "$", "message": "spec must be a JSON object"}], compiled
    if spec.get("spec_version") != SPEC_VERSION:
        errors.append({"path": "$.spec_version", "message": f"spec_version must be {SPEC_VERSION}"})
    if not isinstance(spec.get("title"), str) or not spec["title"].strip():
        errors.append({"path": "$.title", "message": "title must be a non-empty string"})
    for k in ("intro", "submit_label"):
        if k in spec and not isinstance(spec[k], str):
            errors.append({"path": f"$.{k}", "message": f"{k} must be a string"})
    qs = spec.get("questions")
    if not isinstance(qs, list) or not qs:
        errors.append({"path": "$.questions", "message": "questions must be a non-empty list"})
        return errors, compiled

    seen: set[str] = set()
    for i, el in enumerate(qs):
        path = f"$.questions[{i}]"
        if not isinstance(el, dict):
            errors.append({"path": path, "message": "element must be an object"})
            continue
        eid, etype = el.get("id"), el.get("type")
        if not isinstance(eid, str) or not ID_RE.match(eid):
            errors.append({"path": f"{path}.id", "message": "id must match [a-z0-9_-]+"})
        elif eid in seen:
            errors.append({"path": f"{path}.id", "message": f"duplicate id '{eid}'"})
        else:
            seen.add(eid)
        if etype not in ALL_TYPES:
            errors.append({"path": f"{path}.type", "message": f"unknown type; one of {', '.join(sorted(ALL_TYPES))}"})
            continue
        if etype != "context" and (not isinstance(el.get("label"), str) or not el["label"].strip()):
            errors.append({"path": f"{path}.label", "message": "label must be a non-empty string"})
        if "help" in el and not isinstance(el["help"], str):
            errors.append({"path": f"{path}.help", "message": "help must be a string"})
        if "required" in el and not isinstance(el["required"], bool):
            errors.append({"path": f"{path}.required", "message": "required must be a boolean"})
        if "recommendation" in el and not (isinstance(el["recommendation"], str) and el["recommendation"].strip()):
            errors.append({"path": f"{path}.recommendation", "message": "recommendation must be a non-empty one-line string"})

        if etype == "context":
            fmt = el.get("format")
            if fmt not in ("markdown", "mermaid", "image"):
                errors.append({"path": f"{path}.format", "message": "format must be markdown, mermaid or image"})
            elif fmt == "image":
                _check_asset(el.get("src"), f"{path}.src", errors, compiled)
            elif not isinstance(el.get("content"), str) or not el["content"]:
                errors.append({"path": f"{path}.content", "message": "content must be a non-empty string"})
        elif etype in OPTION_TYPES:
            el["_values"] = _check_options(el.get("options"), path, errors)
            recs = [o["value"] for o in el.get("options", []) if isinstance(o, dict) and o.get("recommended") is True and isinstance(o.get("value"), str)]
            if etype == "single_select" and len(recs) > 1:
                errors.append({"path": f"{path}.options", "message": "single_select may mark at most one option recommended"})
            if etype == "ranking" and recs:
                errors.append({"path": f"{path}.options", "message": "ranking has no recommended option; the given order is the recommendation"})
            if recs:
                el["_recommended"] = recs if etype == "multi_select" else recs[0]
            if "allow_other" in el and not isinstance(el["allow_other"], bool):
                errors.append({"path": f"{path}.allow_other", "message": "allow_other must be a boolean"})
            if etype == "multi_select":
                _check_range(el, path, errors, required=False)
        elif etype == "scale":
            _check_range(el, path, errors, required=True)
            _check_recommended_number(el, path, errors)
            if "labels" in el and not (isinstance(el["labels"], dict) and all(isinstance(v, str) for v in el["labels"].values())):
                errors.append({"path": f"{path}.labels", "message": "labels must map scale values to strings"})
        elif etype == "number":
            _check_range(el, path, errors, required=False)
            _check_recommended_number(el, path, errors)
            if "unit" in el and not isinstance(el["unit"], str):
                errors.append({"path": f"{path}.unit", "message": "unit must be a string"})
        elif etype == "short_text":
            if "max_length" in el and not (isinstance(el["max_length"], int) and el["max_length"] > 0):
                errors.append({"path": f"{path}.max_length", "message": "max_length must be a positive integer"})
        elif etype == "matrix":
            el["_rows"] = _check_options(el.get("rows"), path, errors, key="rows")
            el["_cols"] = _check_options(el.get("columns"), path, errors, key="columns")
        elif etype == "review":
            el["_items"] = _check_options(el.get("items"), path, errors, key="items")
            decisions = el.get("decisions", DEFAULT_DECISIONS)
            if not (isinstance(decisions, list) and len(decisions) >= 2 and all(isinstance(d, str) and d for d in decisions)):
                errors.append({"path": f"{path}.decisions", "message": "decisions must be a list of at least two strings"})
            if "comment" in el and not isinstance(el["comment"], bool):
                errors.append({"path": f"{path}.comment", "message": "comment must be a boolean"})
            if isinstance(decisions, list):
                recmap = {}
                for j, it in enumerate(el.get("items", [])):
                    if isinstance(it, dict) and "recommended" in it:
                        if it["recommended"] not in decisions:
                            errors.append({"path": f"{path}.items[{j}].recommended", "message": f"recommended must be one of {', '.join(map(str, decisions))}"})
                        elif isinstance(it.get("id"), str):
                            recmap[it["id"]] = it["recommended"]
                if recmap:
                    el["_recommended"] = recmap

        if isinstance(eid, str) and eid in seen and etype in ANSWER_TYPES:
            compiled.answerable.append(eid)
            compiled.elements[eid] = el
            if el.get("required"):
                compiled.required.append(eid)
    return errors, compiled


def validate_answers(body: Any, compiled: Compiled) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    """Check a submit body. Return (errors, answers, extras) where extras = {other, notes, comments}."""
    empty = {"other": [], "notes": {}, "comments": ""}
    if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
        return ["body must be {answers: {...}, other?: [...], notes?: {...}, comments?: str}"], {}, empty
    answers: dict[str, Any] = body["answers"]
    other = body.get("other", [])
    errors: list[str] = []
    if not isinstance(other, list) or not all(isinstance(x, str) for x in other):
        errors.append("other must be a list of ids")
        other = []
    notes = body.get("notes", {})
    if not isinstance(notes, dict) or not all(isinstance(v, str) for v in notes.values()):
        errors.append("notes must map ids to strings")
        notes = {}
    for nid in notes:
        if nid not in compiled.elements:
            errors.append(f"note for unknown id '{nid}'")
    notes = {k: v.strip() for k, v in notes.items() if isinstance(v, str) and v.strip()}
    comments = body.get("comments", "")
    if not isinstance(comments, str):
        errors.append("comments must be a string")
        comments = ""
    extras = {"other": other, "notes": notes, "comments": comments.strip()}
    for eid in answers:
        if eid not in compiled.elements:
            errors.append(f"unknown id '{eid}'")
    for eid in compiled.required:
        if eid not in answers:
            errors.append(f"required '{eid}' is missing")
    for eid, val in answers.items():
        el = compiled.elements.get(eid)
        if el is None:
            continue
        t = el["type"]
        is_other = eid in other
        if is_other and not (t in ("single_select", "multi_select") and el.get("allow_other", True)):
            errors.append(f"'{eid}' does not allow other")
        if t == "single_select":
            if not isinstance(val, str) or (not is_other and val not in el["_values"]):
                errors.append(f"'{eid}' must be one of its option values")
        elif t == "multi_select":
            if not (isinstance(val, list) and all(isinstance(v, str) for v in val)):
                errors.append(f"'{eid}' must be a list of option values")
            else:
                known = [v for v in val if v in el["_values"]]
                if not is_other and len(known) != len(val):
                    errors.append(f"'{eid}' has values outside its options")
                lo, hi = el.get("min"), el.get("max")
                if _is_num(lo) and len(val) < lo or _is_num(hi) and len(val) > hi:
                    errors.append(f"'{eid}' must have between {lo} and {hi} selections")
        elif t == "ranking":
            if not (isinstance(val, list) and sorted(val) == sorted(el["_values"])):
                errors.append(f"'{eid}' must be a full ordering of its option values")
        elif t in ("scale", "number"):
            lo, hi = el.get("min"), el.get("max")
            if not _is_num(val) or (_is_num(lo) and val < lo) or (_is_num(hi) and val > hi):
                errors.append(f"'{eid}' must be a number within its range")
        elif t in ("short_text", "long_text"):
            if not isinstance(val, str):
                errors.append(f"'{eid}' must be a string")
            elif t == "short_text" and isinstance(el.get("max_length"), int) and len(val) > el["max_length"]:
                errors.append(f"'{eid}' exceeds max_length")
        elif t == "matrix":
            if not (isinstance(val, dict) and all(r in el["_rows"] and c in el["_cols"] for r, c in val.items())):
                errors.append(f"'{eid}' must map row values to column values")
        elif t == "review":
            decisions = el.get("decisions", DEFAULT_DECISIONS)
            ok = isinstance(val, dict) and all(
                i in el["_items"] and isinstance(d, dict) and d.get("decision") in decisions
                and isinstance(d.get("comment", ""), str)
                for i, d in val.items()
            )
            if not ok:
                errors.append(f"'{eid}' must map item ids to {{decision, comment}}")
    return errors, answers, extras


def strip_private(spec: dict[str, Any]) -> dict[str, Any]:
    """Drop the `_values`-style scratch keys the validator adds before inlining the spec."""
    out = json.loads(json.dumps(spec))
    for el in out.get("questions", []):
        for k in [k for k in el if k.startswith("_")]:
            del el[k]
    return out


# ── example and schema ─────────────────────────────────────────────────────────

EXAMPLE: dict[str, Any] = {
    "spec_version": 1,
    "title": "ask-form: every element type",
    "intro": "A **sample form** the agent can start from. Every type below is optional except the first. Each question takes a note (press `n`); the form ends with general comments.",
    "submit_label": "Send answers",
    "questions": [
        {"id": "s_choices", "type": "section", "label": "Choices"},
        {"id": "approach", "type": "single_select", "label": "Which approach should we take?", "required": True,
         "help": "One decision. Descriptions say what happens if chosen.",
         "recommendation": "CLI first: the spike already proved loopback works from the sandbox, and MCP can wrap it later.",
         "options": [
             {"value": "cli", "label": "CLI first", "description": "Zero daemon; ships this week.", "recommended": True},
             {"value": "mcp", "label": "MCP first", "description": "Works in every harness; two more days."},
         ]},
        {"id": "surfaces", "type": "multi_select", "label": "Which surfaces matter for v1?", "min": 1, "max": 3,
         "options": [{"value": "web", "label": "Web"}, {"value": "mobile", "label": "Mobile"},
                     {"value": "tv", "label": "TV"}, {"value": "watch", "label": "Watch"}]},
        {"id": "priority", "type": "ranking", "label": "Rank these by priority",
         "options": [{"value": "speed", "label": "Speed"}, {"value": "safety", "label": "Safety"},
                     {"value": "polish", "label": "Polish"}]},
        {"id": "s_measures", "type": "section", "label": "Measures"},
        {"id": "confidence", "type": "scale", "label": "How confident are you in this plan?", "min": 1, "max": 5,
         "labels": {"1": "not at all", "5": "very"}, "recommended": 4, "recommendation": "Two spikes passed; the unknowns left are UI taste, not feasibility."},
        {"id": "budget_days", "type": "number", "label": "Days you are willing to spend", "min": 0, "max": 30, "step": 0.5, "unit": "days"},
        {"id": "s_text", "type": "section", "label": "Words"},
        {"id": "codename", "type": "short_text", "label": "A codename for this effort", "max_length": 40, "placeholder": "e.g. glasshouse"},
        {"id": "concerns", "type": "long_text", "label": "Anything that worries you?", "placeholder": "Free text. Markdown is fine."},
        {"id": "s_review", "type": "section", "label": "Review"},
        {"id": "ctx_diagram", "type": "context", "format": "mermaid",
         "content": "flowchart LR\n  A[agent] -->|spec.json| B[ask_form.py]\n  B -->|serves| C[browser]\n  C -->|answers| B\n  B -->|stdout| A"},
        {"id": "fit", "type": "matrix", "label": "Rate each component on each axis",
         "rows": [{"value": "cli", "label": "CLI"}, {"value": "renderer", "label": "Renderer"}],
         "columns": [{"value": "good", "label": "Good"}, {"value": "ok", "label": "OK"}, {"value": "bad", "label": "Bad"}]},
        {"id": "decisions", "type": "review", "label": "Decide on each item",
         "items": [{"id": "name", "label": "Name: ask-form", "description": "Descriptive; the agent reaches for 'ask'.", "recommended": "approve"},
                   {"id": "home", "label": "Home: inside the skill", "description": "Travels with the skill into every registry.", "recommended": "approve"}]},
    ],
}

_OPTION_ITEMS = {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["value", "label"],
                 "properties": {"value": {"type": "string", "minLength": 1}, "label": {"type": "string", "minLength": 1},
                                "description": {"type": "string"},
                                "recommended": {"type": "boolean", "description": "badge this option; at most one per single_select; not for ranking"}}}}
_BASE_PROPS = {"id": {"type": "string", "pattern": ID_RE.pattern}, "type": {"type": "string"},
               "label": {"type": "string", "minLength": 1}, "help": {"type": "string"}, "required": {"type": "boolean"},
               "recommendation": {"type": "string", "description": "one line: what the agent recommends and why; shown under the help text"}}


def _el(type_name: str, props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "required": ["id", "type"] + (["label"] if type_name != "context" else []) + (required or []),
            "properties": {**_BASE_PROPS, "type": {"const": type_name}, **props}}


SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "ask-form spec v1",
    "type": "object",
    "required": ["spec_version", "title", "questions"],
    "properties": {
        "spec_version": {"const": SPEC_VERSION},
        "title": {"type": "string", "minLength": 1},
        "intro": {"type": "string", "description": "markdown"},
        "submit_label": {"type": "string"},
        "questions": {"type": "array", "minItems": 1, "items": {"oneOf": [
            _el("section", {}),
            _el("context", {"format": {"enum": ["markdown", "mermaid", "image"]}, "content": {"type": "string"},
                            "src": {"type": "string", "description": "local image path or http(s) URL"}}, ["format"]),
            _el("single_select", {"options": _OPTION_ITEMS, "allow_other": {"type": "boolean", "default": True}}, ["options"]),
            _el("multi_select", {"options": _OPTION_ITEMS, "allow_other": {"type": "boolean", "default": True},
                                 "min": {"type": "integer"}, "max": {"type": "integer"}}, ["options"]),
            _el("scale", {"min": {"type": "number"}, "max": {"type": "number"}, "step": {"type": "number"},
                          "labels": {"type": "object", "additionalProperties": {"type": "string"}},
                          "recommended": {"type": "number", "description": "marked on the slider; never preselected"}}, ["min", "max"]),
            _el("ranking", {"options": _OPTION_ITEMS}, ["options"]),
            _el("short_text", {"placeholder": {"type": "string"}, "max_length": {"type": "integer", "minimum": 1}}),
            _el("long_text", {"placeholder": {"type": "string"}}),
            _el("number", {"min": {"type": "number"}, "max": {"type": "number"}, "step": {"type": "number"}, "unit": {"type": "string"},
                           "recommended": {"type": "number"}}),
            _el("matrix", {"rows": _OPTION_ITEMS, "columns": _OPTION_ITEMS}, ["rows", "columns"]),
            _el("review", {"items": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["id", "label"],
                                     "properties": {"id": {"type": "string"}, "label": {"type": "string"}, "description": {"type": "string"},
                                                    "recommended": {"type": "string", "description": "one of decisions"}}}},
                           "decisions": {"type": "array", "minItems": 2, "items": {"type": "string"}, "default": DEFAULT_DECISIONS},
                           "comment": {"type": "boolean", "default": True}}, ["items"]),
        ]}},
    },
    "$comment": "Answers: single_select → string · multi_select → [string] · scale/number → number · ranking → [value] full order · "
                "short_text/long_text → string · matrix → {row: column} · review → {item: {decision, comment}}. "
                "Ids answered through 'other' are listed in meta.other; unanswered optional ids in meta.skipped; per-question notes in meta.notes {id: text}; form-level comments in meta.comments; meta.diverged lists answered ids where the user chose against a recommendation.",
}


# ── server ─────────────────────────────────────────────────────────────────────


class Run:
    """Terminal state shared between the handler threads and the main thread."""

    def __init__(self, spec: dict[str, Any], compiled: Compiled, token: str) -> None:
        self.spec, self.compiled, self.token = spec, compiled, token
        self.lock = threading.Lock()
        self.event = threading.Event()
        self.outcome: str | None = None
        self.answers: dict[str, Any] = {}
        self.extras: dict[str, Any] = {"other": [], "notes": {}, "comments": ""}
        self.started = time.monotonic()

    def finish(self, outcome: str, answers: dict[str, Any] | None = None, extras: dict[str, Any] | None = None) -> bool:
        """First writer wins. Returns False when a terminal state already exists."""
        with self.lock:
            if self.outcome is not None:
                return False
            self.outcome = outcome
            self.answers = answers or {}
            if extras:
                self.extras = extras
            return True


class Handler(BaseHTTPRequestHandler):
    server_version = "ask-form/1"
    run: Run  # set on the server instance

    def log_message(self, *_: Any) -> None:  # quiet: stderr is reserved for the URL and notes
        return

    # helpers
    def _send(self, status: HTTPStatus, body: bytes = b"", ctype: str = "text/plain; charset=utf-8", extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, status: HTTPStatus, obj: Any) -> None:
        self._send(status, json.dumps(obj).encode(), "application/json")

    def _authorized(self, query: str) -> bool:
        return parse_qs(query).get("t", [None])[0] == self.server.run.token  # type: ignore[attr-defined]

    # routes
    def do_GET(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        run: Run = self.server.run  # type: ignore[attr-defined]
        if url.path == "/":
            if not self._authorized(url.query):
                return self._send(HTTPStatus.FORBIDDEN, b"forbidden")
            html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
            inlined = json.dumps(strip_private(run.spec)).replace("</", "<\\/")
            html = html.replace("<!--SPEC-->", f'<script id="spec" type="application/json">{inlined}</script>')
            return self._send(HTTPStatus.OK, html.encode(), "text/html; charset=utf-8")
        if url.path.startswith("/static/"):
            rel = url.path[len("/static/"):]
            target = (STATIC_DIR / rel).resolve()
            if not target.is_file() or STATIC_DIR not in target.parents:
                return self._send(HTTPStatus.NOT_FOUND, b"not found")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return self._send(HTTPStatus.OK, target.read_bytes(), ctype)
        if url.path.startswith("/asset/"):
            if not self._authorized(url.query):
                return self._send(HTTPStatus.FORBIDDEN, b"forbidden")
            try:
                idx = int(url.path[len("/asset/"):])
                target = run.compiled.assets[idx]
            except (ValueError, IndexError):
                return self._send(HTTPStatus.NOT_FOUND, b"not found")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return self._send(HTTPStatus.OK, target.read_bytes(), ctype)
        return self._send(HTTPStatus.NOT_FOUND, b"not found")

    def do_POST(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        run: Run = self.server.run  # type: ignore[attr-defined]
        if url.path not in ("/submit", "/cancel"):
            return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        if not self._authorized(url.query):
            return self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
        if url.path == "/cancel":
            if not run.finish("cancelled"):
                return self._json(HTTPStatus.CONFLICT, {"error": "already finished"})
            self._json(HTTPStatus.OK, {"status": "cancelled"})
            run.event.set()
            return None
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Content-Type must be application/json"})
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": f"body exceeds {MAX_BODY} bytes"})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json(HTTPStatus.BAD_REQUEST, {"errors": ["body is not valid JSON"]})
        errors, answers, extras = validate_answers(body, run.compiled)
        if errors:
            return self._json(HTTPStatus.BAD_REQUEST, {"errors": errors})
        if not run.finish("submitted", answers, extras):
            return self._json(HTTPStatus.CONFLICT, {"error": "already finished"})
        self._json(HTTPStatus.OK, {"status": "submitted"})
        run.event.set()  # after the response is written; the main thread shuts the server down
        return None


def launch_browser(url: str) -> bool:
    """Open the URL in the default browser. macOS uses `open` directly: Python's webbrowser
    module goes through AppleScript there and mangles query strings (the spike proved `open`
    works from the sandbox). Elsewhere, webbrowser. Any failure → False; the caller prints the URL."""
    try:
        if sys.platform == "darwin":
            return subprocess.run(["open", url], capture_output=True, timeout=15).returncode == 0
        return bool(webbrowser.open(url))
    except Exception:  # noqa: BLE001 — every launcher failure has the same fallback
        return False


def serve(spec: dict[str, Any], compiled: Compiled, timeout: float | None, open_browser: bool) -> tuple[int, dict[str, Any]]:
    run = Run(spec, compiled, secrets.token_urlsafe(18))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    except OSError as e:
        return 3, {"status": "error", "stage": "bind", "message": str(e)}
    server.daemon_threads = True
    server.run = run  # type: ignore[attr-defined]
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={run.token}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(url, file=sys.stderr, flush=True)
    if open_browser:
        if not launch_browser(url):
            print("could not launch a browser; open the URL above by hand", file=sys.stderr, flush=True)
    else:
        print("open the URL above in a browser", file=sys.stderr, flush=True)

    run.event.wait(timeout)  # timeout=None waits until submit or cancel
    run.finish("timeout")
    time.sleep(0.3)  # let in-flight responses (the "Sent" page's fetch) drain before the socket closes
    server.shutdown()  # main thread only: shutdown() blocks until serve_forever returns
    server.server_close()

    if run.outcome == "submitted":
        skipped = [i for i in compiled.answerable if i not in run.answers]
        meta: dict[str, Any] = {"duration_s": round(time.monotonic() - run.started, 1), "skipped": skipped, "other": run.extras["other"]}
        if run.extras["notes"]:
            meta["notes"] = run.extras["notes"]
        if run.extras["comments"]:
            meta["comments"] = run.extras["comments"]
        diverged = diverged_ids(run.answers, compiled)
        if diverged:
            meta["diverged"] = diverged
        return 0, {"status": "submitted", "answers": run.answers, "meta": meta}
    return 1, {"status": run.outcome}


# ── persistence ────────────────────────────────────────────────────────────────
#
# Every submitted form becomes ~/.lightbridge/projects/<key>/asks/<YYYY-MM-DD_HHMM>_<slug>.md:
# a record of a human decision, same class as handoffs/, always-on (no config section). Root,
# key and state dir come from the one shared resolver (scripts/lightbridge/lb_resolve.py),
# path-loaded lazily so the stdout contract and the offline verbs never depend on it.

ASKS_SUBDIR = "asks"


def slugify(text: str, limit: int = 6) -> str:
    """Filesystem-safe slug from the title: first `limit` alphanumeric words (mirrors plan_store)."""
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    return "-".join(words[:limit]) or "ask"


def load_resolver() -> Any:
    """Path-load lb_resolve.py. parents[5] is the agent-stuff root: registry entries are symlinks,
    so resolve() lands inside the repo. A copied install has no root above it → FileNotFoundError."""
    path = Path(__file__).resolve().parents[5] / "scripts" / "lightbridge" / "lb_resolve.py"
    if not path.is_file():
        raise FileNotFoundError(f"lightbridge resolver not found at {path} (copied install?)")
    spec = importlib.util.spec_from_file_location("lightbridge", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def git_state(root: Path) -> str:
    """`<branch> @ <short sha>` (+ ` (dirty)`), or `none` when the folder is not a repo."""
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5)
    try:
        sha = run("rev-parse", "--short", "HEAD")
        if sha.returncode != 0:
            return "none"
        branch = run("branch", "--show-current").stdout.strip() or "HEAD"
        dirty = " (dirty)" if run("status", "--porcelain").stdout.strip() else ""
        return f"{branch} @ {sha.stdout.strip()}{dirty}"
    except (OSError, subprocess.SubprocessError):
        return "none"


def _labels(el: dict[str, Any], key: str = "options") -> dict[str, str]:
    return {o.get("value", o.get("id")): o.get("label", "") for o in el.get(key, []) if isinstance(o, dict)}


def _answer_md(el: dict[str, Any], val: Any, is_other: bool) -> str:
    """One question's answer as markdown, per type. Agent strings are plain text here."""
    t = el["type"]
    labels = _labels(el)
    if t == "single_select":
        return f"{val} *(other)*" if is_other else f"{labels.get(val, val)} `{val}`"
    if t == "multi_select":
        return "\n" + "\n".join(f"- {v} *(other)*" if v not in labels else f"- {labels[v]} `{v}`" for v in val)
    if t == "ranking":
        return "\n" + "\n".join(f"{i}. {labels.get(v, v)}" for i, v in enumerate(val, 1))
    if t == "scale":
        lbl = (el.get("labels") or {}).get(str(val))
        return f"{val} {lbl}" if lbl else str(val)
    if t == "number":
        return f"{val} {el['unit']}" if el.get("unit") else str(val)
    if t == "matrix":
        rows, cols = _labels(el, "rows"), _labels(el, "columns")
        return "\n" + "\n".join(f"- {rows.get(r, r)} → {cols.get(c, c)}" for r, c in val.items())
    if t == "review":
        items = _labels(el, "items")
        lines = []
        for i, d in val.items():
            comment = f" — {d['comment']}" if d.get("comment") else ""
            lines.append(f"- {items.get(i, i)}: **{d.get('decision')}**{comment}")
        return "\n" + "\n".join(lines)
    text = str(val).strip()
    return "\n" + "\n".join(f"> {line}" for line in text.splitlines()) if text else "_(empty)_"


def _recommended_md(el: dict[str, Any]) -> str | None:
    t = el["type"]
    if t in ("single_select", "multi_select"):
        recs = [o for o in el.get("options", []) if isinstance(o, dict) and o.get("recommended") is True]
        if not recs:
            return None
        return ", ".join(f"{o.get('label')} `{o.get('value')}`" for o in recs)
    if t in ("scale", "number") and "recommended" in el:
        return str(el["recommended"])
    if t == "review":
        recs = [(it.get("label"), it["recommended"]) for it in el.get("items", []) if isinstance(it, dict) and "recommended" in it]
        return ", ".join(f"{lab}: {d}" for lab, d in recs) if recs else None
    return None


def render_record(spec: dict[str, Any], result: dict[str, Any], ctx: dict[str, str]) -> str:
    """The markdown record: frontmatter, one block per answerable question, comments, raw JSON."""
    meta = result.get("meta", {})
    answers, notes = result.get("answers", {}), meta.get("notes", {})
    other, diverged = set(meta.get("other", [])), set(meta.get("diverged", []))
    out = ["---", f"title: {json.dumps(spec['title'], ensure_ascii=False)}", f"created: {ctx['created']}",
           f"project: {json.dumps(ctx['project'])}", f"git: {ctx['git']}", "status: submitted",
           f"duration_s: {meta.get('duration_s', 0)}", "---", "", f"# {spec['title']}", ""]
    if spec.get("intro"):
        out += [spec["intro"].strip(), ""]
    out += ["## Answers", ""]
    for el in spec["questions"]:
        t = el["type"]
        if t == "section":
            out += [f"## {el['label']}", ""]
            continue
        if t == "context":
            continue
        eid = el["id"]
        out.append(f"### {el['label']}  `{eid}`")
        out.append(f"**Answer:** {_answer_md(el, answers[eid], eid in other)}" if eid in answers else "**Answer:** _skipped_")
        rec = _recommended_md(el)
        if rec or el.get("recommendation"):
            why = f" — {el['recommendation']}" if el.get("recommendation") else ""
            out.append(f"**Recommended:** {rec or '—'}{why}")
        if eid in diverged:
            out.append("**Diverged** from the recommendation.")
        if eid in notes:
            out.append(f"**Note:** {notes[eid]}")
        out.append("")
    if meta.get("comments"):
        out += ["## Comments", "", meta["comments"], ""]
    raw = json.dumps({"spec": spec, "result": result}, ensure_ascii=False, indent=2)
    out += ["## Raw", "", "```json", raw, "```", ""]
    return "\n".join(out)


def save_record(spec: dict[str, Any], result: dict[str, Any], cwd: Path | None = None, now: datetime | None = None) -> Path:
    """Write the record under the project's asks/ dir; returns the path. Raises on any failure."""
    lb = load_resolver()
    root = lb.repo_root(cwd or Path.cwd())
    directory = lb.default_state_dir() / lb.project_key(root) / ASKS_SUBDIR
    directory.mkdir(parents=True, exist_ok=True)
    when = now or datetime.now()
    stamp = when.strftime("%Y-%m-%d_%H%M")
    slug = slugify(spec["title"])
    target = directory / f"{stamp}_{slug}.md"
    suffix = 2
    while target.exists():  # same minute, same title — don't clobber
        target = directory / f"{stamp}_{slug}-{suffix}.md"
        suffix += 1
    ctx = {"created": when.strftime("%Y-%m-%dT%H:%M"), "project": str(root), "git": git_state(root)}
    target.write_text(render_record(strip_private(spec), result, ctx), encoding="utf-8")
    return target


# ── CLI ────────────────────────────────────────────────────────────────────────


def load_spec(source: str | None) -> tuple[Any, list[dict[str, str]]]:
    try:
        if source in (None, "-"):
            if sys.stdin.isatty():
                return None, [{"path": "$", "message": "no SPEC given and stdin is a terminal; pass a path or pipe JSON"}]
            raw = sys.stdin.read()
        else:
            raw = Path(source).read_text(encoding="utf-8")
    except OSError as e:
        return None, [{"path": "$", "message": f"cannot read spec: {e}"}]
    try:
        return json.loads(raw), []
    except json.JSONDecodeError as e:
        return None, [{"path": "$", "message": f"spec is not valid JSON: {e.msg} (line {e.lineno})"}]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="ask_form.py", description="Serve a local form from a JSON spec; print the answers as JSON.")
    ap.add_argument("spec", nargs="?", help="spec path, '-' or omitted for stdin")
    ap.add_argument("--timeout", type=float, default=None, help="give up after S seconds (default: wait until submit or cancel)")
    ap.add_argument("--no-open", action="store_true", help="print the URL only; do not launch a browser")
    ap.add_argument("--no-save", action="store_true", help="do not save the record under ~/.lightbridge/projects/<key>/asks/")
    ap.add_argument("--example", action="store_true", help="print a spec exercising every element type")
    ap.add_argument("--schema", action="store_true", help="print the JSON Schema of a spec")
    ap.add_argument("--validate", action="store_true", help="validate the spec and exit; nothing binds")
    args = ap.parse_args(argv)

    if args.example:
        print(json.dumps(EXAMPLE, indent=2, ensure_ascii=False))
        return 0
    if args.schema:
        print(json.dumps(SCHEMA, indent=2))
        return 0

    spec, errors = load_spec(args.spec)
    if not errors:
        errors, compiled = validate_spec(spec)
    if errors:
        print(json.dumps({"status": "invalid", "errors": errors}, indent=2))
        return 2
    if args.validate:
        print(json.dumps({"status": "valid", "answerable": compiled.answerable, "required": compiled.required,
                          "assets": [str(p) for p in compiled.assets]}, indent=2))
        return 0
    if args.timeout is not None and args.timeout <= 0:
        print(json.dumps({"status": "invalid", "errors": [{"path": "--timeout", "message": "must be positive"}]}))
        return 2

    code, result = serve(spec, compiled, args.timeout, open_browser=not args.no_open)
    if code == 0 and not args.no_save:
        try:
            saved = save_record(spec, result)
            result["meta"]["saved"] = str(saved)
            print(f"saved {saved}", file=sys.stderr, flush=True)
        except Exception as e:  # noqa: BLE001 — persistence is best-effort; the answers are on stdout regardless
            print(f"not saved: {e}", file=sys.stderr, flush=True)
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
