"""Loopback-only artifact delivery and explicit, idempotent snapshot storage."""

from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from jsonschema import Draft7Validator, ValidationError
from ed_core import Failure, MAX_JSON, digest, read_json

FILES = {
    "index.html": "text/html",
    "viewer.js": "text/javascript",
    "theme.css": "text/css",
    "viewer.css": "text/css",
    "document.json": "application/json",
    "artifact.json": "application/json",
}


def runtime_dir() -> Path:
    path = Path(tempfile.gettempdir()) / f"explorable-document-{os.getuid()}"
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise Failure(5, "viewer", "Unsafe viewer runtime directory.")
    path.chmod(0o700)
    return path


def record_path(identifier: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise Failure(2, "identity", "Invalid artifact ID.")
    return runtime_dir() / f"{identifier}.json"


def save_submission(
    root: Path, manifest: dict, schema: dict, key: str, value: dict
) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", key):
        raise Failure(
            2, "submission", "Idempotency-Key requires 16–64 plain characters."
        )
    if (
        not isinstance(value, dict)
        or set(value) != {"snapshot", "comment"}
        or not isinstance(value["comment"], str)
        or len(value["comment"]) > 4000
    ):
        raise Failure(
            2, "submission", "Submit snapshot and a comment up to 4000 characters."
        )
    try:
        Draft7Validator(schema).validate(value["snapshot"])
    except ValidationError as exc:
        raise Failure(
            2, "submission", f"Snapshot schema: {exc.message[:1000]}"
        ) from exc
    identifier = digest({"key": key, "artifact": manifest["id"]})[:32]
    folder = root / "submissions" / manifest["id"]
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{identifier}.json"
    payload_hash = digest(value)
    record = {
        "schema_version": 1,
        "submission_id": identifier,
        "artifact_id": manifest["id"],
        "rendered_hash": manifest["rendered_hash"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "payload_hash": payload_hash,
        **value,
    }
    # Atomic create-if-absent: racing retries can never overwrite another payload.
    stage = folder / f".{uuid4().hex}.tmp"
    try:
        with stage.open("x") as stream:
            json.dump(record, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(stage, target)
            directory = os.open(folder, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except FileExistsError:
            record = read_json(target, MAX_JSON + 4096)
            if record["payload_hash"] != payload_hash:
                raise Failure(
                    2,
                    "conflict",
                    "Idempotency key already used with different reviewed data.",
                )
    finally:
        stage.unlink(missing_ok=True)
    return {
        k: record[k]
        for k in ["submission_id", "artifact_id", "created_at", "rendered_hash"]
    }


def make_server(
    directory: Path, root: Path, token: str, temporary: bool = False
) -> ThreadingHTTPServer:
    manifest = read_json(directory / "manifest.json")
    payload = read_json(directory / "rendered/document.json", 100 * 1024**2)
    schema = payload.get("schema") if not temporary else None

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def respond(
            self, status: int, value: object, mime: str = "application/json"
        ) -> None:
            data = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
            )
            self.end_headers()
            self.wfile.write(data)

        def guard(self, mutation: bool = False) -> bool:
            host = f"127.0.0.1:{server.server_port}"
            if self.headers.get("Host") != host:
                self.respond(403, {"message": "Host rejected"})
                return False
            origin = self.headers.get("Origin")
            if (origin and origin != f"http://{host}") or (
                mutation and origin != f"http://{host}"
            ):
                self.respond(403, {"message": "Origin rejected"})
                return False
            return True

        def authorized(self) -> bool:
            if not hmac.compare_digest(
                self.headers.get("Authorization", ""), f"Bearer {token}"
            ):
                self.respond(403, {"message": "Session capability required"})
                return False
            return True

        def do_GET(self) -> None:
            if not self.guard():
                return
            if self.path in {"/api/session", "/api/health"}:
                if self.path == "/api/session" and not schema:
                    self.respond(404, {"message": "Handoff unavailable"})
                elif self.authorized():
                    self.respond(200, {"id": manifest["id"], "status": "ready"})
                return
            name = "index.html" if self.path == "/" else self.path[1:]
            if name not in FILES:
                self.respond(404, {"message": "Unknown artifact file"})
                return
            try:
                self.respond(
                    200, (directory / "rendered" / name).read_bytes(), FILES[name]
                )
            except OSError:
                self.respond(
                    500,
                    {
                        "message": "Saved file unavailable; reopen after checking integrity."
                    },
                )

        def do_POST(self) -> None:
            if not self.guard(mutation=True):
                return
            if self.path not in {"/api/stop", "/api/submissions"} or (
                self.path == "/api/submissions" and not schema
            ):
                self.respond(404, {"message": "Route unavailable"})
                return
            if not self.authorized():
                return
            if self.path == "/api/stop":
                self.respond(200, {"status": "stopped", "artifact_id": manifest["id"]})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if (
                    self.headers.get("Transfer-Encoding")
                    or not 0 < size <= MAX_JSON
                    or self.headers.get("Content-Type") != "application/json"
                ):
                    self.respond(
                        413,
                        {
                            "message": "Send bounded application/json with Content-Length"
                        },
                    )
                    return
                self.connection.settimeout(5)
                data = self.rfile.read(size)
                if len(data) != size:
                    raise ValueError("Incomplete body")
                value = json.loads(
                    data,
                    parse_constant=lambda _: (_ for _ in ()).throw(
                        ValueError("Non-finite JSON")
                    ),
                )
                assert isinstance(schema, dict)
                result = save_submission(
                    root,
                    manifest,
                    schema,
                    self.headers.get("Idempotency-Key", ""),
                    value,
                )
                self.respond(200, result)
            except Failure as exc:
                self.respond(
                    409 if exc.result["stage"] == "conflict" else 422, exc.result
                )
            except (ValueError, UnicodeError, RecursionError):
                self.respond(400, {"message": "Invalid JSON payload"})
            except OSError:
                self.respond(
                    500,
                    {
                        "message": "Snapshot was not saved. Retry or download the reviewed copy."
                    },
                )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    return server


def contact(record: dict, route: str, stop: bool = False) -> dict:
    request = Request(
        record["url"] + route,
        data=b"" if stop else None,
        headers={"Authorization": f"Bearer {record['token']}", "Origin": record["url"]},
    )
    with urlopen(request, timeout=2) as response:
        return json.load(response)


def stop(identifier: str) -> dict:
    record = record_path(identifier)
    if not record.exists():
        return {"status": "not_running", "artifact_id": identifier}
    value = read_json(record)
    try:
        result = contact(value, "/api/stop", stop=True)
    except (URLError, OSError):
        result = {"status": "not_running", "artifact_id": identifier}
    record.unlink(missing_ok=True)
    return result


def serve(directory: Path, root: Path, temporary: bool = False) -> None:
    token = secrets.token_urlsafe(32)
    identifier = read_json(directory / "manifest.json")["id"]
    server = make_server(directory, root, token, temporary)
    record = record_path(identifier)
    value = {
        "id": identifier,
        "pid": os.getpid(),
        "url": f"http://127.0.0.1:{server.server_port}",
        "token": token,
    }
    stage = record.with_suffix(f".{uuid4().hex}.tmp")
    with stage.open("x") as stream:
        os.chmod(stage, 0o600)
        json.dump(value, stream)
    stage.replace(record)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if record.exists() and read_json(record).get("token") == token:
            record.unlink(missing_ok=True)


def start(directory: Path, root: Path, temporary: bool = False) -> dict:
    identifier = read_json(directory / "manifest.json")["id"]
    record = record_path(identifier)
    if record.exists():
        try:
            value = read_json(record)
            if contact(value, "/api/health")["id"] == identifier:
                return {
                    "status": "ready",
                    "artifact_id": identifier,
                    "url": value["url"] + f"/#session={value['token']}",
                }
        except (URLError, OSError, ValueError):
            record.unlink(missing_ok=True)
    log = runtime_dir() / f"{identifier}.log"
    with log.open("a") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                str(directory),
                str(root),
                str(int(temporary)),
            ],
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            start_new_session=True,
        )
    for _ in range(100):
        if record.exists():
            value = read_json(record)
            try:
                if contact(value, "/api/health")["id"] == identifier:
                    return {
                        "status": "ready",
                        "artifact_id": identifier,
                        "url": value["url"] + f"/#session={value['token']}",
                    }
            except (URLError, OSError):
                pass
        if process.poll() is not None:
            break
        time.sleep(0.05)
    raise Failure(
        5,
        "viewer",
        "Viewer did not start. Use serve ID in a foreground/background terminal.",
        artifact_id=identifier,
        artifact_path=str(directory),
        log_path=str(log),
    )


if __name__ == "__main__":
    serve(Path(sys.argv[1]), Path(sys.argv[2]), bool(int(sys.argv[3])))
