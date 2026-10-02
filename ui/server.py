"""`make ui`: the course on a page, served from this laptop.

The standard library's HTTP server and one session at a time — this is a
demonstration surface for one presenter, not a service. It listens on
localhost only. Every call that changes something is a POST; the page reads
the whole state back after each one.
"""
from __future__ import annotations

import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ui.session import PRESETS, Session  # noqa: E402

HERE = pathlib.Path(__file__).parent
STATIC = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/app.css": ("app.css", "text/css")}
LOCK = threading.Lock()
STATE = {"session": Session()}

# A button, the session method it presses, and the fields it reads.
ACTIONS = {"submit": ("submit", ["brief"]), "approve-outline": ("approve_outline", []),
           "generate": ("generate", ["node"]), "approve": ("approve", ["node"]),
           "reject": ("reject", ["node", "reason"]), "checks": ("course_checks", []),
           "sign": ("sign", []), "publish": ("publish", []), "release": ("release", [])}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):         # noqa: A002 — the page is the log
        pass

    def _send(self, code: int, body: bytes, kind: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, code: int = 200) -> None:
        self._send(code, json.dumps(payload, default=_plain).encode())

    def do_GET(self):
        if self.path in STATIC:
            name, kind = STATIC[self.path]
            return self._send(200, (HERE / name).read_bytes(), kind)
        if self.path == "/api/state":
            with LOCK:
                return self._json(STATE["session"].snapshot())
        if self.path == "/api/presets":
            return self._json({k: {"title": v[0], "brief": v[1]} for k, v in PRESETS.items()})
        self._send(404, b"{}")

    def _ours(self) -> bool:
        """Only this page may press the buttons. Another page open in the same
        browser could otherwise post here — a plain-text POST needs no
        preflight — and reset the demo, or switch it to live and spend calls."""
        port = self.server.server_address[1]
        local = {f"localhost:{port}", f"127.0.0.1:{port}"}
        origin = self.headers.get("Origin")
        return (self.headers.get("Host") in local
                and (origin is None or origin.removeprefix("http://") in local)
                and (self.headers.get("Content-Type") or "").startswith("application/json"))

    def do_POST(self):
        if not self._ours():
            return self._json({"ok": False, "error": "only this page may call this server"}, 403)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"ok": False, "error": "the request is not JSON"}, 400)
        if not isinstance(body, dict):
            return self._json({"ok": False, "error": "the request must be a JSON object"}, 400)
        name = self.path.removeprefix("/api/")
        with LOCK:
            if name == "reset":
                mode = body.get("mode") if body.get("mode") in ("recorded", "live") else "recorded"
                preset = body.get("preset") if body.get("preset") in PRESETS else "course"
                try:
                    STATE["session"] = Session(mode, preset)
                except Exception as exc:              # noqa: BLE001 — e.g. live without keys
                    return self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
                return self._json({"ok": True})
            if name not in ACTIONS:
                return self._json({"ok": False, "error": f"no action {name!r}"}, 404)
            method, fields = ACTIONS[name]
            return self._json(STATE["session"].act(method, *[body.get(f) for f in fields]))


def _plain(value):
    return sorted(value) if isinstance(value, (set, frozenset)) else str(value)


def main(port: int = 8800) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"the course on a page: http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8800)
