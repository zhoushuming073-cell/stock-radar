"""Serve the existing static dashboard on the local website port."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


root = Path(__file__).resolve().parents[1] / "site" / "dist"
handler = partial(QuietHandler, directory=str(root))
ThreadingHTTPServer(("127.0.0.1", 4174), handler).serve_forever()
