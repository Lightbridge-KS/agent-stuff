#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = [
#   "presidio-analyzer[langextract]>=2.2.364,<3",
#   "presidio-anonymizer>=2.2.364,<3",
#   "presidio-image-redactor>=0.0.60",
#   "pandas>=2.0",
#   "en_core_web_lg @ https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl",
#   "typer>=0.12",
#   "pyyaml>=6",
# ]
# ///
"""Deterministic PHI/PII de-identification CLI over Microsoft Presidio — the shell an agent drives.

    entities   list the entity types the analyzer can detect
    scan       find PHI/PII in a file; findings as a table or --json; exit 1 when found
    anonymize  apply a policy (replace/redact/mask/hash/encrypt/keep/pseudonym/date_shift)
    verify     re-scan an anonymized file; exit 1 on leaks the policy did not intend to keep
    restore    reverse pseudonym/date_shift/encrypt using the sidecar written by anonymize
    doctor     check the spaCy model, tesseract, and Ollama

Input routing by extension: .txt/.md → text · .json → structured (keys) · .csv → structured (columns) · .png/.jpg/.tif/.bmp → image (OCR) · .dcm or a directory → DICOM pixels. PDF/DOCX are refused: parse to Markdown first (parse-to-md, local only).

Everything runs on this machine. No cloud recognizer is ever enabled; Ollama `*:cloud` tags are refused. Output bytes go only to -o; the sidecar is re-identification key material — keep it out of git.

Exit codes: 0 ok / clean · 1 findings or leaks (scan, verify) · 2 fix the request (params or policy, checked before any engine loads) · 3 environment (model, tesseract, Ollama, DEID_KEY — the message names the fix).
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import shutil
import tempfile
import warnings
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Iterable, Optional

import typer
import yaml
from presidio_anonymizer.operators import Operator, OperatorType

app = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
    help=__doc__,
)

EXIT_FINDINGS = 1  # scan found entities at/above threshold · verify found leaks
EXIT_PARAMS = 2  # request or policy invalid — fix and rerun
EXIT_ENV = 3  # model / tesseract / Ollama / DEID_KEY missing

SKILL_DIR = Path(__file__).resolve().parent.parent
PRESETS_DIR = SKILL_DIR / "references" / "policies"
SIDECAR_VERSION = 1

TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".log"}
JSON_EXT = {".json"}
CSV_EXT = {".csv", ".tsv"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
DICOM_EXT = {".dcm", ".dicom"}
REFUSED_EXT = {".pdf", ".docx", ".pptx", ".xlsx", ".doc"}
STRUCTURED = {"csv", "json"}

BUILTIN_OPS = {"replace", "redact", "mask", "hash", "encrypt", "keep"}
CUSTOM_OPS = {"pseudonym", "date_shift"}
REVERSIBLE_OPS = {"pseudonym", "date_shift", "encrypt"}
SIDECAR_OPS = {"pseudonym", "encrypt"}  # restore is impossible without the sidecar
RESIDUAL_OPS = {"keep", "date_shift"}  # verify expects these entity types to remain detectable
DEFAULT_LLM_ENTITIES = ["PERSON", "LOCATION", "ORGANIZATION", "PHONE_NUMBER", "EMAIL_ADDRESS", "DATE_TIME", "ID"]
DEFAULT_LLM_MODEL = "ollama:gemma4:e4b"
OLLAMA_URL = "http://localhost:11434"

# A column/key is treated as *bare entities* (whole-cell operator, catches NER misses) when this
# share of its non-empty cells has a finding and that finding covers this share of the cell.
COLUMN_HIT_RATIO = 0.6
COLUMN_COVERAGE = 0.8

# Entity types that are PHI under HIPAA Safe Harbor or its direct analogues (see references/entities.md)
PHI_ENTITIES = {
    "PERSON", "LOCATION", "DATE_TIME", "PHONE_NUMBER", "EMAIL_ADDRESS", "URL", "IP_ADDRESS",
    "MEDICAL_LICENSE", "US_SSN", "US_MBI", "US_NPI", "US_HEALTH_INSURANCE_MEMBER_ID",
    "US_CLAIM_NUMBER", "US_PRESCRIPTION_NUMBER", "US_DRIVER_LICENSE", "US_PASSPORT",
    "US_BANK_NUMBER", "CREDIT_CARD", "IBAN_CODE", "UK_NHS", "TH_TNIN", "ID", "AU_MEDICARE",
    "MAC_ADDRESS", "UUID", "GENERIC_PII_ENTITY",
}

DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y",
    "%d %B %Y", "%B %d, %Y", "%d %b %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y",
    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M",
    "%d/%m/%y", "%m/%d/%y",
]

log = logging.getLogger("deid")


# ---------------------------------------------------------------------------
# Errors and output helpers
# ---------------------------------------------------------------------------


class PolicyError(ValueError):
    """The policy or request is malformed — exit 2 territory."""


def fail(code: int, message: str) -> None:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code)


def emit(obj: Any) -> None:
    typer.echo(json.dumps(obj, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass
class OpSpec:
    op: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class PatternSpec:
    name: str
    entity: str
    regex: str
    score: float = 0.6
    context: list[str] = field(default_factory=list)


@dataclass
class Policy:
    """A validated de-identification policy: what to look for, what to do with each entity type."""

    name: str = "default"
    language: str = "en"
    threshold: float = 0.5
    entities: list[str] = field(default_factory=list)
    allow: list[str] = field(default_factory=list)
    patterns: list[PatternSpec] = field(default_factory=list)
    columns: dict[str, str] = field(default_factory=dict)  # column / key name → entity type (forced)
    operators: dict[str, OpSpec] = field(default_factory=lambda: {"DEFAULT": OpSpec("replace")})
    llm: Optional[str] = None
    llm_entities: list[str] = field(default_factory=lambda: list(DEFAULT_LLM_ENTITIES))
    llm_generic: bool = False

    @classmethod
    def load(cls, ref: Optional[str]) -> "Policy":
        """Load a preset name (references/policies/<name>.yaml) or a YAML path; None → defaults."""
        if ref is None:
            return cls()
        path = Path(ref)
        if not path.suffix and not path.exists():
            path = PRESETS_DIR / f"{ref}.yaml"
        if not path.exists():
            presets = ", ".join(sorted(p.stem for p in PRESETS_DIR.glob("*.yaml"))) or "none found"
            raise PolicyError(f"policy '{ref}' not found — presets: {presets}; or pass a YAML path")
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise PolicyError(f"{path}: not valid YAML — {exc}") from exc
        return cls.from_dict(raw, name=path.stem)

    @classmethod
    def from_dict(cls, raw: dict[str, Any], name: str = "inline") -> "Policy":
        if not isinstance(raw, dict):
            raise PolicyError("policy must be a YAML mapping")
        unknown = set(raw) - {"language", "threshold", "entities", "allow", "patterns", "columns", "operators", "llm"}
        if unknown:
            raise PolicyError(f"unknown policy keys: {', '.join(sorted(unknown))}")
        pol = cls(name=name)
        pol.language = str(raw.get("language", pol.language))
        pol.threshold = _validate_threshold(raw.get("threshold", pol.threshold))
        pol.entities = _validate_entity_list(raw.get("entities") or [], "entities")
        pol.allow = [str(x) for x in (raw.get("allow") or [])]
        pol.patterns = [_validate_pattern(p) for p in (raw.get("patterns") or [])]
        pol.columns = _validate_columns(raw.get("columns") or {})
        ops = raw.get("operators")
        if ops is not None:
            if not isinstance(ops, dict) or not ops:
                raise PolicyError("operators must be a non-empty mapping of ENTITY_TYPE → {op: ...}")
            pol.operators = {}
            for ent, spec in ops.items():
                pol.operators[_validate_entity_name(str(ent), allow_default=True)] = _validate_op(str(ent), spec)
        pol.operators.setdefault("DEFAULT", OpSpec("replace"))
        llm = raw.get("llm")
        if llm:
            if isinstance(llm, str):
                llm = {"model": llm}
            if not isinstance(llm, dict) or "model" not in llm:
                raise PolicyError("llm must be a model string ('ollama:gemma4:e4b') or a mapping with 'model'")
            pol.llm = validate_llm_ref(str(llm["model"]))
            pol.llm_entities = _validate_entity_list(llm.get("entities") or pol.llm_entities, "llm.entities")
            pol.llm_generic = bool(llm.get("generic", False))
        return pol

    def op_for(self, entity_type: str) -> OpSpec:
        return self.operators.get(entity_type) or self.operators["DEFAULT"]

    @property
    def reversible(self) -> bool:
        return any(spec.op in REVERSIBLE_OPS for spec in self.operators.values())

    @property
    def needs_sidecar(self) -> bool:
        return any(spec.op in SIDECAR_OPS for spec in self.operators.values())

    @property
    def residual_entities(self) -> set[str]:
        return {ent for ent, spec in self.operators.items() if spec.op in RESIDUAL_OPS}

    def forced_entity(self, group: str) -> Optional[str]:
        """Entity forced by `columns:` for a column name or dotted key path (full path or last segment)."""
        return self.columns.get(group) or self.columns.get(group.rsplit(".", 1)[-1])


def _validate_threshold(value: Any) -> float:
    try:
        t = float(value)
    except (TypeError, ValueError):
        raise PolicyError(f"threshold must be a number in [0, 1], got {value!r}")
    if not 0.0 <= t <= 1.0:
        raise PolicyError(f"threshold must be in [0, 1], got {t}")
    return t


def _validate_entity_name(name: str, allow_default: bool = False) -> str:
    if allow_default and name == "DEFAULT":
        return name
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
        raise PolicyError(f"entity type '{name}' must be UPPER_SNAKE_CASE (e.g. PERSON, TH_TNIN)")
    return name


def _validate_entity_list(values: Any, where: str) -> list[str]:
    if isinstance(values, str):
        values = [v.strip() for v in values.split(",") if v.strip()]
    if not isinstance(values, list):
        raise PolicyError(f"{where} must be a list of entity types")
    return [_validate_entity_name(str(v)) for v in values]


def _validate_columns(raw: Any) -> dict[str, str]:
    if isinstance(raw, str):
        pairs = [p.strip() for p in raw.split(",") if p.strip()]
        try:
            raw = dict(p.split("=", 1) for p in pairs)
        except ValueError:
            raise PolicyError("--columns takes name=ENTITY pairs, e.g. hn=ID,mrn=ID")
    if not isinstance(raw, dict):
        raise PolicyError("columns must be a mapping of column/key name → ENTITY_TYPE")
    return {str(k): _validate_entity_name(str(v)) for k, v in raw.items()}


def _validate_pattern(raw: Any) -> PatternSpec:
    if not isinstance(raw, dict) or not {"name", "entity", "regex"} <= set(raw):
        raise PolicyError("each pattern needs name, entity, regex (optional score, context)")
    try:
        re.compile(raw["regex"])
    except re.error as exc:
        raise PolicyError(f"pattern '{raw['name']}': invalid regex — {exc}") from exc
    score = _validate_threshold(raw.get("score", 0.6))
    ctx = raw.get("context") or []
    if not isinstance(ctx, list):
        raise PolicyError(f"pattern '{raw['name']}': context must be a list of words")
    return PatternSpec(str(raw["name"]), _validate_entity_name(str(raw["entity"])), str(raw["regex"]), score, [str(c) for c in ctx])


def _validate_op(entity: str, spec: Any) -> OpSpec:
    if isinstance(spec, str):
        spec = {"op": spec}
    if not isinstance(spec, dict) or "op" not in spec:
        raise PolicyError(f"operators.{entity}: expected {{op: <name>, ...params}}")
    op = str(spec["op"])
    params = {k: v for k, v in spec.items() if k != "op"}
    if op not in BUILTIN_OPS | CUSTOM_OPS:
        raise PolicyError(f"operators.{entity}: unknown op '{op}' — use one of {', '.join(sorted(BUILTIN_OPS | CUSTOM_OPS))}")
    if op == "mask":
        if "chars_to_mask" not in params or not isinstance(params["chars_to_mask"], int) or params["chars_to_mask"] < 0:
            raise PolicyError(f"operators.{entity}: mask needs chars_to_mask (int ≥ 0)")
        params.setdefault("masking_char", "*")
        params.setdefault("from_end", False)
        if len(str(params["masking_char"])) != 1:
            raise PolicyError(f"operators.{entity}: masking_char must be one character")
    elif op == "hash":
        params.setdefault("hash_type", "sha256")
        if params["hash_type"] not in {"sha256", "sha512"}:
            raise PolicyError(f"operators.{entity}: hash_type must be sha256 or sha512")
    elif op == "encrypt":
        if "key" in params:
            raise PolicyError(f"operators.{entity}: never put the key in a policy — export DEID_KEY instead")
    elif op == "replace":
        if "new_value" in params and not isinstance(params["new_value"], str):
            raise PolicyError(f"operators.{entity}: replace.new_value must be a string")
    elif op == "date_shift":
        days = params.get("days", "random")
        if days != "random" and not isinstance(days, int):
            raise PolicyError(f"operators.{entity}: date_shift.days must be an int or 'random'")
        params["days"] = days
        rng = params.setdefault("range", 365)
        if not isinstance(rng, int) or rng <= 0:
            raise PolicyError(f"operators.{entity}: date_shift.range must be a positive int")
    elif op == "pseudonym":
        fmt = params.setdefault("format", "<{entity}_{n}>")
        if "{n}" not in fmt:
            raise PolicyError(f"operators.{entity}: pseudonym.format must contain {{n}}")
    return OpSpec(op, params)


def is_cloud_model(model: str) -> bool:
    """Ollama routes `*:cloud` / `*-cloud` tags to its hosted service — PHI would leave the machine."""
    return "cloud" in model.rsplit(":", 1)[-1]


def validate_llm_ref(ref: str) -> str:
    """'ollama:<model>' — the only provider; cloud-routed tags are refused (they leave the device)."""
    if not ref.startswith("ollama:") or len(ref) <= len("ollama:"):
        raise PolicyError(f"--llm must be 'ollama:<model>' (e.g. {DEFAULT_LLM_MODEL}), got '{ref}'")
    model = ref[len("ollama:"):]
    if is_cloud_model(model):
        raise PolicyError(f"'{model}' is an Ollama cloud-routed model — PHI would leave this machine; pick a local tag")
    return ref


# ---------------------------------------------------------------------------
# Custom operators (registered on the anonymizer / deanonymizer engines)
# ---------------------------------------------------------------------------


class Pseudonym(Operator):
    """Consistent per-run surrogate: the same value always maps to the same <TYPE_n>."""

    def operate(self, text: str, params: dict | None = None) -> str:
        entity = params["entity_type"]
        mapping: dict[str, dict[str, str]] = params["entity_mapping"]
        per_type = mapping.setdefault(entity, {})
        if text in per_type:
            return per_type[text]
        per_type[text] = params.get("format", "<{entity}_{n}>").format(entity=entity, n=len(per_type) + 1)
        return per_type[text]

    def validate(self, params: dict | None = None) -> None:
        if not params or "entity_mapping" not in params:
            raise ValueError("pseudonym needs entity_mapping")

    def operator_name(self) -> str:
        return "pseudonym"

    def operator_type(self) -> OperatorType:
        return OperatorType.Anonymize


class PseudonymReverse(Operator):
    def operate(self, text: str, params: dict | None = None) -> str:
        for per_type in params["entity_mapping"].values():
            for original, surrogate in per_type.items():
                if surrogate == text:
                    return original
        return text

    def validate(self, params: dict | None = None) -> None:
        if not params or "entity_mapping" not in params:
            raise ValueError("pseudonym restore needs entity_mapping")

    def operator_name(self) -> str:
        return "pseudonym"

    def operator_type(self) -> OperatorType:
        return OperatorType.Deanonymize


def shift_date(text: str, days: int) -> Optional[str]:
    """Shift a date string by `days`, preserving its format; None when no known format parses it."""
    for fmt in DATE_FORMATS:
        try:
            return (datetime.strptime(text.strip(), fmt) + timedelta(days=days)).strftime(fmt)
        except ValueError:
            continue
    return None


class DateShift(Operator):
    """Shift parseable dates by a per-run offset; unparseable ones fall back to a pseudonym counter."""

    def operate(self, text: str, params: dict | None = None) -> str:
        shifted = shift_date(text, params["days"])
        if shifted is not None:
            return shifted
        return Pseudonym().operate(text, {"entity_type": params["entity_type"], "entity_mapping": params["entity_mapping"]})

    def validate(self, params: dict | None = None) -> None:
        if not params or "days" not in params or "entity_mapping" not in params:
            raise ValueError("date_shift needs days and entity_mapping")

    def operator_name(self) -> str:
        return "date_shift"

    def operator_type(self) -> OperatorType:
        return OperatorType.Anonymize


class DateShiftReverse(Operator):
    def operate(self, text: str, params: dict | None = None) -> str:
        shifted = shift_date(text, -params["days"])
        return shifted if shifted is not None else PseudonymReverse().operate(text, params)

    def validate(self, params: dict | None = None) -> None:
        if not params or "days" not in params:
            raise ValueError("date_shift restore needs days")

    def operator_name(self) -> str:
        return "date_shift"

    def operator_type(self) -> OperatorType:
        return OperatorType.Deanonymize


# ---------------------------------------------------------------------------
# Run state: the per-run mutable context shared by every cell/segment of one file
# ---------------------------------------------------------------------------


@dataclass
class RunState:
    policy: Policy
    entity_mapping: dict[str, dict[str, str]] = field(default_factory=dict)
    date_offset_days: int = 0
    key: Optional[str] = None

    @classmethod
    def start(cls, policy: Policy) -> "RunState":
        state = cls(policy=policy)
        for spec in policy.operators.values():
            if spec.op == "date_shift":
                state.date_offset_days = (
                    spec.params["days"] if spec.params["days"] != "random"
                    else random.choice([d for d in range(-spec.params["range"], spec.params["range"] + 1) if d != 0])
                )
            if spec.op == "encrypt":
                state.key = require_key()
        return state

    def operator_configs(self, reverse: bool = False) -> dict:
        """Presidio OperatorConfig per entity type (DEFAULT included) — forward or restore direction."""
        from presidio_anonymizer import OperatorConfig

        configs = {}
        for entity, spec in self.policy.operators.items():
            op, params = spec.op, dict(spec.params)
            if op == "pseudonym":
                params = {"entity_mapping": self.entity_mapping, "format": params["format"]}
            elif op == "date_shift":
                params = {"days": self.date_offset_days, "entity_mapping": self.entity_mapping}
            elif op == "encrypt":
                params = {"key": self.key or require_key()}
                if reverse:
                    op = "decrypt"
            elif reverse:
                continue  # replace/redact/mask/hash/keep are one-way; nothing to restore
            configs[entity] = OperatorConfig(op, params)
        if reverse:
            configs.setdefault("DEFAULT", OperatorConfig("keep"))
        return configs


def require_key() -> str:
    key = os.environ.get("DEID_KEY")
    if not key:
        fail(EXIT_ENV, "encrypt/decrypt needs DEID_KEY in the environment (16, 24 or 32 bytes); never pass it as a flag")
    if len(key.encode()) not in (16, 24, 32):
        fail(EXIT_ENV, f"DEID_KEY must be 16, 24 or 32 bytes, got {len(key.encode())}")
    return key


# ---------------------------------------------------------------------------
# Engines (lazy — importing presidio_analyzer loads spaCy)
# ---------------------------------------------------------------------------


class _RegistryNoise(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "not added to registry" not in record.getMessage()


def _quiet_presidio(verbose: bool) -> None:
    for name in ("presidio-analyzer", "presidio_analyzer", "presidio-anonymizer", "presidio-image-redactor"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO if verbose else logging.WARNING)
        lg.addFilter(_RegistryNoise())
    for name in ("pydicom", "absl", "py.warnings"):
        logging.getLogger(name).setLevel(logging.ERROR)
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", message=".*pixel_data_handlers.*")


def build_analyzer(policy: Policy, llm: Optional[str] = None):
    """AnalyzerEngine with the always-on extras: TH_TNIN under `en`, policy patterns, optional Ollama LLM."""
    try:
        from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
        from presidio_analyzer.predefined_recognizers import ThTninRecognizer
    except ImportError as exc:  # pragma: no cover — uv resolves deps; guards a broken env
        fail(EXIT_ENV, f"presidio-analyzer import failed: {exc} — rerun once outside the sandbox so uv can fetch the env")
    try:
        engine = AnalyzerEngine(supported_languages=[policy.language])
    except OSError as exc:
        fail(EXIT_ENV, f"spaCy model missing for '{policy.language}': {exc} — first run needs network to fetch en_core_web_lg")
    engine.registry.add_recognizer(ThTninRecognizer(supported_language=policy.language))
    for p in policy.patterns:
        engine.registry.add_recognizer(
            PatternRecognizer(supported_entity=p.entity, name=p.name, patterns=[Pattern(p.name, p.regex, p.score)],
                              context=p.context or None, supported_language=policy.language)
        )
    llm_ref = llm or policy.llm
    if llm_ref:
        engine.registry.add_recognizer(_llm_recognizer(policy, llm_ref))
    return engine


def _llm_recognizer(policy: Policy, llm_ref: str):
    """presidio's LangExtract recognizer over local Ollama, configured from a generated YAML."""
    try:
        from presidio_analyzer.predefined_recognizers import BasicLangExtractRecognizer
    except ImportError as exc:
        fail(EXIT_ENV, f"LangExtract extra missing: {exc}")
    model = llm_ref[len("ollama:"):]
    models = ollama_models()
    if not models:
        fail(EXIT_ENV, f"Ollama not reachable at {OLLAMA_URL} — start it (`ollama serve`) or drop --llm")
    if model not in models and f"{model}:latest" not in models:
        fail(EXIT_ENV, f"model '{model}' is not pulled — `ollama pull {model}` or pick one of: {', '.join(m for m in models if not is_cloud_model(m))}")
    entities = [e for e in policy.llm_entities if e != "GENERIC_PII_ENTITY"]
    mappings = {"person": "PERSON", "name": "PERSON", "patient": "PERSON", "doctor": "PERSON", "provider": "PERSON",
                "location": "LOCATION", "address": "LOCATION", "organization": "ORGANIZATION", "hospital": "ORGANIZATION",
                "phone": "PHONE_NUMBER", "phone_number": "PHONE_NUMBER", "email": "EMAIL_ADDRESS", "date": "DATE_TIME",
                "date_time": "DATE_TIME", "id": "ID", "identifier": "ID", "hn": "ID", "mrn": "ID", "patient_id": "ID",
                "medical_record_number": "ID", "url": "URL", "ip_address": "IP_ADDRESS", "ssn": "US_SSN",
                "us_ssn": "US_SSN", "credit_card": "CREDIT_CARD", "medical_license": "MEDICAL_LICENSE",
                "iban": "IBAN_CODE", "passport": "ID", "national_id": "ID"}
    cfg = {
        "lm_recognizer": {"supported_entities": entities, "labels_to_ignore": [],
                          "enable_generic_consolidation": policy.llm_generic, "min_score": 0.5},
        "langextract": {
            "prompt_file": "langextract_prompts/default_pii_phi_prompt.j2",
            "examples_file": "langextract_prompts/default_pii_phi_examples.yaml",
            "model": {"model_id": model,
                      "provider": {"name": "ollama", "kwargs": {"model_url": OLLAMA_URL},
                                   "extract_params": {"temperature": None, "use_schema_constraints": False,
                                                      "fence_output": False, "max_char_buffer": 600, "show_progress": False},
                                   "language_model_params": {"timeout": 300, "num_ctx": 8192}}},
            "entity_mappings": mappings,
        },
    }
    tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    yaml.safe_dump(cfg, tmp)
    tmp.close()
    return BasicLangExtractRecognizer(config_path=tmp.name, supported_language=policy.language)


def build_anonymizer():
    from presidio_anonymizer import AnonymizerEngine

    engine = AnonymizerEngine()
    engine.add_anonymizer(Pseudonym)
    engine.add_anonymizer(DateShift)
    return engine


def build_deanonymizer():
    from presidio_anonymizer import DeanonymizeEngine

    engine = DeanonymizeEngine()
    engine.add_deanonymizer(PseudonymReverse)
    engine.add_deanonymizer(DateShiftReverse)
    return engine


def ollama_models() -> list[str]:
    import urllib.request

    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as resp:
            return [m["name"] for m in json.load(resp).get("models", [])]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Text path
# ---------------------------------------------------------------------------


def analyze_text(analyzer, text: str, policy: Policy, threshold: float, explain: bool = False):
    if not text.strip():
        return []
    return analyzer.analyze(
        text=text, language=policy.language, entities=policy.entities or None, score_threshold=threshold,
        allow_list=policy.allow or None, return_decision_process=explain,
    )


def analyze_batch(analyzer, texts: list[str], policy: Policy, threshold: float, context: Optional[list[str]] = None) -> list[list]:
    """Span findings for many strings in one spaCy batch (structured cells)."""
    from presidio_analyzer import BatchAnalyzerEngine

    if not texts:
        return []
    batch = BatchAnalyzerEngine(analyzer_engine=analyzer)
    return list(batch.analyze_iterator(
        texts=texts, language=policy.language, entities=policy.entities or None, score_threshold=threshold,
        allow_list=policy.allow or None, batch_size=64, context=context or None,
    ))


def finding_dict(r, text: str, explain: bool = False) -> dict[str, Any]:
    d = {"entity_type": r.entity_type, "start": r.start, "end": r.end, "score": round(float(r.score), 3),
         "text": text[r.start:r.end]}
    meta = getattr(r, "recognition_metadata", None) or {}
    if meta.get("recognizer_name"):
        d["recognizer"] = meta["recognizer_name"]
    if explain and getattr(r, "analysis_explanation", None):
        d["explanation"] = r.analysis_explanation.textual_explanation or r.analysis_explanation.__dict__
    return d


def anonymize_segment(anonymizer, text: str, results, state: RunState) -> tuple[str, list[dict]]:
    """Apply the policy to one string; returns (new_text, items) where items index the NEW text."""
    if not results:
        return text, []
    out = anonymizer.anonymize(text=text, analyzer_results=results, operators=state.operator_configs())
    items = [i.to_dict() for i in out.items]
    for item in items:
        item.pop("score", None)
    return out.text, items


def restore_segment(deanonymizer, text: str, items: list[dict], state: RunState) -> str:
    from presidio_anonymizer.entities import OperatorResult

    reversible = [OperatorResult(start=i["start"], end=i["end"], entity_type=i["entity_type"], text=i.get("text"), operator=i["operator"])
                  for i in items if i["operator"] in REVERSIBLE_OPS]
    if not reversible:
        return text
    return deanonymizer.deanonymize(text=text, entities=reversible, operators=state.operator_configs(reverse=True)).text


# ---------------------------------------------------------------------------
# Structured path — CSV columns and JSON keys share one cell model and one operator path
# ---------------------------------------------------------------------------


@dataclass
class Cell:
    group: str  # column name, or dotted key path (list indices dropped)
    address: dict[str, Any]  # {"column", "row"} for csv · {"path": [...]} for json
    value: str


def load_cells(kind: str, source: Path) -> tuple[Any, list[Cell]]:
    """The container (DataFrame or JSON object) plus every string cell in it."""
    if kind == "csv":
        import pandas as pd

        df = pd.read_csv(source, dtype=str, keep_default_na=False, sep="\t" if source.suffix == ".tsv" else ",")
        cells = [Cell(str(col), {"column": str(col), "row": row}, v) for col in df.columns for row, v in enumerate(df[col].tolist())]
        return df, cells
    data = json.loads(source.read_text(encoding="utf-8"))
    cells = [Cell(dotted(path), {"path": list(path)}, value) for path, value in json_leaves(data)]
    return data, cells


def store_cell(kind: str, container: Any, cell: Cell, value: str) -> None:
    if kind == "csv":
        container.at[cell.address["row"], cell.address["column"]] = value
    else:
        node = container
        for p in cell.address["path"][:-1]:
            node = node[p]
        node[cell.address["path"][-1]] = value


def write_container(kind: str, container: Any, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if kind == "csv":
        container.to_csv(out, index=False, sep="\t" if out.suffix == ".tsv" else ",")
    else:
        out.write_text(json.dumps(container, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cell_from_address(cells: list[Cell], address: dict[str, Any]) -> Optional[Cell]:
    for c in cells:
        if c.address == address:
            return c
    return None


def json_leaves(node: Any, path: tuple = ()) -> Iterable[tuple[tuple, str]]:
    """(path, value) for every string leaf; path elements are keys or list indices."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from json_leaves(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from json_leaves(v, path + (i,))
    elif isinstance(node, str):
        yield path, node


def dotted(path: Iterable) -> str:
    return ".".join(str(p) for p in path if not isinstance(p, int))


def whole_cell_result(entity_type: str, text: str):
    from presidio_anonymizer.entities import RecognizerResult

    return RecognizerResult(entity_type=entity_type, start=0, end=len(text), score=1.0)


PLACEHOLDER_RE = re.compile(r"^\s*<[A-Z][A-Z0-9_]*(_\d+)?>\s*$")


def is_placeholder(value: str) -> bool:
    """A value already replaced by us (<PERSON>, <ID_3>) — not an identifier, never re-flagged."""
    return bool(PLACEHOLDER_RE.match(value))


def group_context(group: str) -> list[str]:
    """Words from a column name / key path — presidio boosts recognizers whose context words match
    (`phone` → PhoneRecognizer), which is what lifts a bare `212-555-5555` above the threshold."""
    return [w for w in re.split(r"[^A-Za-z0-9]+", group.lower()) if w]


def classify_cells(analyzer, cells: list[Cell], policy: Policy, threshold: float) -> tuple[dict[str, str], list[list]]:
    """Span-scan every cell (one spaCy batch per group, with the group name as context), then decide
    per group (column / key) whether it holds *bare entities* — forced by policy.columns, or inferred
    when most cells hit and the hit covers the cell. Typed groups get a whole-cell result on every
    non-empty cell (so NER misses are still covered); the rest keep their span results.
    Returns (typed groups, per-cell results)."""
    groups: dict[str, list[int]] = {}
    for i, c in enumerate(cells):
        groups.setdefault(c.group, []).append(i)
    per_cell: list[list] = [[] for _ in cells]
    for group, idxs in groups.items():
        for i, results in zip(idxs, analyze_batch(analyzer, [cells[i].value for i in idxs], policy, threshold, context=group_context(group))):
            per_cell[i] = results
    typed: dict[str, str] = {}
    for group, idxs in groups.items():
        forced = policy.forced_entity(group)
        if forced:
            typed[group] = forced
            continue
        nonempty = [i for i in idxs if cells[i].value.strip() and not is_placeholder(cells[i].value)]
        hits = [i for i in nonempty if per_cell[i]]
        if not nonempty or len(hits) / len(nonempty) < COLUMN_HIT_RATIO:
            continue
        best = [max(per_cell[i], key=lambda r: r.score) for i in hits]
        coverage = sum((r.end - r.start) / len(cells[i].value) for i, r in zip(hits, best)) / len(hits)
        if coverage < COLUMN_COVERAGE:
            continue
        typed[group] = Counter(r.entity_type for r in best).most_common(1)[0][0]
    if policy.entities:
        typed = {g: e for g, e in typed.items() if e in policy.entities}
    for i, c in enumerate(cells):
        if c.group in typed:
            per_cell[i] = [whole_cell_result(typed[c.group], c.value)] if c.value.strip() and not is_placeholder(c.value) else []
    return typed, per_cell


# ---------------------------------------------------------------------------
# Image / DICOM path
# ---------------------------------------------------------------------------


def build_image_analyzer(analyzer):
    if not shutil.which("tesseract"):
        fail(EXIT_ENV, "tesseract not found on PATH — `brew install tesseract` (macOS) / apt install tesseract-ocr")
    import pydicom  # noqa: F401 — pydicom resets its logger level on import; quiet it before the redactor imports it

    logging.getLogger("pydicom").setLevel(logging.ERROR)
    from presidio_image_redactor import ImageAnalyzerEngine

    return ImageAnalyzerEngine(analyzer_engine=analyzer)


def image_kwargs(policy: Policy, threshold: float) -> dict[str, Any]:
    # presidio-image-redactor iterates allow_list unconditionally — it must be a list, never None
    return {"language": policy.language, "entities": policy.entities or None, "score_threshold": threshold,
            "allow_list": list(policy.allow)}


def image_findings(image_analyzer, image, policy: Policy, threshold: float) -> list[dict]:
    """Mirror of ImageAnalyzerEngine.analyze that also keeps the OCR text, so each box reports what it covers."""
    pre, meta = image_analyzer.image_preprocessor.preprocess_image(image)
    ocr = image_analyzer.remove_space_boxes(image_analyzer.ocr.perform_ocr(pre))
    if meta and "scale_factor" in meta:
        ocr = image_analyzer._scale_bbox_results(ocr, meta["scale_factor"])
    text = image_analyzer.ocr.get_text_from_ocr_dict(ocr)
    kwargs = image_kwargs(policy, threshold)
    results = image_analyzer.analyzer_engine.analyze(text=text, **kwargs)
    boxes = image_analyzer.map_analyzer_results_to_bounding_boxes(results, ocr, text, kwargs["allow_list"])
    return [{"entity_type": b.entity_type, "score": round(float(b.score), 3), "left": b.left, "top": b.top,
             "width": b.width, "height": b.height, "text": text[b.start:b.end]} for b in boxes]


def parse_fill(value: str):
    if value == "black":
        return (0, 0, 0)
    if value == "white":
        return (255, 255, 255)
    m = re.fullmatch(r"(\d{1,3}),(\d{1,3}),(\d{1,3})", value)
    if m:
        return tuple(int(x) for x in m.groups())
    fail(EXIT_PARAMS, "image --fill must be black, white, or R,G,B")


def dicom_files(source: Path) -> list[Path]:
    return sorted(p for p in source.rglob("*") if p.suffix.lower() in DICOM_EXT) if source.is_dir() else [source]


# ---------------------------------------------------------------------------
# Routing, sidecar, formatting
# ---------------------------------------------------------------------------


def kind_of(path: Path, dicom_flag: bool = False) -> str:
    if dicom_flag or path.is_dir():
        return "dicom"
    ext = path.suffix.lower()
    if ext in TEXT_EXT:
        return "text"
    if ext in JSON_EXT:
        return "json"
    if ext in CSV_EXT:
        return "csv"
    if ext in IMAGE_EXT:
        return "image"
    if ext in DICOM_EXT:
        return "dicom"
    if ext in REFUSED_EXT:
        fail(EXIT_PARAMS, f"{path.name}: convert to Markdown first (parse-to-md, local `lit`), then de-identify the .md")
    fail(EXIT_PARAMS, f"{path.name}: unsupported extension '{ext}' — text/json/csv/image/.dcm (or --dicom for a directory)")


def require_input(path: Path) -> Path:
    if not path.exists():
        fail(EXIT_PARAMS, f"input not found: {path}")
    return path


def sidecar_write(path: Path, state: RunState, kind: str, source: Path, extra: dict[str, Any]) -> None:
    data = {"version": SIDECAR_VERSION, "kind": kind, "source": str(source), "policy": state.policy.name,
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "date_offset_days": state.date_offset_days, "entity_mapping": state.entity_mapping, **extra}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sidecar_read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(EXIT_PARAMS, f"sidecar unreadable: {exc}")
    if data.get("version") != SIDECAR_VERSION or "kind" not in data:
        fail(EXIT_PARAMS, f"{path}: not a deid sidecar (version {SIDECAR_VERSION})")
    return data


def sidecar_items(data: dict[str, Any]) -> Iterable[dict]:
    yield from data.get("items", [])
    for cell in data.get("cells", []):
        yield from cell.get("items", [])


def state_from_sidecar(data: dict[str, Any], policy: Policy) -> RunState:
    state = RunState(policy=policy, entity_mapping=data.get("entity_mapping", {}), date_offset_days=data.get("date_offset_days", 0))
    if any(i.get("operator") == "encrypt" for i in sidecar_items(data)):
        state.key = require_key()
    return state


def print_findings(findings: list[dict], where: str, threshold: float) -> None:
    for f in findings:
        if "start" in f:
            loc = f"@{f['start']}-{f['end']}"
        elif "left" in f:
            loc = f"[{f['left']},{f['top']} {f['width']}x{f['height']}]"
        else:
            loc = ""
        if f.get("mode"):
            cell = f" {f['group']} ({f['mode']}, {f['cells']} cells)"
        elif "column" in f:
            cell = f" {f['column']}#{f['row']}"
        elif "path" in f:
            cell = " " + ".".join(str(p) for p in f["path"])
        else:
            cell = f" {Path(f['file']).name}" if "file" in f else ""
        text = f" {json.dumps(f['text'], ensure_ascii=False)}" if f.get("text") is not None else ""
        rec = f"  ({f['recognizer']})" if f.get("recognizer") else ""
        score = f"{f['score']:.2f}" if f.get("score") is not None else "  - "
        typer.echo(f"{f['entity_type']:<22} {score}{cell}{text} {loc}{rec}")
    typer.echo(f"{len(findings)} finding(s) ≥ {threshold} in {where}")


def count_by_entity(items: Iterable[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for i in items:
        counts[i["entity_type"]] = counts.get(i["entity_type"], 0) + 1
    return dict(sorted(counts.items()))


# ---------------------------------------------------------------------------
# Verbs
# ---------------------------------------------------------------------------

PolicyOpt = Annotated[Optional[str], typer.Option("--policy", "-p", help="Preset name (references/policies/*.yaml) or a YAML path.")]
ThresholdOpt = Annotated[Optional[float], typer.Option("--threshold", "-t", min=0.0, max=1.0, help="Min score; overrides the policy.")]
EntitiesOpt = Annotated[Optional[str], typer.Option("--entities", "-e", help="Comma list restricting entity types (PERSON,TH_TNIN).")]
AllowOpt = Annotated[Optional[str], typer.Option("--allow", help="Comma list of literals never flagged.")]
ColumnsOpt = Annotated[Optional[str], typer.Option("--columns", help="Force column/key → entity for csv/json: hn=ID,mrn=ID.")]
LlmOpt = Annotated[Optional[str], typer.Option("--llm", help=f"Add a local Ollama LLM recognizer, e.g. {DEFAULT_LLM_MODEL} (Thai names). Cloud tags refused.")]
JsonOpt = Annotated[bool, typer.Option("--json", help="Machine-readable output.")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Show presidio's own log lines.")]
DicomOpt = Annotated[bool, typer.Option("--dicom", help="Treat the input directory as DICOM files.")]


def _load_policy(policy: Optional[str], threshold: Optional[float] = None, entities: Optional[str] = None,
                 allow: Optional[str] = None, columns: Optional[str] = None, llm: Optional[str] = None) -> Policy:
    try:
        pol = Policy.load(policy)
        if threshold is not None:
            pol.threshold = threshold
        if entities:
            pol.entities = _validate_entity_list(entities, "--entities")
        if allow:
            pol.allow.extend(a.strip() for a in allow.split(",") if a.strip())
        if columns:
            pol.columns.update(_validate_columns(columns))
        if llm:
            pol.llm = validate_llm_ref(llm)
    except PolicyError as exc:
        fail(EXIT_PARAMS, str(exc))
    return pol


def collect_findings(kind: str, source: Path, pol: Policy, analyzer, explain: bool = False) -> tuple[list[dict], dict[str, Any]]:
    """Every finding in `source` for its kind, plus kind-specific extras (typed columns/keys)."""
    findings: list[dict] = []
    extra: dict[str, Any] = {}

    if kind == "text":
        text = source.read_text(encoding="utf-8")
        findings = [finding_dict(r, text, explain) for r in analyze_text(analyzer, text, pol, pol.threshold, explain)]
    elif kind in STRUCTURED:
        _, cells = load_cells(kind, source)
        typed, per_cell = classify_cells(analyzer, cells, pol, pol.threshold)
        extra["typed"] = typed
        for group, ent in typed.items():
            n = sum(1 for c, results in zip(cells, per_cell) if c.group == group and results)
            if n:
                findings.append({"entity_type": ent, "score": None, "group": group, "mode": "column" if kind == "csv" else "key", "cells": n})
        for c, results in zip(cells, per_cell):
            if c.group in typed:
                continue
            for r in results:
                findings.append({**finding_dict(r, c.value), **c.address})
    elif kind == "image":
        from PIL import Image

        findings = image_findings(build_image_analyzer(analyzer), Image.open(source), pol, pol.threshold)
    elif kind == "dicom":
        import pydicom
        from presidio_image_redactor import DicomImageRedactorEngine

        engine = DicomImageRedactorEngine(image_analyzer_engine=build_image_analyzer(analyzer))
        for f in dicom_files(source):
            _, boxes = engine.redact_and_return_bbox(pydicom.dcmread(f), fill="contrast", **image_kwargs(pol, pol.threshold))
            for b in boxes:
                findings.append({"file": str(f), "entity_type": b.get("entity_type", "?"),
                                 "score": round(float(b["score"]), 3) if b.get("score") is not None else None,
                                 "left": b.get("left"), "top": b.get("top"), "width": b.get("width"), "height": b.get("height")})
    return findings, extra


@app.command()
def entities(
    lang: Annotated[str, typer.Option("--lang", help="Language code.")] = "en",
    as_json: JsonOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """List entity types the analyzer can detect (PHI-relevant ones marked)."""
    _quiet_presidio(verbose)
    analyzer = build_analyzer(Policy(language=lang))
    names = sorted(set(analyzer.get_supported_entities(language=lang)))
    if as_json:
        emit([{"entity_type": n, "phi": n in PHI_ENTITIES} for n in names])
        return
    for n in names:
        typer.echo(f"{'*' if n in PHI_ENTITIES else ' '} {n}")
    typer.echo(f"{len(names)} entity types for '{lang}'  (* = PHI-relevant; see references/entities.md)")


@app.command()
def scan(
    source: Annotated[Path, typer.Argument(help="File to scan (or a DICOM directory with --dicom).")],
    policy: PolicyOpt = None,
    threshold: ThresholdOpt = None,
    entities: EntitiesOpt = None,
    allow: AllowOpt = None,
    columns: ColumnsOpt = None,
    llm: LlmOpt = None,
    explain: Annotated[bool, typer.Option("--explain", help="Include each recognizer's decision explanation (text only).")] = False,
    dicom: DicomOpt = False,
    as_json: JsonOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Find PHI/PII. Exit 1 when anything scores at/above the threshold, 0 when clean."""
    pol = _load_policy(policy, threshold, entities, allow, columns, llm)
    kind = kind_of(require_input(source), dicom)
    _quiet_presidio(verbose)
    findings, extra = collect_findings(kind, source, pol, build_analyzer(pol), explain)
    if as_json:
        emit({"source": str(source), "kind": kind, "threshold": pol.threshold, "count": len(findings),
              "by_entity": count_by_entity(findings), **extra, "findings": findings})
    else:
        print_findings(findings, str(source), pol.threshold)
    raise typer.Exit(EXIT_FINDINGS if findings else 0)


@app.command()
def anonymize(
    source: Annotated[Path, typer.Argument(help="File to de-identify (or a DICOM directory with --dicom).")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output file (directory for DICOM).")],
    policy: PolicyOpt = "redact",
    sidecar: Annotated[Optional[Path], typer.Option("--sidecar", help="Write re-identification key material here (needed by restore).")] = None,
    threshold: ThresholdOpt = None,
    entities: EntitiesOpt = None,
    allow: AllowOpt = None,
    columns: ColumnsOpt = None,
    llm: LlmOpt = None,
    fill: Annotated[Optional[str], typer.Option("--fill", help="Box fill — image: black|white|R,G,B · DICOM: contrast|background.")] = None,
    dicom: DicomOpt = False,
    as_json: JsonOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Apply a policy and write the de-identified output to -o (never stdout)."""
    pol = _load_policy(policy, threshold, entities, allow, columns, llm)
    kind = kind_of(require_input(source), dicom)
    if out.resolve() == source.resolve():
        fail(EXIT_PARAMS, "refusing to overwrite the input — pick a different -o")
    if pol.needs_sidecar and sidecar is None and kind in {"text", *STRUCTURED}:
        fail(EXIT_PARAMS, f"policy '{pol.name}' uses pseudonym/encrypt — pass --sidecar map.json so restore stays possible")
    _quiet_presidio(verbose)
    state = RunState.start(pol)
    analyzer = build_analyzer(pol)
    summary: dict[str, Any] = {"source": str(source), "out": str(out), "kind": kind, "policy": pol.name}

    if kind == "text":
        anonymizer = build_anonymizer()
        text = source.read_text(encoding="utf-8")
        new_text, items = anonymize_segment(anonymizer, text, analyze_text(analyzer, text, pol, pol.threshold), state)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(new_text, encoding="utf-8")
        summary["by_entity"] = count_by_entity(items)
        if sidecar:
            sidecar_write(sidecar, state, kind, source, {"items": items})
    elif kind in STRUCTURED:
        anonymizer = build_anonymizer()
        container, cells = load_cells(kind, source)
        typed, per_cell = classify_cells(analyzer, cells, pol, pol.threshold)
        recorded: list[dict] = []
        all_items: list[dict] = []
        for cell, results in zip(cells, per_cell):
            if not results:
                continue
            new_value, items = anonymize_segment(anonymizer, cell.value, results, state)
            store_cell(kind, container, cell, new_value)
            recorded.append({**cell.address, "items": items})
            all_items.extend(items)
        write_container(kind, container, out)
        summary.update({"typed": typed, "by_entity": count_by_entity(all_items)})
        if sidecar:
            sidecar_write(sidecar, state, kind, source, {"typed": typed, "cells": recorded})
    elif kind == "image":
        from PIL import Image
        from presidio_image_redactor import ImageRedactorEngine

        image_analyzer = build_image_analyzer(analyzer)
        image = Image.open(source)
        boxes = image_findings(image_analyzer, image, pol, pol.threshold)
        redacted = ImageRedactorEngine(image_analyzer_engine=image_analyzer).redact(
            image, fill=parse_fill(fill or "black"), **image_kwargs(pol, pol.threshold))
        out.parent.mkdir(parents=True, exist_ok=True)
        redacted.save(out)
        summary.update({"by_entity": count_by_entity(boxes), "boxes": len(boxes), "reversible": False})
    elif kind == "dicom":
        from presidio_image_redactor import DicomImageRedactorEngine

        if out.exists() and not out.is_dir():
            fail(EXIT_PARAMS, "DICOM output must be a directory")
        fill_value = fill or "contrast"
        if fill_value not in {"contrast", "background"}:
            fail(EXIT_PARAMS, "DICOM --fill must be contrast or background")
        out.mkdir(parents=True, exist_ok=True)
        engine = DicomImageRedactorEngine(image_analyzer_engine=build_image_analyzer(analyzer))
        kwargs = dict(fill=fill_value, save_bboxes=True, **image_kwargs(pol, pol.threshold))
        if source.is_dir():
            engine.redact_from_directory(str(source), str(out), **kwargs)
        else:
            engine.redact_from_file(str(source), str(out), **kwargs)
        summary.update({"files": len(dicom_files(source)), "reversible": False,
                        "note": "pixels only — scrub headers with dcmtk dcmodify"})

    if sidecar and kind in {"text", *STRUCTURED}:
        summary["sidecar"] = str(sidecar)
        summary["reversible"] = pol.reversible
    if as_json:
        emit(summary)
    else:
        by = summary.get("by_entity") or {}
        detail = ", ".join(f"{k}×{v}" for k, v in by.items()) or "nothing to change"
        typer.echo(f"{kind}: {detail} → {out}" + (f"  (sidecar: {sidecar})" if summary.get("sidecar") else ""))


@app.command()
def verify(
    source: Annotated[Path, typer.Argument(help="Anonymized file to re-scan (or a DICOM directory with --dicom).")],
    policy: PolicyOpt = "redact",
    threshold: ThresholdOpt = None,
    columns: ColumnsOpt = None,
    llm: LlmOpt = None,
    dicom: DicomOpt = False,
    as_json: JsonOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Re-scan an anonymized file with the policy that produced it. Entity types the policy keeps or
    date-shifts are expected residuals; anything else still detected is a leak → exit 1."""
    pol = _load_policy(policy, threshold, None, None, columns, llm)
    kind = kind_of(require_input(source), dicom)
    _quiet_presidio(verbose)
    findings, _ = collect_findings(kind, source, pol, build_analyzer(pol))
    expected = pol.residual_entities
    leaks = [f for f in findings if f["entity_type"] not in expected]
    residual = [f for f in findings if f["entity_type"] in expected]
    if as_json:
        emit({"source": str(source), "kind": kind, "policy": pol.name, "leaks": leaks, "expected_residual": len(residual),
              "by_entity": count_by_entity(leaks)})
    else:
        print_findings(leaks, str(source), pol.threshold)
        typer.echo(f"{'LEAKS' if leaks else 'clean'}: {len(leaks)} leak(s), {len(residual)} expected residual(s) "
                   f"({', '.join(sorted(expected)) or 'none'} allowed by policy '{pol.name}')")
    raise typer.Exit(EXIT_FINDINGS if leaks else 0)


@app.command()
def restore(
    source: Annotated[Path, typer.Argument(help="De-identified file produced by anonymize.")],
    out: Annotated[Path, typer.Option("--out", "-o", help="Where to write the restored file.")],
    sidecar: Annotated[Path, typer.Option("--sidecar", help="Sidecar written by anonymize.")],
    verbose: VerboseOpt = False,
) -> None:
    """Reverse pseudonym / date_shift / encrypt from the sidecar. Irreversible operators stay as they are."""
    require_input(source)
    data = sidecar_read(require_input(sidecar))
    kind = data["kind"]
    if kind not in {"text", *STRUCTURED}:
        fail(EXIT_PARAMS, f"restore supports text/csv/json sidecars, not '{kind}' (image redaction is destructive by design)")
    _quiet_presidio(verbose)
    try:
        pol = Policy.load(data.get("policy"))
    except PolicyError:
        pol = Policy()
    state = state_from_sidecar(data, pol)
    deanonymizer = build_deanonymizer()

    if kind == "text":
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(restore_segment(deanonymizer, source.read_text(encoding="utf-8"), data.get("items", []), state), encoding="utf-8")
    else:
        container, cells = load_cells(kind, source)
        for rec in data.get("cells", []):
            address = {k: v for k, v in rec.items() if k != "items"}
            cell = cell_from_address(cells, address)
            if cell is None:
                fail(EXIT_PARAMS, f"sidecar cell {address} not found in {source.name} — is this the file anonymize wrote?")
            store_cell(kind, container, cell, restore_segment(deanonymizer, cell.value, rec["items"], state))
        write_container(kind, container, out)
    typer.echo(f"restored {kind} → {out}")


@app.command()
def doctor(as_json: JsonOpt = False) -> None:
    """Check the environment: spaCy model, tesseract, Ollama. Exit 3 when the core (spaCy) is missing."""
    from importlib.metadata import PackageNotFoundError, version

    report: dict[str, Any] = {}
    for pkg in ("presidio-analyzer", "presidio-anonymizer", "presidio-image-redactor", "spacy", "en_core_web_lg"):
        try:
            report[pkg] = version(pkg)
        except PackageNotFoundError:
            report[pkg] = None
    try:
        import spacy

        spacy.load("en_core_web_lg")
        report["spacy_model"] = "ok"
    except Exception as exc:
        report["spacy_model"] = f"missing: {exc}"
    report["tesseract"] = shutil.which("tesseract") or "missing (brew install tesseract) — image/DICOM paths unavailable"
    models = ollama_models()
    report["ollama"] = {"url": OLLAMA_URL, "reachable": bool(models), "local_models": [m for m in models if not is_cloud_model(m)]}
    if as_json:
        emit(report)
    else:
        for k, v in report.items():
            typer.echo(f"{k:<26} {v if not isinstance(v, dict) else json.dumps(v, ensure_ascii=False)}")
    if report["spacy_model"] != "ok":
        raise typer.Exit(EXIT_ENV)


if __name__ == "__main__":
    app()
