import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from mojoanalyzer import analyze_text
from mojoanalyzer.server import MAX_BYTES, Handler, handle_analyze

BAD = "def f(n: Int) -> Float64:\n    return 1.0 / n\n"


def test_analyze_text():
    assert any(f.rule == "MA201" for f in analyze_text(BAD, min_confidence="low"))


def test_handle_ok_and_errors():
    s, o = handle_analyze({"code": BAD, "select": "MA2", "min_confidence": "low"})
    assert s == 200 and o["count"] >= 1 and o["findings"][0]["rule"].startswith("MA2")
    assert handle_analyze([])[0] == 400
    assert handle_analyze({})[0] == 400
    assert handle_analyze({"code": 1})[0] == 400
    assert handle_analyze({"code": "x", "min_confidence": "nope"})[0] == 400
    assert handle_analyze({"code": "x" * (MAX_BYTES + 1)})[0] == 413


@pytest.fixture
def base():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _post(url, data):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_http(base):
    with urllib.request.urlopen(base + "/healthz") as r:
        assert json.load(r)["ok"] is True
    with urllib.request.urlopen(base + "/rules") as r:
        assert len(json.load(r)) > 30
    s, o = _post(base + "/analyze", json.dumps({"code": BAD, "min_confidence": "low"}).encode())
    assert s == 200 and o["count"] >= 1
    assert _post(base + "/analyze", b"not json")[0] == 400
    assert _post(base + "/nope", b"{}")[0] == 404
