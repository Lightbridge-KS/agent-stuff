"""Thin FastMCP adapter for the packaged notebook domain service."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from .contracts import CellInput, EditOperation, ToolEnvelope
from .errors import NotebookToolError
from .roots import RootAccess, RootResolver, ServiceRegistry


SERVER_INSTRUCTIONS = (
    "Use notebook_read before notebook_edit and pass the returned revision. Prefer stable "
    "cell ids, not indexes. Source edits to code cells clear old outputs. Use these tools "
    "instead of reading or writing raw .ipynb JSON. notebook_execute always starts a clean "
    "kernel and may have arbitrary code side effects even when write_back is false. "
    "Keep reusable logic in src/ and use notebooks for orchestration and narrative."
)

ToolResult = Annotated[CallToolResult, ToolEnvelope]


def create_server(
    roots: list[str] | None = None,
    *,
    use_client_roots: bool = False,
    config_path: Path | None = None,
) -> FastMCP:
    resolver = RootResolver(
        roots,
        use_client_roots=use_client_roots,
        config_path=config_path,
    )
    services = ServiceRegistry()
    mcp = FastMCP("Notebook Tools", instructions=SERVER_INSTRUCTIONS)

    @mcp.tool(
        title="Read Jupyter notebook",
        description=(
            "Read and validate a Jupyter notebook by cell structure instead of raw JSON. "
            "Use before editing to obtain the current revision and stable cell ids."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
        structured_output=True,
    )
    async def notebook_read(
        ctx: Context,
        path: Annotated[
            str,
            Field(description="Absolute .ipynb path beneath a configured root"),
        ],
        mode: Literal["outline", "cells"] = "outline",
        cell_ids: Annotated[list[str] | None, Field(max_length=100)] = None,
        query: str | None = None,
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=100)] = 50,
        include_outputs: bool = False,
        max_source_lines: Annotated[int, Field(ge=1, le=80)] = 80,
        max_output_items: Annotated[int, Field(ge=0, le=5)] = 5,
        max_output_chars: Annotated[int, Field(ge=0, le=2_000)] = 2_000,
    ) -> ToolResult:
        return await _resolved_sync_call(
            resolver,
            services,
            ctx,
            "read",
            path=path,
            mode=mode,
            cell_ids=cell_ids,
            query=query,
            offset=offset,
            limit=limit,
            include_outputs=include_outputs,
            max_source_lines=max_source_lines,
            max_output_items=max_output_items,
            max_output_chars=max_output_chars,
        )

    @mcp.tool(
        title="Create Jupyter notebook",
        description=(
            "Create a new valid Jupyter notebook from structured cells. Refuses to overwrite "
            "an existing notebook and returns generated cell ids plus its initial revision."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
        structured_output=True,
    )
    async def notebook_create(
        ctx: Context,
        path: Annotated[
            str,
            Field(description="Absolute new .ipynb path beneath a configured root"),
        ],
        cells: Annotated[list[CellInput], Field(min_length=1, max_length=200)],
        kernel_name: str = "python3",
        kernel_display_name: str = "Python 3",
        language: str = "python",
        metadata: dict[str, Any] | None = None,
    ) -> ToolResult:
        return await _resolved_sync_call(
            resolver,
            services,
            ctx,
            "create",
            path=path,
            cells=cells,
            kernel_name=kernel_name,
            kernel_display_name=kernel_display_name,
            language=language,
            metadata=metadata,
        )

    @mcp.tool(
        title="Edit Jupyter notebook",
        description=(
            "Atomically apply an ordered batch of cell edits guarded by the exact revision "
            "returned from notebook_read. Supports dry-run, replace, insert, delete, move, "
            "and output clearing."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
        structured_output=True,
    )
    async def notebook_edit(
        ctx: Context,
        path: Annotated[str, Field(description="Absolute existing .ipynb path")],
        expected_revision: Annotated[
            str,
            Field(description="Revision from the latest notebook_read"),
        ],
        operations: Annotated[list[EditOperation], Field(min_length=1, max_length=100)],
        dry_run: bool = False,
    ) -> ToolResult:
        return await _resolved_sync_call(
            resolver,
            services,
            ctx,
            "edit",
            path=path,
            expected_revision=expected_revision,
            operations=operations,
            dry_run=dry_run,
        )

    @mcp.tool(
        title="Execute Jupyter notebook",
        description=(
            "Execute a notebook from the beginning in a fresh Jupyter kernel, optionally "
            "stopping after one cell. Code may have arbitrary side effects even when outputs "
            "are not written back."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=True,
        ),
        structured_output=True,
    )
    async def notebook_execute(
        ctx: Context,
        path: Annotated[str, Field(description="Absolute existing .ipynb path")],
        stop_after_cell_id: str | None = None,
        kernel_name: str | None = None,
        timeout_seconds: Annotated[int, Field(ge=1, le=1_800)] = 120,
        allow_errors: bool = False,
        write_back: bool = False,
        expected_revision: str | None = None,
    ) -> ToolResult:
        try:
            access = await resolver.resolve(ctx)
            service = services.get(access.roots)
            data = await service.execute(
                path=path,
                stop_after_cell_id=stop_after_cell_id,
                kernel_name=kernel_name,
                timeout_seconds=timeout_seconds,
                allow_errors=allow_errors,
                write_back=write_back,
                expected_revision=expected_revision,
            )
            data["access"] = access.metadata()
            return _success(_execution_summary(data), data)
        except NotebookToolError as exc:
            return _error(exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive MCP boundary
            return _error(
                NotebookToolError(
                    "INTERNAL_ERROR",
                    f"Unexpected notebook execution failure: {exc}",
                    "Inspect the server diagnostics and retry after correcting the underlying environment.",
                )
            )

    return mcp


async def _resolved_sync_call(
    resolver: RootResolver,
    services: ServiceRegistry,
    context: Context,
    method_name: str,
    /,
    **kwargs: Any,
) -> CallToolResult:
    try:
        access = await resolver.resolve(context)
        function = getattr(services.get(access.roots), method_name)
        data = await asyncio.to_thread(function, **kwargs)
        _attach_access(data, access)
        return _success(_summary(data), data)
    except NotebookToolError as exc:
        return _error(exc)
    except Exception as exc:  # pragma: no cover - defensive MCP boundary
        return _error(
            NotebookToolError(
                "INTERNAL_ERROR",
                f"Unexpected notebook-tools failure: {exc}",
                "Inspect the server diagnostics and retry after correcting the underlying environment.",
            )
        )


def _attach_access(data: dict[str, Any], access: RootAccess) -> None:
    data["access"] = access.metadata()


def _success(summary: str, data: dict[str, Any]) -> CallToolResult:
    payload = {"ok": True, "data": data, "error": None}
    return CallToolResult(
        content=[TextContent(type="text", text=summary)],
        structuredContent=payload,
    )


def _error(error: NotebookToolError) -> CallToolResult:
    payload = {"ok": False, "data": None, "error": error.as_dict()}
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"{error.code}: {error.message}\nNext: {error.recovery}",
            )
        ],
        structuredContent=payload,
        isError=True,
    )


def _summary(data: dict[str, Any]) -> str:
    if "changes" in data:
        verb = "Previewed" if data.get("dry_run") else "Edited"
        return (
            f"{verb} notebook {data['path']}: {data['operation_count']} operation(s), "
            f"{data['cell_count']} cell(s), revision {data['revision']}."
        )
    if "cell_ids" in data:
        return (
            f"Created notebook {data['path']}: {data['cell_count']} cell(s), "
            f"revision {data['revision']}."
        )
    return (
        f"Read notebook {data['path']}: {data['cell_count']} cell(s), "
        f"returned {len(data['cells'])}, revision {data['revision']}."
    )


def _execution_summary(data: dict[str, Any]) -> str:
    destination = " and wrote outputs back" if data.get("write_back") else " in memory"
    return (
        f"Executed notebook {data['path']}{destination}: "
        f"{data['executed_code_cells']} code cell(s), revision {data['revision']}."
    )
