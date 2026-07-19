"""Filesystem boundary, revisions, locks, and durable atomic writes."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import threading
from pathlib import Path

from .errors import NotebookToolError


def revision_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PathPolicy:
    """Resolve notebook paths beneath an explicit set of trusted roots."""

    def __init__(self, roots: list[str | Path]) -> None:
        if not roots:
            raise ValueError("At least one --root is required.")
        resolved: list[Path] = []
        for raw in roots:
            root = Path(raw).expanduser()
            if not root.is_absolute():
                raise ValueError(f"Allowed root must be absolute: {raw}")
            try:
                root = root.resolve(strict=True)
            except FileNotFoundError as exc:
                raise ValueError(f"Allowed root does not exist: {raw}") from exc
            if not root.is_dir():
                raise ValueError(f"Allowed root is not a directory: {raw}")
            if root not in resolved:
                resolved.append(root)
        self.roots = tuple(resolved)

    def resolve(self, raw_path: str, *, for_create: bool = False) -> Path:
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            raise NotebookToolError(
                "INVALID_PATH",
                f"Notebook path must be absolute: {raw_path}",
                "Resolve the path against the Codex workspace and retry with an absolute .ipynb path.",
            )
        if path.suffix.lower() != ".ipynb":
            raise NotebookToolError(
                "INVALID_PATH",
                f"Notebook path must end in .ipynb: {raw_path}",
                "Choose a Jupyter notebook path ending in .ipynb.",
            )

        if for_create:
            try:
                parent = path.parent.resolve(strict=True)
            except FileNotFoundError as exc:
                raise NotebookToolError(
                    "INVALID_PATH",
                    f"Notebook parent directory does not exist: {path.parent}",
                    "Create or choose an existing parent directory under an allowed root.",
                ) from exc
            candidate = parent / path.name
        else:
            try:
                candidate = path.resolve(strict=True)
            except FileNotFoundError as exc:
                raise NotebookToolError(
                    "NOTEBOOK_NOT_FOUND",
                    f"Notebook not found: {path}",
                    "Check the absolute path or create the notebook first.",
                ) from exc

        if not any(candidate.is_relative_to(root) for root in self.roots):
            raise NotebookToolError(
                "OUTSIDE_ALLOWED_ROOT",
                f"Notebook path is outside configured roots: {candidate}",
                "Use a notebook beneath an allowed root or add its project root to the MCP server configuration.",
                {"allowed_roots": [str(root) for root in self.roots]},
            )
        return candidate


class PathLocks:
    """Process-local locks covering each notebook's full read-modify-write window."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[Path, threading.RLock] = {}

    def for_path(self, path: Path) -> threading.RLock:
        with self._guard:
            return self._locks.setdefault(path, threading.RLock())


def read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise NotebookToolError(
            "NOTEBOOK_NOT_FOUND",
            f"Notebook not found: {path}",
            "Read the notebook again using its current absolute path.",
        ) from exc
    except OSError as exc:
        raise NotebookToolError(
            "FILE_IO_ERROR",
            f"Could not read notebook {path}: {exc}",
            "Check file permissions and retry.",
        ) from exc


def atomic_create(path: Path, data: bytes, mode: int = 0o644) -> None:
    """Create `path` from a durable sibling temp file without overwriting."""

    temp_path = _write_temp(path, data, mode)
    try:
        try:
            os.link(temp_path, path)
        except FileExistsError as exc:
            raise NotebookToolError(
                "NOTEBOOK_ALREADY_EXISTS",
                f"Notebook already exists: {path}",
                "Use notebook_edit for an existing notebook or choose a new path.",
            ) from exc
        except OSError as exc:
            raise NotebookToolError(
                "FILE_IO_ERROR",
                f"Could not create notebook {path}: {exc}",
                "Check destination permissions and free space, then retry.",
            ) from exc
        _fsync_directory(path.parent)
    finally:
        _safe_unlink(temp_path)


def atomic_replace(path: Path, data: bytes, expected_revision: str) -> None:
    """Replace a notebook iff its exact bytes still match `expected_revision`."""

    current = read_bytes(path)
    actual_revision = revision_of(current)
    if actual_revision != expected_revision:
        raise NotebookToolError(
            "STALE_REVISION",
            f"Notebook changed since it was read: {path}",
            "Call notebook_read again, reconcile the latest cells, and retry with its revision.",
            {
                "expected_revision": expected_revision,
                "current_revision": actual_revision,
            },
        )

    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        mode = 0o644
    temp_path = _write_temp(path, data, mode)
    replaced = False
    try:
        os.replace(temp_path, path)
        replaced = True
        _fsync_directory(path.parent)
    except OSError as exc:
        raise NotebookToolError(
            "FILE_IO_ERROR",
            f"Could not atomically replace notebook {path}: {exc}",
            "Check destination permissions and free space; the original notebook was left intact when replacement failed.",
        ) from exc
    finally:
        if not replaced:
            _safe_unlink(temp_path)


def _write_temp(path: Path, data: bytes, mode: int) -> Path:
    fd, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        _safe_unlink(temp_path)
        raise
    return temp_path


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(directory, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
