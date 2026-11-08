# Deploy to mojojojo

mojojojo hosts Python functions from a ZIP. mojoanalyzer is pure Python with no dependencies, so the whole
analyzer is vendored into the function bundle.

```
export MOJOJOJO_API_KEY=mj_live_...
pip install mojojojo
./build.sh                                   # writes dist/mojojojo-app.zip
mojojojo project "mojoanalyzer" --runtime app    # prints PROJECT_ID
mojojojo deploy "$PROJECT_ID" dist/mojojojo-app.zip
```

Call it:

```
curl -s -H 'Content-Type: application/json' \
  -d '{"code":"def f(n: Int) -> Float64:\n    return 1.0 / n\n","select":"MA2"}' \
  "https://mojojojo.cc/p/$PROJECT_ID/api/analyze"
```

Request fields: `code` or `files` (`{name: source}`), `select`, `ignore` (comma lists of rule ids or prefixes),
`min_confidence` (low|medium|high), `min_severity`. Response: `{count, findings[]}`. Payload limit 512 KB.

Each deploy is an immutable ZIP, so rollback is redeploying the previous ZIP.
