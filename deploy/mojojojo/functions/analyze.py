import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from mojoanalyzer.server import handle_analyze


def handler(request):
    status, body = handle_analyze(request.get("body"))
    return {"status": status, "body": body}
