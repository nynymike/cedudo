#!/usr/bin/env python3
"""Serve the workshop policy directory over HTTP with CORS for Tarp."""

from __future__ import annotations

import http.server
import socketserver
from pathlib import Path

PORT = 8000
POLICY_DIR = Path(__file__).resolve().parent.parent / "policy"


class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()


def main() -> None:
    if not POLICY_DIR.is_dir():
        raise SystemExit(f"policy directory not found: {POLICY_DIR}")

    handler = lambda *args, **kwargs: CORSRequestHandler(  # noqa: E731
        *args, directory=str(POLICY_DIR), **kwargs
    )

    with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
        print(f"Serving policy store at http://127.0.0.1:{PORT}/")
        print("Configure Tarp to load: http://127.0.0.1:8000/cedudo.cjar")
        print(f"Directory: {POLICY_DIR}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
