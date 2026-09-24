"""Token-gated one-result collection; runtime state is never part of the archive."""
from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import sys
import threading
import time
from urllib.parse import urlsplit, parse_qs
import subprocess
import webbrowser

from aq_document import Failure, SNAPSHOT
from aq_form import validate_answers
from aq_store import new_id, save


def launch(url):
    try:
        if sys.platform == 'darwin':
            return subprocess.run(['open', url], capture_output=True, timeout=15).returncode == 0
        return webbrowser.open(url)
    except (OSError, subprocess.TimeoutExpired):
        return False


class Collection:
    def __init__(self, bundle, manifest, *, saving=True, staged=False, root=None):
        self.bundle, self.manifest = bundle, manifest
        self.saving, self.staged, self.root = saving, staged, root
        self.form = json.loads((bundle / 'form.json').read_text())
        self.html = (bundle / 'rendered/index.html').read_text().replace(SNAPSHOT, '<script id="aq-snapshot" type="application/json">{"mode":"collect"}</script>').encode()
        self.token = secrets.token_urlsafe(32)
        self.lock, self.done, self.ack = threading.Lock(), threading.Event(), threading.Event()
        self.result = None
        self.started = time.monotonic()

    def finish(self, status, body=None):
        with self.lock:
            if self.result is not None:
                return 409, {'message': 'Already finished; retrieve /state for the accepted result.'}
            if status == 'submitted':
                errors, values = validate_answers(body, self.form['questions'])
                if errors:
                    return 400, {'errors': errors}
                result = {'status': status, **values}
                result['meta'].update({'ask_id': new_id(self.form['title']), 'duration_s': round(time.monotonic() - self.started, 1)})
                if self.saving:
                    try:
                        save(self.bundle, result, self.manifest, root=self.root, staged=self.staged)
                    except (OSError, Failure) as exc:
                        result['meta']['save_error'] = str(exc)
                        print(f'not saved: {exc}', file=sys.stderr, flush=True)
            else:
                result = {'status': status}
            self.result = result
            return 200, result


def server_for(run):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_):
            pass

        def reply(self, code, value, content='application/json'):
            body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', content + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline' data:; style-src 'unsafe-inline' data:; img-src data:; font-src data:; connect-src 'self'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def authorized(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            tokens = parse_qs(urlsplit(self.path).query).get('t', [])
            return self.headers.get('Host') == origin[7:] and self.headers.get('Origin', origin) == origin and len(tokens) == 1 and secrets.compare_digest(tokens[0], run.token)

        def do_GET(self):
            if not self.authorized():
                return self.reply(403, {'message': 'Invalid local session'})
            route = urlsplit(self.path).path
            if route in {'/', '/index.html'}:
                return self.reply(200, run.html, 'text/html')
            if route == '/state':
                return self.reply(200, run.result or {'status': 'waiting'})
            self.reply(404, {'message': 'Unknown route'})

        def do_POST(self):
            if not self.authorized():
                return self.reply(403, {'message': 'Invalid local session'})
            route = urlsplit(self.path).path
            if route == '/ack':
                self.reply(200, {'status': 'acknowledged'})
                if run.result is not None:
                    run.ack.set()
                return
            if route not in {'/submit', '/cancel'}:
                return self.reply(404, {'message': 'Unknown route'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.reply(415, {'message': 'Use application/json'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                return self.reply(400, {'message': 'Invalid content length'})
            if not 0 < length <= 1_000_000:
                return self.reply(413, {'message': 'Expected 1–1000000 bytes'})
            try:
                body = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeError, TimeoutError):
                return self.reply(400, {'message': 'Invalid JSON body'})
            code, result = run.finish('submitted' if route == '/submit' else 'cancelled', body)
            self.reply(code, result)
            if code == 200:
                run.done.set()
    return ThreadingHTTPServer(('127.0.0.1', 0), Handler)


def collect(bundle, manifest, *, no_save=False, no_open=False, timeout=None, staged=False):
    run = Collection(bundle, manifest, saving=not no_save, staged=staged)
    try:
        server = server_for(run)
    except OSError as exc:
        raise Failure(3, 'bind', str(exc)) from exc
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/?t={run.token}'
    print(url, file=sys.stderr, flush=True)
    if not no_open and not launch(url):
        print('Browser launch failed; open the URL above.', file=sys.stderr, flush=True)
    try:
        if not run.done.wait(timeout):
            run.finish('timeout')
        else:
            run.ack.wait(5)  # bounded delivery/recovery window, not a user-input timer
    except KeyboardInterrupt:
        run.finish('cancelled')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    return run.result
