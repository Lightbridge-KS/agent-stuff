"""Source contracts, fixed compilation, and immutable artifact storage."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from uuid import uuid4
from typing import NoReturn

from jsonschema import Draft7Validator, ValidationError, SchemaError

SKILL = Path(__file__).resolve().parent.parent
RUNTIME = SKILL / "runtime"
ID = re.compile(r"[a-f0-9]{32}\Z")
MAX_JSON = 1_048_576


class Failure(Exception):
    def __init__(self, code: int, stage: str, message: str, **details: object):
        super().__init__(message)
        self.code = code
        self.result = {"status": "error", "stage": stage, "message": message, **details}


def invalid(message: str, location: str = "source") -> NoReturn:
    raise Failure(2, "source", message, location=location)


def read_json(path: Path, limit: int = MAX_JSON) -> dict:
    if path.stat().st_size > limit:
        invalid(f"JSON exceeds {limit} bytes; reduce it.", path.name)

    def pairs(items: list) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                invalid(f"Duplicate JSON key: {key}", path.name)
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_text(),
            object_pairs_hook=pairs,
            parse_constant=lambda value: invalid(f"Non-finite JSON value: {value}"),
        )
        if not isinstance(value, dict):
            invalid("JSON document must be an object.", path.name)
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        invalid(f"Invalid JSON: {exc}", path.name)
    raise AssertionError("unreachable")


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )


def relative(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_./-]{1,200}", name):
        invalid(
            "Use a bounded relative path with plain filename characters.", str(name)
        )
    parts = Path(name).parts
    if name.startswith("/") or ".." in parts or any(p.startswith(".") for p in parts):
        invalid("Paths must remain inside source.", name)
    target = root / name
    if not target.resolve().is_relative_to(root.resolve()):
        invalid("Path escapes source.", name)
    return target


def bounded_schema(schema: object, depth: int = 0) -> None:
    """A deliberately small, portable JSON Schema subset, shared with precompiled Ajv."""
    if not isinstance(schema, dict) or depth > 12:
        invalid("Schema must be an object nested at most 12 levels.")
    allowed = {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "enum",
        "const",
        "description",
    }
    if set(schema) - allowed:
        invalid(
            f"Unsupported schema keywords: {sorted(set(schema) - allowed)}. No refs or executable patterns."
        )
    try:
        Draft7Validator.check_schema(schema)
    except SchemaError as exc:
        invalid(f"Invalid schema: {exc.message}")
    kind = schema.get("type")
    kinds = kind if isinstance(kind, list) else [kind]
    if not kinds or any(
        k not in {"object", "array", "string", "number", "integer", "boolean", "null"}
        for k in kinds
    ):
        invalid("Schema requires explicit JSON type(s).")
    if "object" in kinds:
        if schema.get("additionalProperties") is not False or not isinstance(
            schema.get("properties"), dict
        ):
            invalid("Every object needs properties and additionalProperties: false.")
        if len(schema["properties"]) > 100:
            invalid("Schema objects have at most 100 properties.")
        for child in schema["properties"].values():
            bounded_schema(child, depth + 1)
    if "array" in kinds:
        if (
            not isinstance(schema.get("maxItems"), int)
            or not 0 <= schema["maxItems"] <= 10000
        ):
            invalid("Arrays require maxItems <= 10000.")
        bounded_schema(schema.get("items"), depth + 1)
    if "string" in kinds and (
        not isinstance(schema.get("maxLength"), int)
        or not 0 <= schema["maxLength"] <= 100000
    ):
        invalid("Strings require maxLength <= 100000.")
    if (
        any(k in kinds for k in ["number", "integer"])
        and not {"minimum", "maximum"} <= schema.keys()
    ):
        invalid("Numbers require minimum and maximum.")


def validate_source(source: Path, destination: Path) -> dict:
    source = source.resolve()
    if not source.is_dir():
        invalid("Pass a source directory containing artifact.json.")
    descriptor = read_json(source / "artifact.json", 65536)
    try:
        Draft7Validator(read_json(RUNTIME / "descriptor.schema.json")).validate(
            descriptor
        )
    except ValidationError as exc:
        invalid(exc.message, "/".join(map(str, exc.path)) or "artifact.json")
    for name in [descriptor["entry"], *descriptor.get("assets", [])]:
        if not relative(source, name).is_file():
            invalid("Declared file is missing.", name)
    identifiers = [item["id"] for item in descriptor["interactions"]]
    if len(identifiers) != len(set(identifiers)):
        invalid("Interaction IDs must be unique.")
    for item in descriptor["interactions"]:
        bounded_schema(item["input_schema"])
    allowed_json = {"artifact.json", "checks.json", *descriptor.get("assets", [])}
    if descriptor.get("handoff"):
        name = descriptor["handoff"]["schema"]
        bounded_schema(read_json(relative(source, name), 65536))
        allowed_json.add(name)
    if (source / "checks.json").exists():
        checks = read_json(source / "checks.json")
        if (
            set(checks) != {"version", "scenarios"}
            or checks["version"] != 1
            or not isinstance(checks["scenarios"], list)
            or len(checks["scenarios"]) > 100
        ):
            invalid("checks.json requires version 1 and at most 100 scenarios.")
        for scenario in checks["scenarios"]:
            if (
                not isinstance(scenario, dict)
                or set(scenario) != {"interaction", "steps"}
                or scenario["interaction"] not in identifiers
                or not isinstance(scenario["steps"], list)
                or not 1 <= len(scenario["steps"]) <= 100
            ):
                invalid("Each scenario names a declared interaction and 1–100 steps.")
            assertion = False
            for step in scenario["steps"]:
                if (
                    not isinstance(step, dict)
                    or set(step) - {"action", "selector", "index", "value"}
                    or step.get("action")
                    not in {"click", "fill", "select", "press", "text", "value"}
                ):
                    invalid("Check actions: click, fill, select, press, text, value.")
                if (
                    not isinstance(step.get("selector"), str)
                    or not 1 <= len(step["selector"]) <= 500
                    or not isinstance(step.get("index", 0), int)
                    or not 0 <= step.get("index", 0) <= 1000
                ):
                    invalid("Checks need a bounded CSS selector and nonnegative index.")
                if step["action"] != "click" and (
                    not isinstance(step.get("value"), str) or len(step["value"]) > 4000
                ):
                    invalid("Check values must be strings up to 4000 characters.")
                assertion |= step["action"] in {"text", "value"}
            if not assertion:
                invalid("Every scenario must assert a visible text or value result.")
    text_bytes = asset_bytes = 0
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        name = path.relative_to(source).as_posix()
        if path.is_symlink():
            invalid("Symlinks are unsupported; copy explicit source/assets.", name)
        if path.is_dir():
            if any(
                part in {"node_modules", "_toolchain", ".git"} or part.startswith(".")
                for part in path.relative_to(source).parts
            ):
                invalid("Remove reserved directories from the source package.", name)
            continue
        relative(source, name)
        if path.suffix in {".ts", ".tsx", ".mdx", ".css", ".md", ".txt"}:
            text_bytes += path.stat().st_size
            if path.suffix == ".css":
                css = path.read_text()
                if "\\" in css or re.search(r"@import|url\s*\(", css, re.IGNORECASE):
                    invalid(
                        "CSS imports/URLs/escapes are unsupported. Import declared images from TSX; use local system fonts.",
                        name,
                    )
        elif name in allowed_json:
            asset_bytes += path.stat().st_size
        else:
            invalid(
                "Unsupported source file; declare data/assets or remove build config.",
                name,
            )
        if path.name in {"package.json", "tsconfig.json"} or path.name.startswith(
            ("vite.config.", "postcss.config.")
        ):
            invalid("Artifact build configuration is not supported.", name)
        if text_bytes > 10 * 1024**2 or asset_bytes > 50 * 1024**2:
            invalid("Source exceeds 10 MiB text / 50 MiB declared assets.")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return descriptor


def hashes(folder: Path, exclude: set[str] | None = None) -> dict[str, str]:
    result = {}
    for path in sorted(folder.rglob("*")):
        name = path.relative_to(folder).as_posix()
        if path.is_symlink():
            raise Failure(
                4, "integrity", "Symlink in artifact; rebuild from reviewed source."
            )
        if path.is_file() and name not in (exclude or set()):
            result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def run(args: list[str], cwd: Path, code: int = 3) -> str:
    environment = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(
            ("NODE_OPTIONS", "NODE_PATH", "VITE_", "npm_config_", "PNPM_")
        )
    }
    try:
        result = subprocess.run(
            args, cwd=cwd, env=environment, capture_output=True, text=True, timeout=180
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Failure(
            code,
            "dependency",
            f"Cannot run {args[0]}: {exc}. Check the pinned prerequisites.",
        ) from exc
    if result.returncode:
        raise Failure(
            code,
            "build" if code == 3 else "verification",
            (result.stderr or result.stdout)[-4000:],
        )
    return result.stdout


def rendered_files(folder: Path) -> dict[str, str]:
    if (
        sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())
        > 100 * 1024**2
    ):
        raise Failure(3, "build", "Rendered output exceeds 100 MiB.")
    return hashes(folder, {"artifact.json"})


def build(source: Path, work: Path, browser: bool = False) -> tuple[dict, dict]:
    descriptor = validate_source(source, work / "source")
    tools = work / "source/_toolchain"
    shutil.copytree(
        RUNTIME,
        tools,
        ignore=shutil.ignore_patterns(
            "node_modules", ".work", "check.json", "__pycache__"
        ),
    )
    toolchain_hash = digest(hashes(tools))
    authored = hashes(work / "source")
    source_hash = digest(
        {k: v for k, v in authored.items() if not k.startswith("_toolchain/")}
    )
    version = read_json(tools / "package.json")["version"]
    if (
        run(["node", "--version"], work).strip() != "v26.7.0"
        or run(["pnpm", "--version"], work).strip() != "10.18.2"
    ):
        raise Failure(3, "dependency", "Use tested Node 26.7.0 and pnpm 10.18.2.")
    # Dependencies and generated compiler state never enter the archived source.
    with tempfile.TemporaryDirectory(prefix="explorable-build-") as folder:
        compiler = Path(folder) / "toolchain"
        shutil.copytree(tools, compiler)
        run(["pnpm", "install", "--frozen-lockfile", "--ignore-scripts"], compiler)
        run(
            [
                "node",
                "build.mjs",
                str((work / "source").resolve()),
                str((work / "rendered").resolve()),
            ],
            compiler,
        )
        files = rendered_files(work / "rendered")
        evidence = {
            "schema_version": 1,
            "source_hash": source_hash,
            "toolchain_hash": toolchain_hash,
            "rendered_hash": digest(files),
            "static": "passed",
            "browser": {"status": "not_run"},
            "environment": {"node": "26.7.0", "pnpm": "10.18.2"},
        }
        write_json(
            work / "rendered/artifact.json",
            {
                "id": "preview",
                "source_format": Path(descriptor["entry"]).suffix[1:],
                "toolchain_version": version,
                "rendered_hash": evidence["rendered_hash"],
                "browser_status": "not_run",
            },
        )
        if browser:
            run(
                [
                    "node",
                    "browser.mjs",
                    str((work / "rendered").resolve()),
                    str((work / "source").resolve()),
                    str((work / "screenshots").resolve()),
                ],
                compiler,
                code=6,
            )
            evidence["browser"] = read_json(work / "screenshots/browser.json")
    write_json(work / "verification.json", evidence)
    return descriptor, evidence


def matched_evidence(supplied: dict, current: dict, descriptor: dict) -> dict:
    """Accept only the evidence record, never a CLI envelope carrying local paths."""
    if set(supplied) != set(current):
        raise Failure(
            6,
            "evidence",
            "Use the verification.json at evidence_path, not the CLI result envelope.",
        )
    if any(
        supplied.get(key) != current[key]
        for key in [
            "schema_version",
            "source_hash",
            "toolchain_hash",
            "rendered_hash",
            "environment",
        ]
    ):
        raise Failure(
            6,
            "evidence",
            "Evidence belongs to different source/toolchain/output; run check again.",
        )
    browser = supplied.get("browser", {})
    if not isinstance(browser, dict):
        raise Failure(6, "evidence", "Browser evidence must be an object.")
    if supplied.get("static") != "passed" or browser.get("status") not in {
        "passed",
        "not_run",
    }:
        raise Failure(
            6, "evidence", "Failed or malformed evidence cannot be published as passed."
        )
    if browser["status"] == "passed":
        checked = {
            item.get("id")
            for item in browser.get("interactions", [])
            if isinstance(item, dict) and item.get("status") == "passed"
        }
        if (
            not {item["id"] for item in descriptor["interactions"]} <= checked
            or browser.get("errors")
            or browser.get("unexpected_requests")
        ):
            raise Failure(
                6,
                "evidence",
                "Browser evidence is incomplete or failed; run check --browser again.",
            )
    return supplied


def store_root() -> Path:
    executable = shutil.which("lb")
    if not executable:
        raise Failure(
            4,
            "project",
            "Install the lb CLI; project identity is resolved with lb path --json.",
        )
    output = run([executable, "path", "--json"], Path.cwd(), code=4)
    return Path(json.loads(output)["config"]).parent / "explorable-documents"


def artifact(root: Path, identifier: str) -> tuple[Path, dict]:
    if not ID.fullmatch(identifier):
        raise Failure(
            2, "identity", "Use the 32-character artifact ID returned by present/list."
        )
    directory = root / "artifacts" / identifier
    if not directory.is_dir():
        raise Failure(4, "storage", "Artifact not found in this project.")
    manifest = read_json(directory / "manifest.json")
    if manifest.get("schema_version") != 1 or manifest.get("id") != identifier:
        raise Failure(
            4, "integrity", "Unsupported saved artifact; rebuild from reviewed source."
        )
    for name in ["source", "rendered"]:
        if hashes(directory / name) != manifest["files"][name]:
            raise Failure(
                4,
                "integrity",
                f"Saved {name} hashes differ; rebuild as a new revision.",
            )
    if (
        digest(read_json(directory / "verification.json"))
        != manifest["verification_hash"]
    ):
        raise Failure(4, "integrity", "Saved evidence changed; create a new revision.")
    return directory, manifest


def publish(
    work: Path, root: Path, descriptor: dict, evidence: dict, parent: str | None = None
) -> tuple[Path, dict]:
    if parent:
        artifact(root, parent)
    identifier = uuid4().hex
    manifest = {
        "schema_version": 1,
        "id": identifier,
        "title": descriptor["title"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "revision_of": parent,
        "source_format": Path(descriptor["entry"]).suffix[1:],
        "toolchain_version": read_json(work / "source/_toolchain/package.json")[
            "version"
        ],
        "source_hash": evidence["source_hash"],
        "toolchain_hash": evidence["toolchain_hash"],
        "rendered_hash": evidence["rendered_hash"],
        "browser_status": evidence["browser"]["status"],
        "verification_hash": digest(evidence),
        "provenance": descriptor.get("data_sources", []),
        "warnings": ["No hostile-code zero-egress guarantee."],
    }
    write_json(work / "verification.json", evidence)
    write_json(
        work / "rendered/artifact.json",
        {
            k: manifest[k]
            for k in [
                "id",
                "source_format",
                "toolchain_version",
                "rendered_hash",
                "browser_status",
            ]
        },
    )
    manifest["files"] = {name: hashes(work / name) for name in ["source", "rendered"]}
    write_json(work / "manifest.json", manifest)
    destination = root / "artifacts" / identifier
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".publish-", dir=destination.parent))
    try:
        for name in ["source", "rendered"]:
            shutil.copytree(work / name, stage / name)
        for name in ["manifest.json", "verification.json"]:
            shutil.copyfile(work / name, stage / name)
        stage.rename(destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return destination, manifest
