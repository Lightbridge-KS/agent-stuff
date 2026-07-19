"""Typed public inputs and result envelope for MCP schema generation."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CellType = Literal["markdown", "code", "raw"]
SourceInput = str | list[str]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CellInput(StrictModel):
    cell_type: CellType
    source: SourceInput = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplaceOperation(StrictModel):
    op: Literal["replace"]
    cell_id: str
    source: SourceInput
    cell_type: CellType | None = None


class InsertBeforeOperation(StrictModel):
    op: Literal["insert_before"]
    cell_id: str = Field(description="Anchor cell id")
    new_cell: CellInput


class InsertAfterOperation(StrictModel):
    op: Literal["insert_after"]
    cell_id: str = Field(description="Anchor cell id")
    new_cell: CellInput


class DeleteOperation(StrictModel):
    op: Literal["delete"]
    cell_id: str


class MoveBeforeOperation(StrictModel):
    op: Literal["move_before"]
    cell_id: str = Field(description="Cell to move")
    anchor_id: str


class MoveAfterOperation(StrictModel):
    op: Literal["move_after"]
    cell_id: str = Field(description="Cell to move")
    anchor_id: str


class ClearOutputsOperation(StrictModel):
    op: Literal["clear_outputs"]
    cell_id: str | None = Field(
        default=None,
        description="Code cell id; omit to clear every code cell",
    )


EditOperation = Annotated[
    ReplaceOperation
    | InsertBeforeOperation
    | InsertAfterOperation
    | DeleteOperation
    | MoveBeforeOperation
    | MoveAfterOperation
    | ClearOutputsOperation,
    Field(discriminator="op"),
]


class ErrorPayload(StrictModel):
    code: str
    message: str
    recovery: str
    details: dict[str, Any] | None = None


class ToolEnvelope(StrictModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: ErrorPayload | None = None
