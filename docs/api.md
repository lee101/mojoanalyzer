# API

## Python

```python
from mojoanalyzer import analyze_text, analyze_paths, analyze_sources

found = analyze_text("def f(n: Int) -> Float64:\n    return 1.0 / n\n", min_confidence="low")
for f in found:
    print(f.line, f.rule, f.message, f.suggestion)

analyze_paths(["src"], rule_ids=None, min_confidence="medium", min_severity="info", jobs=None)
analyze_sources([("a.mojo", src_a), ("b.mojo", src_b)])  # cross-file call index is shared
```

`jobs=None` uses up to 16 worker processes (fork) when there are at least 12 files; `jobs=1` is serial.
Set `MOJOANALYZER_JOBS` to override the default.

## HTTP

```
mojoanalyzer serve [--host 127.0.0.1] [--port 8080]      # PORT env sets the default port
```

| route | |
|---|---|
| `GET /healthz` | `{"ok": true, "version": "..."}` |
| `GET /rules` | rule metadata list |
| `POST /analyze` | JSON body below |

```
curl -s localhost:8080/analyze -H 'Content-Type: application/json' \
  -d '{"code": "def f(n: Int) -> Float64:\n    return 1.0 / n\n", "select": "MA2", "min_confidence": "low"}'
```

Body: `code` (one source) or `files` (`{name: source}`, up to 200 files), optional `select` / `ignore`
(comma string or list of rule ids or prefixes), `min_confidence` (`low|medium|high`, default `medium`),
`min_severity` (`info|low|medium|high`). Total source limit 512000 bytes. Response:
`{"count": N, "findings": [{path, line, col, rule, severity, confidence, risk, risk_note, message, suggestion, why, hot, scope}]}`.
Errors are `{"error": "..."}` with 400, 404, 411 or 413. The server has no auth or TLS: put it behind a proxy.

## Exit codes and formats

CLI exit code 1 when a finding is at or above `--fail-on` (default `low`), 0 otherwise, 2 for usage errors.
`--format text|json|llm|sarif`. SARIF uploads to GitHub code scanning.
