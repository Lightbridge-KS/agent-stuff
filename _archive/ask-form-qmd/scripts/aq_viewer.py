"""Artifact-scoped loopback viewer. No idle, visibility, or lifetime timers."""
from __future__ import annotations

import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from aq_document import Failure
from aq_store import check_id, verify_bundle


def runtime_root() -> Path:
    identity = str(os.getuid()) if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")
    path = Path(tempfile.gettempdir()) / ("ask-form-qmd-runtime-" + hashlib.sha256(identity.encode()).hexdigest()[:12])
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink() or (hasattr(os, "getuid") and path.stat().st_uid != os.getuid()):
        raise Failure(5, "viewer", "Unsafe runtime directory; remove the conflicting temp entry.")
    if os.name != "nt":
        path.chmod(0o700)
    return path


def runtime_file(ask_id: str) -> Path:
    check_id(ask_id)
    return runtime_root() / (ask_id + ".json")


def load_runtime(ask_id: str) -> dict | None:
    path = runtime_file(ask_id)
    try:
        record = json.loads(path.read_text())
        url = urllib.parse.urlsplit(record["base"])
        if url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port or url.path or url.query or url.username:
            return None
        if record.get("id") != ask_id or not isinstance(record.get("token"), str):
            return None
        return record
    except (OSError, ValueError, KeyError):
        return None


def request(record: dict, route: str, method: str = "GET") -> dict:
    url = record["base"] + route + "?t=" + urllib.parse.quote(record["token"])
    req = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
    # Ignore proxy environment configuration for this local capability URL.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=2) as response:
        return json.load(response)


def healthy(record: dict | None) -> bool:
    if record is None:
        return False
    try:
        return request(record, "/health").get("id") == record["id"]
    except (OSError, ValueError):
        return False


def view_result(record: dict) -> dict:
    artifact = Path(record["artifact"])
    return {"status": "ready", "ask_id": record["id"], "saved": record["saved"],
            "source_path": str(artifact / "source.qmd"), "html_path": str(artifact / "rendered/index.html"),
            "url": record["base"] + "/?t=" + record["token"], "warnings": record.get("warnings", []).copy()}


@contextlib.contextmanager
def viewer_lock(ask_id: str):
    """Kernel-released lock; crashed launchers cannot strand an exclusive lock."""
    path = runtime_root() / (ask_id + ".lock")
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            stream.write(b"0")
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def start(artifact: Path, entrypoint: Path) -> dict:
    manifest = json.loads((artifact / "manifest.json").read_text())
    ask_id = manifest["id"]
    with viewer_lock(ask_id):
        existing = load_runtime(ask_id)
        if healthy(existing) and Path(existing["artifact"]).resolve() == artifact.resolve():
            return view_result(existing)
        runtime_file(ask_id).unlink(missing_ok=True)
        log = runtime_root() / (ask_id + ".log")
        options = {"start_new_session": True} if os.name != "nt" else {
            "creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
        try:
            with log.open("w") as output:
                proc = subprocess.Popen([sys.executable, str(entrypoint), "_serve", str(artifact)],
                                        stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                        close_fds=True, **options)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                record = load_runtime(ask_id)
                if healthy(record):
                    return view_result(record)
                if proc.poll() is not None:
                    break
                time.sleep(0.05)
            proc.terminate() if proc.poll() is None else None
            proc.wait(timeout=5)
            detail = log.read_text()[-1500:]
            raise Failure(5, "viewer", "Viewer did not become ready. Use serve ID in the harness's background runner. " + detail,
                          ask_id=ask_id, html_path=str(artifact / "rendered/index.html"), saved=manifest["saved"])
        except OSError as exc:
            raise Failure(5, "viewer", f"Cannot start viewer: {exc}", ask_id=ask_id,
                          html_path=str(artifact / "rendered/index.html"), saved=manifest["saved"]) from exc


def stop(ask_id: str) -> dict:
    with viewer_lock(ask_id):
        record = load_runtime(ask_id)
        if not healthy(record):
            runtime_file(ask_id).unlink(missing_ok=True)
            return {"status": "stopped", "ask_id": ask_id, "already_stopped": True}
        request(record, "/stop", "POST")
        for _ in range(100):
            if not healthy(record):
                return {"status": "stopped", "ask_id": ask_id, "saved": record["saved"]}
            time.sleep(0.05)
        raise Failure(5, "viewer", "Viewer has not confirmed shutdown; retry stop.")


def serve(artifact: Path, *, guard_startup: bool = False) -> None:
    artifact = artifact.resolve()
    verify_bundle(artifact)
    manifest = json.loads((artifact / "manifest.json").read_text())
    ask_id = manifest["id"]
    html = (artifact / "rendered/index.html").read_bytes()
    if hashlib.sha256(html).hexdigest() != manifest["html_sha256"]:
        raise Failure(5, "viewer", "Saved HTML hash mismatch; regenerate the artifact.")
    token = secrets.token_urlsafe(32)
    policy = ("default-src 'none'; script-src 'unsafe-inline' data:; style-src 'unsafe-inline' data:; "
              "img-src data:; font-src data:; connect-src 'none'; frame-src 'none'; "
              "object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log capability URLs.

        def authorized(self) -> bool:
            if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                self.reply(403, b"Invalid host", "text/plain")
                return False
            origin = self.headers.get("Origin")
            if origin and origin != f"http://127.0.0.1:{self.server.server_port}":
                self.reply(403, b"Invalid origin", "text/plain")
                return False
            values = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("t", [])
            if len(values) != 1 or not secrets.compare_digest(values[0], token):
                self.reply(403, b"Invalid token", "text/plain")
                return False
            return True

        def reply(self, status: int, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", policy)
            self.end_headers()
            if self.command != "HEAD":
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        def do_GET(self):
            if not self.authorized():
                return
            path = urllib.parse.urlsplit(self.path).path
            if path in {"/", "/index.html"}:
                self.reply(200, html, "text/html")
            elif path == "/health":
                self.reply(200, json.dumps({"id": ask_id}).encode(), "application/json")
            else:
                self.reply(404, b"Not found", "text/plain")

        do_HEAD = do_GET

        def do_POST(self):
            if not self.authorized():
                return
            if urllib.parse.urlsplit(self.path).path != "/stop":
                self.reply(404, b"Not found", "text/plain")
                return
            self.reply(200, b'{"status":"stopping"}', "application/json")
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    # Detached launchers already hold this lock until readiness. Foreground
    # launchers acquire it here, then release before entering the serving loop.
    with viewer_lock(ask_id) if guard_startup else contextlib.nullcontext():
        existing = load_runtime(ask_id)
        if healthy(existing):
            print(json.dumps(view_result(existing)), flush=True)
            return
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        record = {"id": ask_id, "pid": os.getpid(), "base": f"http://127.0.0.1:{server.server_port}",
                  "token": token, "artifact": str(artifact), "saved": manifest["saved"], "warnings": manifest.get("warnings", [])}
        path = runtime_file(ask_id)
        pending = path.with_suffix(f".{os.getpid()}.tmp")
        pending.write_text(json.dumps(record))
        pending.replace(path)
        print(json.dumps(view_result(record)), flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        current = load_runtime(ask_id)
        if current and current["token"] == token:
            path.unlink(missing_ok=True)
        if not manifest["saved"]:
            shutil.rmtree(artifact)
