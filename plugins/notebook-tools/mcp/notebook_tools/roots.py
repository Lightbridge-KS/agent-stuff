"""Portable allowed-root resolution for direct and plugin MCP launches."""

from __future__ import annotations

import json
import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from platformdirs import user_config_path

from .errors import NotebookToolError

if TYPE_CHECKING:
    from .service import NotebookService


CONFIG_SCHEMA_VERSION = 1
CONFIG_ENV = "NOTEBOOK_TOOLS_CONFIG"


@dataclass(frozen=True, slots=True)
class RootAccess:
    """The complete allowed-root set selected for one MCP request."""

    roots: tuple[Path, ...]
    source: Literal["static", "client", "config"]

    def metadata(self) -> dict[str, Any]:
        return {"root_source": self.source, "root_count": len(self.roots)}


def default_config_path() -> Path:
    """Return the platform-native roots configuration path."""

    override = os.environ.get(CONFIG_ENV)
    if override:
        return Path(override).expanduser().resolve(strict=False)
    return user_config_path("notebook-tools") / "config.toml"


def canonical_directories(values: list[str | Path]) -> tuple[Path, ...]:
    """Validate, resolve, sort, and deduplicate existing absolute directories."""

    roots: set[Path] = set()
    for raw in values:
        root = Path(raw).expanduser()
        if not root.is_absolute():
            raise ValueError(f"Allowed root must be absolute: {raw}")
        try:
            root = root.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError(f"Allowed root does not exist: {raw}") from exc
        if not root.is_dir():
            raise ValueError(f"Allowed root is not a directory: {raw}")
        roots.add(root)
    return tuple(sorted(roots, key=str))


def read_config_roots(path: Path | None = None) -> tuple[Path, ...]:
    """Read and validate the explicit fallback roots configuration."""

    config_path = path or default_config_path()
    if not config_path.is_file():
        return ()
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise _configuration_error(
            f"Could not read roots config {config_path}: {exc}", config_path
        ) from exc

    if data.get("schema_version") != CONFIG_SCHEMA_VERSION:
        raise _configuration_error(
            f"Roots config {config_path} must set schema_version = {CONFIG_SCHEMA_VERSION}.",
            config_path,
        )
    values = data.get("roots")
    if not isinstance(values, list) or not all(
        isinstance(value, str) for value in values
    ):
        raise _configuration_error(
            f"Roots config {config_path} must contain a string roots array.",
            config_path,
        )
    try:
        return canonical_directories(values)
    except ValueError as exc:
        raise _configuration_error(
            f"Invalid root in {config_path}: {exc}", config_path
        ) from exc


def write_config_roots(roots: tuple[Path, ...], path: Path | None = None) -> Path:
    """Atomically write a deterministic user roots configuration."""

    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"schema_version = {CONFIG_SCHEMA_VERSION}", "roots = ["]
    lines.extend(f"  {json.dumps(str(root), ensure_ascii=False)}," for root in roots)
    lines.append("]")
    payload = ("\n".join(lines) + "\n").encode()

    fd, raw_temp = tempfile.mkstemp(
        prefix=f".{config_path.name}.tmp-", dir=config_path.parent
    )
    temp_path = Path(raw_temp)
    replaced = False
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, config_path)
        replaced = True
        _fsync_directory(config_path.parent)
    finally:
        if not replaced:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
    return config_path


class RootResolver:
    """Select static, MCP-client, or explicit config roots without widening access."""

    def __init__(
        self,
        static_roots: list[str | Path] | None = None,
        *,
        use_client_roots: bool = False,
        config_path: Path | None = None,
    ) -> None:
        if static_roots and use_client_roots:
            raise ValueError("--root and --use-client-roots are mutually exclusive.")
        if not static_roots and not use_client_roots:
            raise ValueError("Provide at least one --root or --use-client-roots.")
        self._static_roots = canonical_directories(static_roots or ())
        self._use_client_roots = use_client_roots
        self._config_path = config_path

    async def resolve(self, context: Any | None = None) -> RootAccess:
        if self._static_roots:
            return RootAccess(self._static_roots, "static")

        client_roots = await self._client_roots(context)
        if client_roots:
            return RootAccess(client_roots, "client")

        config_roots = read_config_roots(self._config_path)
        if config_roots:
            return RootAccess(config_roots, "config")
        raise _configuration_error(
            "The MCP client supplied no usable filesystem roots and no fallback roots are configured.",
            self._config_path,
        )

    async def _client_roots(self, context: Any | None) -> tuple[Path, ...]:
        if not self._use_client_roots or context is None:
            return ()
        try:
            result = await context.session.list_roots()
        except Exception:
            return ()

        roots: set[Path] = set()
        for item in getattr(result, "roots", ()):
            parsed = urlparse(str(getattr(item, "uri", "")))
            if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
                continue
            candidate = Path(url2pathname(unquote(parsed.path)))
            if not candidate.is_absolute():
                continue
            try:
                candidate = candidate.resolve(strict=True)
            except (FileNotFoundError, OSError):
                continue
            if candidate.is_dir():
                roots.add(candidate)
        return tuple(sorted(roots, key=str))


class ServiceRegistry:
    """Reuse services, and therefore path locks, for each canonical root set."""

    def __init__(self) -> None:
        self._services: dict[tuple[str, ...], NotebookService] = {}

    def get(self, roots: tuple[Path, ...]) -> NotebookService:
        from .service import NotebookService

        key = tuple(str(root) for root in roots)
        service = self._services.get(key)
        if service is None:
            service = NotebookService(list(roots))
            self._services[key] = service
        return service


def _configuration_error(
    message: str, config_path: Path | None = None
) -> NotebookToolError:
    return NotebookToolError(
        "ROOT_CONFIGURATION_REQUIRED",
        message,
        "Open a project as the MCP client root or run notebook_roots.py add /absolute/project/root.",
        {"config_path": str(config_path or default_config_path())},
    )


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
