from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .core import CONFIDENCES, SEVERITIES
from .engine import analyze_sources, select_rules
from .rules import ALL

MAX_BYTES = 512_000
MAX_FILES = 200


def _csv(v: object) -> list[str]:
    if isinstance(v, str):
        v = v.split(",")
    return [str(x).strip() for x in v or [] if str(x).strip()] if isinstance(v, list) else []


def handle_analyze(body: object) -> tuple[int, dict]:
    """Shared by the HTTP server and the mojojojo function. body: {code | files, select, ignore, min_*}."""
    if not isinstance(body, dict):
        return 400, {"error": "json object required"}
    files = body.get("files")
    if files is None and isinstance(body.get("code"), str):
        files = {"input.mojo": body["code"]}
    if not isinstance(files, dict) or not files or not all(isinstance(v, str) for v in files.values()):
        return 400, {"error": "send {code} or {files: {name: source}}"}
    if len(files) > MAX_FILES:
        return 413, {"error": f"more than {MAX_FILES} files"}
    if sum(len(v) for v in files.values()) > MAX_BYTES:
        return 413, {"error": f"payload over {MAX_BYTES} bytes"}
    conf, sev = body.get("min_confidence", "medium"), body.get("min_severity", "info")
    if conf not in CONFIDENCES or sev not in SEVERITIES:
        return 400, {"error": f"min_confidence in {list(CONFIDENCES)}, min_severity in {list(SEVERITIES)}"}
    found = analyze_sources(
        [(str(k), v) for k, v in files.items()],
        select_rules(_csv(body.get("select")), _csv(body.get("ignore"))),
        conf,
        sev,
        jobs=1,
    )
    return 200, {"count": len(found), "findings": [f.to_dict() for f in found]}


def rules_payload() -> list[dict]:
    return [
        {
            "id": r.id,
            "name": r.name,
            "severity": r.severity,
            "confidence": r.confidence,
            "risk": r.risk,
            "doc": " ".join((r.__doc__ or "").split()),
        }
        for r in ALL
    ]


class Handler(BaseHTTPRequestHandler):
    server_version = f"mojoanalyzer/{__version__}"

    def _send(self, status: int, obj: object) -> None:
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send(200, {"ok": True, "version": __version__})
        elif self.path == "/rules":
            self._send(200, rules_payload())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/analyze":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self._send(411, {"error": "Content-Length required"})
        if n > MAX_BYTES * 2:
            return self._send(413, {"error": "payload too large"})
        try:
            body = json.loads(self.rfile.read(n))
        except ValueError:
            return self._send(400, {"error": "invalid json"})
        try:
            status, out = handle_analyze(body)
        except Exception as e:
            status, out = 500, {"error": f"{type(e).__name__}: {e}"}
        self._send(status, out)

    def log_message(self, fmt: str, *args: object) -> None:
        if os.environ.get("MOJOANALYZER_ACCESS_LOG"):
            super().log_message(fmt, *args)


def serve(host: str, port: int) -> None:
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"mojoanalyzer {__version__} listening on {host}:{port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="mojoanalyzer serve", description="HTTP API: POST /analyze, GET /rules /healthz")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    a = ap.parse_args(argv)
    serve(a.host, a.port)
    return 0
