"""Workflow-level notebook operations independent of MCP transport and harness."""

from __future__ import annotations

import copy
import subprocess
import time
from pathlib import Path
from typing import Any, Literal

import nbformat
from jupyter_client.kernelspec import NoSuchKernel
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError, CellTimeoutError

from .contracts import CellInput, EditOperation
from .document import (
    NotebookDocument,
    assign_missing_ids,
    bounded_source,
    compact_preview,
    load_document,
    new_cell,
    serialize_notebook,
    source_sha256,
    source_text,
    summarize_outputs,
    validate_notebook,
)
from .errors import NotebookToolError, invalid_operation
from .filesystem import (
    PathLocks,
    PathPolicy,
    atomic_create,
    atomic_replace,
    read_bytes,
    revision_of,
)


class NotebookService:
    def __init__(self, roots: list[str | Path]) -> None:
        self.paths = PathPolicy(roots)
        self.locks = PathLocks()

    def read(
        self,
        *,
        path: str,
        mode: Literal["outline", "cells"] = "outline",
        cell_ids: list[str] | None = None,
        query: str | None = None,
        offset: int = 0,
        limit: int = 50,
        include_outputs: bool = False,
        max_source_lines: int = 80,
        max_output_items: int = 5,
        max_output_chars: int = 2_000,
    ) -> dict[str, Any]:
        notebook_path = self.paths.resolve(path)
        document = self._load(notebook_path)
        if cell_ids and query:
            raise invalid_operation(
                "cell_ids and query are mutually exclusive.",
                "Choose exact cell ids or one source query, then retry.",
            )
        if offset < 0 or not 1 <= limit <= 100:
            raise invalid_operation(
                "offset must be non-negative and limit must be between 1 and 100.",
                "Use offset >= 0 and 1 <= limit <= 100.",
            )
        if not 1 <= max_source_lines <= 80:
            raise invalid_operation(
                "max_source_lines must be between 1 and 80.",
                "Use a source-line budget from 1 to 80.",
            )
        if not 0 <= max_output_items <= 5 or not 0 <= max_output_chars <= 2_000:
            raise invalid_operation(
                "Output budgets exceed the server limits.",
                "Use 0 to 5 output items and 0 to 2000 output characters per cell.",
            )

        indexed = list(enumerate(document.raw["cells"]))
        if cell_ids:
            indexed = [
                (
                    document.index_for(handle),
                    document.raw["cells"][document.index_for(handle)],
                )
                for handle in cell_ids
            ]
        elif query is not None:
            needle = query.casefold()
            indexed = [
                (index, cell)
                for index, cell in indexed
                if needle in source_text(cell.get("source", "")).casefold()
            ]

        page = indexed[offset : offset + limit]
        cells = [
            self._present_cell(
                document,
                index,
                cell,
                include_source=mode == "cells",
                include_outputs=include_outputs,
                max_source_lines=max_source_lines,
                max_output_items=max_output_items,
                max_output_chars=max_output_chars,
            )
            for index, cell in page
        ]
        next_offset = offset + len(page) if offset + len(page) < len(indexed) else None
        metadata = document.raw.get("metadata")
        kernel = metadata.get("kernelspec") if isinstance(metadata, dict) else None
        return {
            "path": str(notebook_path),
            "revision": document.revision,
            "valid": True,
            "nbformat": document.raw.get("nbformat"),
            "nbformat_minor": document.raw.get("nbformat_minor"),
            "kernel": copy.deepcopy(kernel) if isinstance(kernel, dict) else None,
            "cell_count": len(document.raw["cells"]),
            "matched_count": len(indexed),
            "offset": offset,
            "next_offset": next_offset,
            "warnings": document.warnings,
            "cells": cells,
        }

    def create(
        self,
        *,
        path: str,
        cells: list[CellInput],
        kernel_name: str = "python3",
        kernel_display_name: str = "Python 3",
        language: str = "python",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not cells:
            raise invalid_operation(
                "notebook_create requires at least one cell.",
                "Provide one or more structured markdown, code, or raw cells.",
            )
        notebook_path = self.paths.resolve(path, for_create=True)
        with self.locks.for_path(notebook_path):
            if notebook_path.exists():
                raise NotebookToolError(
                    "NOTEBOOK_ALREADY_EXISTS",
                    f"Notebook already exists: {notebook_path}",
                    "Use notebook_edit for an existing notebook or choose a new path.",
                )
            raw: dict[str, Any] = {
                "cells": [],
                "metadata": copy.deepcopy(metadata or {}),
                "nbformat": 4,
                "nbformat_minor": 5,
            }
            raw["metadata"].setdefault(
                "kernelspec",
                {
                    "display_name": kernel_display_name,
                    "language": language,
                    "name": kernel_name,
                },
            )
            raw["metadata"].setdefault("language_info", {"name": language})
            for cell_input in cells:
                existing = {cell["id"] for cell in raw["cells"]}
                raw["cells"].append(new_cell(cell_input, existing))
            validate_notebook(raw)
            serialized = serialize_notebook(raw)
            atomic_create(notebook_path, serialized)
            verified = self._load(notebook_path)
            return {
                "path": str(notebook_path),
                "revision": verified.revision,
                "valid": True,
                "cell_count": len(raw["cells"]),
                "cell_ids": [cell["id"] for cell in raw["cells"]],
                "kernel": copy.deepcopy(raw["metadata"]["kernelspec"]),
            }

    def edit(
        self,
        *,
        path: str,
        expected_revision: str,
        operations: list[EditOperation],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if not operations:
            raise invalid_operation(
                "notebook_edit requires at least one operation.",
                "Provide one or more ordered edit operations.",
            )
        notebook_path = self.paths.resolve(path)
        with self.locks.for_path(notebook_path):
            document = self._load(notebook_path)
            self._assert_revision(document, expected_revision)
            candidate = copy.deepcopy(document.raw)
            legacy_mapping = assign_missing_ids(candidate, document)
            changes: list[dict[str, Any]] = []
            for operation in operations:
                changes.append(
                    self._apply_operation(candidate, operation, legacy_mapping)
                )
            validation_warnings = validate_notebook(candidate)
            serialized = serialize_notebook(candidate)
            proposed_revision = revision_of(serialized)
            result = {
                "path": str(notebook_path),
                "dry_run": dry_run,
                "previous_revision": document.revision,
                "revision": document.revision if dry_run else proposed_revision,
                "proposed_revision": proposed_revision,
                "operation_count": len(operations),
                "cell_count": len(candidate["cells"]),
                "changes": changes,
                "legacy_id_mapping": legacy_mapping,
                "warnings": validation_warnings,
                "valid": True,
            }
            if dry_run:
                return result
            atomic_replace(notebook_path, serialized, expected_revision)
            verified = self._load(notebook_path)
            if verified.revision != proposed_revision:
                raise NotebookToolError(
                    "FILE_IO_ERROR",
                    "Notebook revision after save did not match the validated candidate.",
                    "Read the notebook again before attempting another mutation.",
                )
            result["revision"] = verified.revision
            return result

    async def execute(
        self,
        *,
        path: str,
        stop_after_cell_id: str | None = None,
        kernel_name: str | None = None,
        timeout_seconds: int = 120,
        allow_errors: bool = False,
        write_back: bool = False,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        if timeout_seconds < 1 or timeout_seconds > 1_800:
            raise invalid_operation(
                "timeout_seconds must be between 1 and 1800.",
                "Choose a per-cell timeout from 1 to 1800 seconds.",
            )
        notebook_path = self.paths.resolve(path)
        lock = self.locks.for_path(notebook_path)
        with lock:
            document = self._load(notebook_path)
            if write_back:
                if expected_revision is None:
                    raise invalid_operation(
                        "expected_revision is required when write_back=true.",
                        "Call notebook_read and retry with its revision.",
                    )
                self._assert_revision(document, expected_revision)
            candidate = copy.deepcopy(document.raw)
            legacy_mapping = (
                assign_missing_ids(candidate, document) if write_back else {}
            )

        stop_index = (
            document.index_for(stop_after_cell_id)
            if stop_after_cell_id is not None
            else None
        )

        execution_candidate = copy.deepcopy(candidate)
        for cell in execution_candidate["cells"]:
            cell["source"] = source_text(cell.get("source", ""))
        notebook_node = nbformat.from_dict(execution_candidate)
        metadata = candidate.get("metadata", {})
        kernelspec = (
            metadata.get("kernelspec", {}) if isinstance(metadata, dict) else {}
        )
        selected_kernel = kernel_name or (
            kernelspec.get("name") if isinstance(kernelspec, dict) else None
        )
        if not selected_kernel:
            raise NotebookToolError(
                "KERNEL_NOT_FOUND",
                "Notebook has no kernelspec and no kernel_name override was provided.",
                "Pass kernel_name explicitly or add notebook kernelspec metadata.",
            )

        client = NotebookClient(
            notebook_node,
            timeout=timeout_seconds,
            kernel_name=selected_kernel,
            allow_errors=allow_errors,
            resources={"metadata": {"path": str(notebook_path.parent)}},
        )
        executions: list[dict[str, Any]] = []
        first_error: dict[str, Any] | None = None
        try:
            async with client.async_setup_kernel(
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ):
                for index, cell in enumerate(notebook_node.cells):
                    if cell.get("cell_type") == "code":
                        started = time.monotonic()
                        try:
                            await client.async_execute_cell(cell, index)
                        except CellTimeoutError as exc:
                            raise NotebookToolError(
                                "EXECUTION_TIMEOUT",
                                f"Cell {cell.get('id', index)} exceeded {timeout_seconds} seconds.",
                                "Increase timeout_seconds or make the cell bounded, then rerun from a clean kernel.",
                                {"cell_id": cell.get("id"), "index": index},
                            ) from exc
                        except CellExecutionError as exc:
                            details = self._first_cell_error(cell, index)
                            raise NotebookToolError(
                                "CELL_EXECUTION_ERROR",
                                f"Cell {cell.get('id', index)} failed during clean-kernel execution.",
                                "Inspect the returned error, fix the cell or its dependencies, and rerun from the beginning.",
                                details,
                            ) from exc
                        duration_ms = round((time.monotonic() - started) * 1000)
                        cell_error = self._first_cell_error(cell, index)
                        if cell_error and first_error is None:
                            first_error = cell_error
                        executions.append(
                            {
                                "cell_id": cell.get("id"),
                                "index": index,
                                "duration_ms": duration_ms,
                                "status": "error" if cell_error else "ok",
                                "outputs": summarize_outputs(cell.get("outputs", [])),
                            }
                        )
                    if stop_index is not None and index >= stop_index:
                        break
        except NoSuchKernel as exc:
            raise NotebookToolError(
                "KERNEL_NOT_FOUND",
                f"Jupyter kernel is not installed: {selected_kernel}",
                "Install the kernel or retry with an installed kernel_name.",
            ) from exc

        result: dict[str, Any] = {
            "path": str(notebook_path),
            "kernel_name": selected_kernel,
            "write_back": write_back,
            "previous_revision": document.revision,
            "revision": document.revision,
            "executed_code_cells": len(executions),
            "stopped_after_cell_id": stop_after_cell_id,
            "executions": executions,
            "first_error": first_error,
            "legacy_id_mapping": legacy_mapping,
        }
        if write_back:
            executed_raw = copy.deepcopy(dict(notebook_node))
            for index, cell in enumerate(executed_raw["cells"]):
                cell["source"] = copy.deepcopy(candidate["cells"][index]["source"])
            validate_notebook(executed_raw)
            serialized = serialize_notebook(executed_raw)
            proposed_revision = revision_of(serialized)
            with lock:
                atomic_replace(notebook_path, serialized, expected_revision or "")
                verified = self._load(notebook_path)
            result["revision"] = verified.revision
            result["valid"] = True
            if verified.revision != proposed_revision:
                raise NotebookToolError(
                    "FILE_IO_ERROR",
                    "Notebook revision after execution write-back was not the validated candidate.",
                    "Read the notebook again before retrying.",
                )
        return result

    def _load(self, path: Path) -> NotebookDocument:
        return load_document(path, read_bytes(path))

    @staticmethod
    def _assert_revision(document: NotebookDocument, expected: str) -> None:
        if document.revision != expected:
            raise NotebookToolError(
                "STALE_REVISION",
                f"Notebook changed since it was read: {document.path}",
                "Call notebook_read again, reconcile the current cells, and retry with its revision.",
                {"expected_revision": expected, "current_revision": document.revision},
            )

    @staticmethod
    def _present_cell(
        document: NotebookDocument,
        index: int,
        cell: dict[str, Any],
        *,
        include_source: bool,
        include_outputs: bool,
        max_source_lines: int,
        max_output_items: int,
        max_output_chars: int,
    ) -> dict[str, Any]:
        handle, persisted = document.handle_for(index)
        result: dict[str, Any] = {
            "index": index,
            "id": handle,
            "id_persisted": persisted,
            "cell_type": cell.get("cell_type"),
            "preview": compact_preview(cell),
            "source_sha256": source_sha256(cell),
            "source_line_count": len(source_text(cell.get("source", "")).splitlines()),
            "execution_count": cell.get("execution_count")
            if cell.get("cell_type") == "code"
            else None,
            "output_count": len(cell.get("outputs", []))
            if isinstance(cell.get("outputs"), list)
            else 0,
        }
        if include_source:
            source, truncated = bounded_source(cell, max_source_lines)
            result["source"] = source
            result["source_truncated"] = truncated
        if include_outputs and cell.get("cell_type") == "code":
            result["outputs"] = summarize_outputs(
                cell.get("outputs", []),
                max_items=max_output_items,
                max_chars=max_output_chars,
            )
        return result

    def _apply_operation(
        self,
        raw: dict[str, Any],
        operation: EditOperation,
        legacy_mapping: dict[str, str],
    ) -> dict[str, Any]:
        cells: list[dict[str, Any]] = raw["cells"]
        op = operation.op
        if op == "clear_outputs":
            target = (
                legacy_mapping.get(operation.cell_id, operation.cell_id)
                if operation.cell_id
                else None
            )
            affected = 0
            removed = 0
            for cell in cells:
                if target is not None and cell.get("id") != target:
                    continue
                if cell.get("cell_type") != "code":
                    if target is not None:
                        raise invalid_operation(
                            f"clear_outputs target is not a code cell: {target}",
                            "Choose a code cell id or omit cell_id to clear every code cell.",
                        )
                    continue
                outputs = cell.get("outputs", [])
                removed += len(outputs) if isinstance(outputs, list) else 0
                cell["outputs"] = []
                cell["execution_count"] = None
                affected += 1
            if target is not None and not any(
                cell.get("id") == target for cell in cells
            ):
                self._missing_cell(target)
            return {
                "op": op,
                "cell_id": target,
                "affected_cells": affected,
                "removed_outputs": removed,
            }

        target_handle = getattr(operation, "cell_id")
        target = legacy_mapping.get(target_handle, target_handle)
        index = self._find_cell_index(raw, target)
        cell = cells[index]

        if op == "replace":
            next_type = operation.cell_type or cell.get("cell_type")
            if next_type == cell.get("cell_type"):
                replacement = copy.deepcopy(cell)
                replacement["source"] = (
                    copy.deepcopy(operation.source)
                    if isinstance(operation.source, list)
                    else operation.source.splitlines(keepends=True)
                )
            else:
                replacement = {
                    "cell_type": next_type,
                    "id": target,
                    "metadata": copy.deepcopy(cell.get("metadata", {})),
                    "source": (
                        copy.deepcopy(operation.source)
                        if isinstance(operation.source, list)
                        else operation.source.splitlines(keepends=True)
                    ),
                }
                standard_fields = {
                    "cell_type",
                    "id",
                    "metadata",
                    "source",
                    "attachments",
                    "execution_count",
                    "outputs",
                }
                for key, value in cell.items():
                    if key not in standard_fields:
                        replacement[key] = copy.deepcopy(value)
            if next_type == "code":
                replacement["execution_count"] = None
                replacement["outputs"] = []
            cells[index] = replacement
            return {
                "op": op,
                "cell_id": target,
                "index": index,
                "cell_type": next_type,
                "outputs_cleared": next_type == "code",
            }

        if op in {"insert_before", "insert_after"}:
            existing = {item["id"] for item in cells if isinstance(item.get("id"), str)}
            inserted = new_cell(operation.new_cell, existing)
            insert_index = index if op == "insert_before" else index + 1
            cells.insert(insert_index, inserted)
            return {
                "op": op,
                "anchor_id": target,
                "cell_id": inserted["id"],
                "index": insert_index,
                "cell_type": inserted["cell_type"],
            }

        if op == "delete":
            deleted = cells.pop(index)
            return {
                "op": op,
                "cell_id": target,
                "index": index,
                "cell_type": deleted.get("cell_type"),
            }

        if op in {"move_before", "move_after"}:
            anchor_handle = operation.anchor_id
            anchor = legacy_mapping.get(anchor_handle, anchor_handle)
            if anchor == target:
                raise invalid_operation(
                    "A cell cannot be moved relative to itself.",
                    "Choose a different anchor_id.",
                )
            moving = cells.pop(index)
            anchor_index = self._find_cell_index(raw, anchor)
            insert_index = anchor_index if op == "move_before" else anchor_index + 1
            cells.insert(insert_index, moving)
            return {
                "op": op,
                "cell_id": target,
                "anchor_id": anchor,
                "index": insert_index,
            }

        raise invalid_operation(
            f"Unsupported notebook edit operation: {op}",
            "Use replace, insert_before, insert_after, delete, move_before, move_after, or clear_outputs.",
        )

    @staticmethod
    def _find_cell_index(raw: dict[str, Any], cell_id: str) -> int:
        for index, cell in enumerate(raw["cells"]):
            if cell.get("id") == cell_id:
                return index
        NotebookService._missing_cell(cell_id)
        raise AssertionError("unreachable")

    @staticmethod
    def _missing_cell(cell_id: str) -> None:
        raise NotebookToolError(
            "CELL_NOT_FOUND",
            f"Cell id not found: {cell_id}",
            "Call notebook_read again and use a cell id from the current revision.",
        )

    @staticmethod
    def _first_cell_error(cell: Any, index: int) -> dict[str, Any] | None:
        outputs = cell.get("outputs", [])
        for output in outputs if isinstance(outputs, list) else []:
            if isinstance(output, dict) and output.get("output_type") == "error":
                return {
                    "cell_id": cell.get("id"),
                    "index": index,
                    "ename": output.get("ename"),
                    "evalue": output.get("evalue"),
                }
        return None
