"""Loopback HTTP server for the GUI. Binds 127.0.0.1 only."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from self_nomad.gui.app import GuiApp


def serve(repo: Path, port: int = 8765) -> None:
    app = GuiApp(repo)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._respond("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._respond("POST")

        def _respond(self, method: str) -> None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            form: dict[str, str] = {key: values[-1] for key, values in query.items()}
            if method == "POST":
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length).decode("utf-8", errors="replace")
                posted = {key: values[-1] for key, values in parse_qs(raw).items()}
                form.update(posted)
            body = app.handle(method, parsed.path, form).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    host, bound = server.server_address[:2]
    shown = host.decode("ascii") if isinstance(host, bytes) else host
    print(f"self-nomad gui http://{shown}:{bound}/  repo={repo}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
