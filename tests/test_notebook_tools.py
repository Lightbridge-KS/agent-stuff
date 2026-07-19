#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "ipykernel>=6.29,<8",
#   "mcp[cli]>=1.28,<2",
#   "nbclient>=0.11,<1",
#   "nbformat>=5.10,<6",
#   "pydantic>=2.12,<3",
# ]
# ///
"""Behavioral contract tests for scripts/notebook-tools."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_ROOT = REPO_ROOT / "scripts" / "notebook-tools"
sys.path.insert(0, str(TOOL_ROOT))

from notebook_tools.contracts import (  # noqa: E402
    CellInput,
    ClearOutputsOperation,
    DeleteOperation,
    InsertAfterOperation,
    MoveBeforeOperation,
    ReplaceOperation,
)
from notebook_tools.errors import NotebookToolError  # noqa: E402
from notebook_tools.filesystem import atomic_replace, revision_of  # noqa: E402
from notebook_tools.server import SERVER_INSTRUCTIONS, create_server  # noqa: E402
from notebook_tools.service import NotebookService  # noqa: E402


class NotebookCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.service = NotebookService([self.root])
        self.addCleanup(self.tmp.cleanup)

    def create(self, name: str = "sample.ipynb") -> tuple[Path, dict]:
        path = self.root / name
        result = self.service.create(
            path=str(path),
            cells=[
                CellInput(cell_type="markdown", source="# Synthetic notebook\n"),
                CellInput(cell_type="code", source="value = 40 + 2\nprint(value)\n"),
            ],
        )
        return path, result

    def test_create_read_search_and_output_budgets(self) -> None:
        path, created = self.create()
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["cells"][1]["outputs"] = [
            {"output_type": "stream", "name": "stdout", "text": "x" * 80},
            {
                "output_type": "display_data",
                "metadata": {},
                "data": {"image/png": "aGVsbG8=", "text/plain": "figure"},
            },
        ]
        path.write_text(json.dumps(raw), encoding="utf-8")

        read = self.service.read(
            path=str(path),
            mode="cells",
            query="value =",
            include_outputs=True,
            max_output_chars=12,
        )
        self.assertEqual(read["matched_count"], 1)
        self.assertEqual(read["cells"][0]["outputs"][0]["text"], "x" * 12)
        rich = read["cells"][0]["outputs"][1]["rich"][0]
        self.assertEqual(rich, {"mime_type": "image/png", "byte_size": 5})
        self.assertNotEqual(read["revision"], created["revision"])
        self.assertIsNone(read["next_offset"])
        with self.assertRaises(NotebookToolError) as caught:
            self.service.read(path=str(path), max_output_chars=2_001)
        self.assertEqual(caught.exception.code, "INVALID_OPERATION")

    def test_ordered_dry_run_commit_and_stale_guard(self) -> None:
        path, _ = self.create()
        before = self.service.read(path=str(path), mode="cells")
        markdown_id, code_id = [cell["id"] for cell in before["cells"]]
        operations = [
            ReplaceOperation(op="replace", cell_id=code_id, source="value = 43\n"),
            InsertAfterOperation(
                op="insert_after",
                cell_id=markdown_id,
                new_cell=CellInput(cell_type="markdown", source="A second note"),
            ),
            MoveBeforeOperation(
                op="move_before",
                cell_id=code_id,
                anchor_id=markdown_id,
            ),
        ]
        original = path.read_bytes()
        preview = self.service.edit(
            path=str(path),
            expected_revision=before["revision"],
            operations=operations,
            dry_run=True,
        )
        self.assertEqual(path.read_bytes(), original)
        self.assertNotEqual(preview["proposed_revision"], before["revision"])

        committed = self.service.edit(
            path=str(path),
            expected_revision=before["revision"],
            operations=operations,
        )
        after = self.service.read(path=str(path), mode="cells", include_outputs=True)
        self.assertEqual(after["revision"], committed["revision"])
        self.assertEqual(after["cells"][0]["id"], code_id)
        self.assertEqual(after["cells"][0]["execution_count"], None)
        self.assertEqual(after["cells"][0]["output_count"], 0)
        with self.assertRaises(NotebookToolError) as caught:
            self.service.edit(
                path=str(path),
                expected_revision=before["revision"],
                operations=[DeleteOperation(op="delete", cell_id=markdown_id)],
            )
        self.assertEqual(caught.exception.code, "STALE_REVISION")

    def test_invalid_mid_batch_rolls_back(self) -> None:
        path, _ = self.create()
        before = self.service.read(path=str(path), mode="cells")
        original = path.read_bytes()
        with self.assertRaises(NotebookToolError) as caught:
            self.service.edit(
                path=str(path),
                expected_revision=before["revision"],
                operations=[
                    DeleteOperation(op="delete", cell_id=before["cells"][0]["id"]),
                    DeleteOperation(op="delete", cell_id="missing"),
                ],
            )
        self.assertEqual(caught.exception.code, "CELL_NOT_FOUND")
        self.assertEqual(path.read_bytes(), original)

    def test_legacy_handles_persist_and_unknown_fields_survive(self) -> None:
        path = self.root / "legacy.ipynb"
        raw = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "metadata": {"custom": True},
                    "source": ["old"],
                    "attachments": {"x.txt": {"text/plain": "kept"}},
                    "vendor_extension": {"kept": True},
                }
            ],
            "metadata": {"vendor": {"kept": True}},
            "nbformat": 4,
            "nbformat_minor": 4,
        }
        path.write_text(json.dumps(raw), encoding="utf-8")
        before = self.service.read(path=str(path), mode="cells")
        legacy = before["cells"][0]
        self.assertFalse(legacy["id_persisted"])

        preview = self.service.edit(
            path=str(path),
            expected_revision=before["revision"],
            operations=[
                ReplaceOperation(op="replace", cell_id=legacy["id"], source="new")
            ],
            dry_run=True,
        )

        result = self.service.edit(
            path=str(path),
            expected_revision=before["revision"],
            operations=[
                ReplaceOperation(op="replace", cell_id=legacy["id"], source="new")
            ],
        )
        persisted = result["legacy_id_mapping"][legacy["id"]]
        self.assertEqual(preview["legacy_id_mapping"][legacy["id"]], persisted)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["cells"][0]["id"], persisted)
        self.assertEqual(
            saved["cells"][0]["attachments"]["x.txt"], {"text/plain": "kept"}
        )
        self.assertEqual(saved["cells"][0]["vendor_extension"], {"kept": True})
        self.assertEqual(saved["metadata"]["vendor"], {"kept": True})

    def test_clear_outputs_and_type_conversion(self) -> None:
        path, _ = self.create()
        before = self.service.read(path=str(path), mode="cells")
        code_id = before["cells"][1]["id"]
        result = self.service.edit(
            path=str(path),
            expected_revision=before["revision"],
            operations=[ClearOutputsOperation(op="clear_outputs")],
        )
        converted = self.service.edit(
            path=str(path),
            expected_revision=result["revision"],
            operations=[
                ReplaceOperation(
                    op="replace",
                    cell_id=code_id,
                    cell_type="raw",
                    source="raw content",
                )
            ],
        )
        saved = json.loads(path.read_text(encoding="utf-8"))
        raw_cell = next(cell for cell in saved["cells"] if cell["id"] == code_id)
        self.assertEqual(raw_cell["cell_type"], "raw")
        self.assertNotIn("outputs", raw_cell)
        self.assertEqual(converted["cell_count"], 2)

    def test_invalid_notebooks_are_taught_as_stable_errors(self) -> None:
        malformed = self.root / "malformed.ipynb"
        malformed.write_text("{", encoding="utf-8")
        with self.assertRaises(NotebookToolError) as caught:
            self.service.read(path=str(malformed))
        self.assertEqual(caught.exception.code, "INVALID_NOTEBOOK")

        version3 = self.root / "old.ipynb"
        version3.write_text(
            json.dumps({"nbformat": 3, "worksheets": []}), encoding="utf-8"
        )
        with self.assertRaises(NotebookToolError) as caught:
            self.service.read(path=str(version3))
        self.assertEqual(caught.exception.code, "UNSUPPORTED_NBFORMAT")

        duplicate = self.root / "duplicate.ipynb"
        raw = {
            "cells": [
                {"cell_type": "raw", "id": "same", "metadata": {}, "source": []},
                {"cell_type": "raw", "id": "same", "metadata": {}, "source": []},
            ],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        duplicate.write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaises(NotebookToolError) as caught:
            self.service.read(path=str(duplicate))
        self.assertEqual(caught.exception.code, "INVALID_NOTEBOOK")

    def test_root_policy_blocks_relative_outside_and_symlink_escape(self) -> None:
        with self.assertRaises(NotebookToolError) as caught:
            self.service.read(path="relative.ipynb")
        self.assertEqual(caught.exception.code, "INVALID_PATH")

        with tempfile.TemporaryDirectory() as external_dir:
            external = Path(external_dir) / "outside.ipynb"
            external.write_text("{}", encoding="utf-8")
            with self.assertRaises(NotebookToolError) as caught:
                self.service.read(path=str(external))
            self.assertEqual(caught.exception.code, "OUTSIDE_ALLOWED_ROOT")
            link = self.root / "escape.ipynb"
            link.symlink_to(external)
            with self.assertRaises(NotebookToolError) as caught:
                self.service.read(path=str(link))
            self.assertEqual(caught.exception.code, "OUTSIDE_ALLOWED_ROOT")

    def test_atomic_replace_failure_keeps_original_and_cleans_temp(self) -> None:
        path, _ = self.create()
        original = path.read_bytes()
        with mock.patch(
            "notebook_tools.filesystem.os.replace", side_effect=OSError("denied")
        ):
            with self.assertRaises(NotebookToolError) as caught:
                atomic_replace(path, b"replacement", revision_of(original))
        self.assertEqual(caught.exception.code, "FILE_IO_ERROR")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(self.root.glob(f".{path.name}.tmp-*")), [])

    def test_external_change_at_commit_fails_without_overwrite(self) -> None:
        path, _ = self.create()
        before = self.service.read(path=str(path), mode="cells")
        external = b"externally changed"
        real_replace = atomic_replace

        def race(target: Path, data: bytes, expected_revision: str) -> None:
            target.write_bytes(external)
            real_replace(target, data, expected_revision)

        with mock.patch("notebook_tools.service.atomic_replace", side_effect=race):
            with self.assertRaises(NotebookToolError) as caught:
                self.service.edit(
                    path=str(path),
                    expected_revision=before["revision"],
                    operations=[
                        ReplaceOperation(
                            op="replace",
                            cell_id=before["cells"][1]["id"],
                            source="changed",
                        )
                    ],
                )
        self.assertEqual(caught.exception.code, "STALE_REVISION")
        self.assertEqual(path.read_bytes(), external)


class McpCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        asyncio.get_running_loop().set_debug(False)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.server = create_server([str(self.root)])

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_discovery_schemas_annotations_instructions_and_error_envelope(
        self,
    ) -> None:
        tools = {tool.name: tool for tool in await self.server.list_tools()}
        self.assertEqual(
            set(tools),
            {"notebook_read", "notebook_create", "notebook_edit", "notebook_execute"},
        )
        self.assertEqual(
            tools["notebook_create"].inputSchema["required"], ["path", "cells"]
        )
        self.assertEqual(
            tools["notebook_edit"].inputSchema["required"],
            ["path", "expected_revision", "operations"],
        )
        self.assertTrue(tools["notebook_read"].annotations.readOnlyHint)
        self.assertFalse(tools["notebook_edit"].annotations.readOnlyHint)
        self.assertTrue(tools["notebook_execute"].annotations.openWorldHint)
        self.assertEqual(
            set(tools["notebook_read"].outputSchema["properties"]),
            {"ok", "data", "error"},
        )
        self.assertIn(
            "Use notebook_read before notebook_edit", SERVER_INSTRUCTIONS[:512]
        )
        self.assertIn(
            "instead of reading or writing raw .ipynb JSON", SERVER_INSTRUCTIONS[:512]
        )

        result = await self.server.call_tool(
            "notebook_read", {"path": str(self.root / "missing.ipynb")}
        )
        self.assertTrue(result.isError)
        self.assertEqual(
            result.structuredContent["error"]["code"], "NOTEBOOK_NOT_FOUND"
        )
        self.assertIn("Next:", result.content[0].text)


class ExecutionCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        asyncio.get_running_loop().set_debug(False)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.service = NotebookService([self.root])

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def make_notebook(self, name: str, sources: list[str]) -> tuple[Path, dict]:
        path = self.root / name
        created = self.service.create(
            path=str(path),
            cells=[CellInput(cell_type="code", source=source) for source in sources],
        )
        return path, created

    async def test_clean_execution_stop_errors_and_guarded_writeback(self) -> None:
        path, _ = self.make_notebook(
            "execute.ipynb",
            ["value = 41", "print(value + 1)", "raise ValueError('synthetic boom')"],
        )
        read = self.service.read(path=str(path), mode="cells")
        original = path.read_bytes()
        through_second = await self.service.execute(
            path=str(path),
            stop_after_cell_id=read["cells"][1]["id"],
        )
        self.assertEqual(through_second["executed_code_cells"], 2)
        self.assertEqual(
            through_second["executions"][1]["outputs"][0]["text"].strip(), "42"
        )
        self.assertEqual(path.read_bytes(), original)

        allowed = await self.service.execute(path=str(path), allow_errors=True)
        self.assertEqual(allowed["first_error"]["ename"], "ValueError")
        self.assertEqual(allowed["executions"][-1]["status"], "error")
        with self.assertRaises(NotebookToolError) as caught:
            await self.service.execute(path=str(path), allow_errors=False)
        self.assertEqual(caught.exception.code, "CELL_EXECUTION_ERROR")

        persisted = await self.service.execute(
            path=str(path),
            stop_after_cell_id=read["cells"][1]["id"],
            write_back=True,
            expected_revision=read["revision"],
        )
        self.assertNotEqual(persisted["revision"], read["revision"])
        verified = self.service.read(path=str(path), mode="cells", include_outputs=True)
        self.assertEqual(verified["cells"][1]["outputs"][0]["text"].strip(), "42")

    async def test_missing_kernel_and_timeout_are_stable(self) -> None:
        path, _ = self.make_notebook("kernel.ipynb", ["import time; time.sleep(3)"])
        with self.assertRaises(NotebookToolError) as caught:
            await self.service.execute(path=str(path), kernel_name="no-such-kernel")
        self.assertEqual(caught.exception.code, "KERNEL_NOT_FOUND")

        with self.assertRaises(NotebookToolError) as caught:
            await self.service.execute(path=str(path), timeout_seconds=1)
        self.assertEqual(caught.exception.code, "EXECUTION_TIMEOUT")


if __name__ == "__main__":
    unittest.main()
