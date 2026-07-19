"""Notebook parsing, validation, cell identity, and bounded presentation."""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import re
import secrets
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import nbformat
from jsonschema import ValidationError

from .contracts import CellInput, SourceInput
from .errors import NotebookToolError
from .filesystem import revision_of


CELL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SUPPORTED_CELL_TYPES = {"markdown", "code", "raw"}


@dataclass(slots=True)
class NotebookDocument:
    path: Path
    raw: dict[str, Any]
    original_bytes: bytes
    revision: str
    warnings: list[dict[str, str]]

    def handle_for(self, index: int) -> tuple[str, bool]:
        cell = self.raw["cells"][index]
        cell_id = cell.get("id")
        if isinstance(cell_id, str) and CELL_ID_PATTERN.fullmatch(cell_id):
            return cell_id, True
        seed = f"{self.revision}:{index}:{cell.get('cell_type')}:{source_text(cell.get('source', ''))}"
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
        return f"legacy_{digest}", False

    def index_for(self, handle: str) -> int:
        for index in range(len(self.raw["cells"])):
            if self.handle_for(index)[0] == handle:
                return index
        raise NotebookToolError(
            "CELL_NOT_FOUND",
            f"Cell id not found: {handle}",
            "Call notebook_read again and use a cell id from the current revision.",
        )


def load_document(path: Path, data: bytes) -> NotebookDocument:
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NotebookToolError(
            "INVALID_NOTEBOOK",
            f"Notebook is not valid UTF-8 JSON: {path}",
            "Repair the JSON or restore a valid .ipynb file, then retry.",
        ) from exc
    if not isinstance(raw, dict):
        raise NotebookToolError(
            "INVALID_NOTEBOOK",
            "Notebook root must be a JSON object.",
            "Replace the file with a valid nbformat notebook object.",
        )
    notebook_warnings = validate_notebook(raw)
    return NotebookDocument(
        path=path,
        raw=raw,
        original_bytes=data,
        revision=revision_of(data),
        warnings=notebook_warnings,
    )


def validate_notebook(raw: dict[str, Any]) -> list[dict[str, str]]:
    version = raw.get("nbformat")
    if version != 4:
        raise NotebookToolError(
            "UNSUPPORTED_NBFORMAT",
            f"Only nbformat 4 is supported; got {version!r}.",
            "Open and resave the notebook with a current Jupyter client or convert it to nbformat 4.",
        )
    cells = raw.get("cells")
    if not isinstance(cells, list):
        raise NotebookToolError(
            "INVALID_NOTEBOOK",
            "Notebook must contain a cells array.",
            "Repair the notebook structure so cells is an array.",
        )

    seen_ids: set[str] = set()
    missing_ids = 0
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            raise NotebookToolError(
                "INVALID_NOTEBOOK",
                f"Cell at index {index} is not an object.",
                "Repair or remove the malformed cell.",
            )
        if cell.get("cell_type") not in SUPPORTED_CELL_TYPES:
            raise NotebookToolError(
                "INVALID_NOTEBOOK",
                f"Cell at index {index} has unsupported cell_type {cell.get('cell_type')!r}.",
                "Use markdown, code, or raw cells.",
            )
        source_text(cell.get("source", ""))
        cell_id = cell.get("id")
        if cell_id is None:
            missing_ids += 1
        elif not isinstance(cell_id, str) or not CELL_ID_PATTERN.fullmatch(cell_id):
            raise NotebookToolError(
                "INVALID_NOTEBOOK",
                f"Cell at index {index} has invalid id {cell_id!r}.",
                "Use a 1-64 character cell id containing letters, digits, hyphen, or underscore.",
            )
        elif cell_id in seen_ids:
            raise NotebookToolError(
                "INVALID_NOTEBOOK",
                f"Duplicate cell id: {cell_id}",
                "Assign unique ids before retrying.",
            )
        else:
            seen_ids.add(cell_id)

    captured: list[dict[str, str]] = []
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            nbformat.validate(
                nbformat.from_dict(copy.deepcopy(raw)),
                relax_add_props=True,
            )
        captured.extend(
            {"code": warning.category.__name__, "message": str(warning.message)}
            for warning in caught
        )
    except ValidationError as exc:
        compact = " ".join(str(exc).split())[:500]
        raise NotebookToolError(
            "INVALID_NOTEBOOK",
            f"Notebook failed nbformat validation: {compact}",
            "Repair the reported notebook field and retry.",
        ) from exc

    if missing_ids:
        captured.append(
            {
                "code": "MISSING_CELL_IDS",
                "message": f"{missing_ids} cell(s) lack persisted ids; a guarded mutation will assign them.",
            }
        )
    unique: list[dict[str, str]] = []
    seen_warning: set[tuple[str, str]] = set()
    for item in captured:
        key = (item["code"], item["message"])
        if key not in seen_warning:
            seen_warning.add(key)
            unique.append(item)
    return unique


def serialize_notebook(raw: dict[str, Any]) -> bytes:
    return (json.dumps(raw, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def source_text(source: SourceInput | Any) -> str:
    if isinstance(source, str):
        return source
    if isinstance(source, list) and all(isinstance(item, str) for item in source):
        return "".join(source)
    raise NotebookToolError(
        "INVALID_NOTEBOOK",
        "Cell source must be a string or an array of strings.",
        "Repair the cell source and retry.",
    )


def source_lines(source: SourceInput) -> list[str]:
    text = source_text(source)
    return text.splitlines(keepends=True) if text else []


def source_sha256(cell: dict[str, Any]) -> str:
    return hashlib.sha256(
        source_text(cell.get("source", "")).encode("utf-8")
    ).hexdigest()


def new_cell(cell_input: CellInput, existing_ids: Iterable[str]) -> dict[str, Any]:
    existing = set(existing_ids)
    cell_id = generate_cell_id(existing)
    base: dict[str, Any] = {
        "cell_type": cell_input.cell_type,
        "id": cell_id,
        "metadata": copy.deepcopy(cell_input.metadata),
        "source": source_lines(cell_input.source),
    }
    if cell_input.cell_type == "code":
        base["execution_count"] = None
        base["outputs"] = []
    return base


def generate_cell_id(existing_ids: set[str]) -> str:
    for _ in range(100):
        candidate = secrets.token_hex(6)
        if candidate not in existing_ids:
            return candidate
    raise NotebookToolError(
        "INVALID_OPERATION",
        "Could not generate a unique cell id.",
        "Retry the operation.",
    )


def assign_missing_ids(
    raw: dict[str, Any], original: NotebookDocument
) -> dict[str, str]:
    existing = {cell["id"] for cell in raw["cells"] if isinstance(cell.get("id"), str)}
    mapping: dict[str, str] = {}
    for index, cell in enumerate(raw["cells"]):
        if not isinstance(cell.get("id"), str):
            handle, _ = original.handle_for(index)
            cell_id = _legacy_cell_id(handle, existing)
            existing.add(cell_id)
            cell["id"] = cell_id
            mapping[handle] = cell_id
    if mapping and int(raw.get("nbformat_minor", 0)) < 5:
        raw["nbformat_minor"] = 5
    return mapping


def _legacy_cell_id(handle: str, existing_ids: set[str]) -> str:
    for attempt in range(100):
        digest = hashlib.sha256(f"{handle}:{attempt}".encode("utf-8")).hexdigest()[:16]
        candidate = f"cell_{digest}"
        if candidate not in existing_ids:
            return candidate
    raise NotebookToolError(
        "INVALID_OPERATION",
        "Could not derive a unique persisted id for a legacy cell.",
        "Retry after assigning unique cell ids with a current Jupyter client.",
    )


def compact_preview(cell: dict[str, Any], limit: int = 120) -> str:
    text = source_text(cell.get("source", ""))
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    if not lines:
        preview = f"<empty {cell.get('cell_type', 'unknown')} cell>"
    elif cell.get("cell_type") == "markdown":
        preview = next((line for line in lines if line.startswith("#")), lines[0])
    else:
        preview = lines[0]
    return preview if len(preview) <= limit else f"{preview[: limit - 1]}…"


def bounded_source(cell: dict[str, Any], max_lines: int = 80) -> tuple[str, bool]:
    text = source_text(cell.get("source", ""))
    lines = text.splitlines(keepends=True)
    selected = lines[:max_lines]
    preview = "".join(selected)
    char_truncated = len(preview) > 12_000
    if char_truncated:
        preview = preview[:12_000]
    return preview, len(lines) > max_lines or char_truncated


def summarize_outputs(
    outputs: Any,
    *,
    max_items: int = 5,
    max_chars: int = 2_000,
) -> list[dict[str, Any]]:
    if not isinstance(outputs, list):
        return []
    summaries: list[dict[str, Any]] = []
    remaining = max_chars
    for output in outputs[:max_items]:
        if not isinstance(output, dict):
            continue
        summary: dict[str, Any] = {"output_type": output.get("output_type", "unknown")}
        text: str | None = None
        if output.get("output_type") == "stream":
            summary["name"] = output.get("name")
            text = source_text(output.get("text", ""))
        elif output.get("output_type") == "error":
            summary["ename"] = output.get("ename")
            summary["evalue"] = output.get("evalue")
            traceback = output.get("traceback")
            text = "\n".join(traceback) if isinstance(traceback, list) else None
        else:
            data = output.get("data")
            if isinstance(data, dict):
                text_plain = data.get("text/plain")
                if isinstance(text_plain, (str, list)):
                    text = source_text(text_plain)
                rich: list[dict[str, Any]] = []
                for mime, value in data.items():
                    if mime == "text/plain":
                        continue
                    rich.append(
                        {"mime_type": mime, "byte_size": _mime_byte_size(mime, value)}
                    )
                if rich:
                    summary["rich"] = rich
        if text is not None and remaining > 0:
            visible = text[:remaining]
            summary["text"] = visible
            summary["truncated"] = len(text) > len(visible)
            remaining -= len(visible)
        summaries.append(summary)
    if len(outputs) > max_items:
        summaries.append({"omitted_items": len(outputs) - max_items})
    return summaries


def _mime_byte_size(mime_type: str, value: Any) -> int:
    if (
        mime_type.startswith("image/")
        and mime_type != "image/svg+xml"
        and isinstance(value, str)
    ):
        try:
            return len(base64.b64decode(value, validate=True))
        except (binascii.Error, ValueError):
            pass
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
