# Contributing

```
uv run pytest                  # 547 tests: units, golden fixtures, CLI, mojo build of every fixture/example
uv run pytest -m 'not compile' # skip the toolchain tests
UPDATE_GOLDEN=1 uv run pytest tests/test_fixtures.py
uvx ruff check && uvx ruff format --check && uvx ty check
examples/run.sh                # re-run benchmarks (MOJO=/path/to/mojo)
```

Every rule has `tests/fixtures/<RULE>/positive*.mojo` (must fire) and `negative*.mojo` (near misses, must not
fire), each with a golden `.expected` file covering all rules. All fixtures and examples build with
`mojo build`, except `positive_cerr_*.mojo` dialect fixtures, which must fail to build.
The compile tests use `$MOJO` or `mojo` on `PATH` and are skipped when neither exists.

## Adding a rule

1. Add a class in `src/mojoanalyzer/rules/` with `id`, `name`, `severity`, `confidence`, `risk`, a docstring, and `bad`/`good` snippets. Register it in `rules/__init__.py`.
2. Add `tests/fixtures/<ID>/positive*.mojo` and `negative*.mojo` (near misses that must not fire), then `UPDATE_GOLDEN=1 uv run pytest tests/test_fixtures.py` and review the `.expected` diff.
3. Prefer silence over a wrong suggestion: bail out when types, callees or aliasing are unknown.
4. For perf rules add `examples/<name>/before.mojo` and `after.mojo`, run `examples/run.sh`, and record the result in `examples/RESULTS.md`. Drop the rule if it gives no measurable gain.
5. Regenerate docs: `uv run python scripts/gen_rules_doc.py > docs/rules.md`.

## Performance changes

The analyzer must stay deterministic. Check that findings are byte-identical before and after on a large tree:

```
MOJOANALYZER_JOBS=1 mojoanalyzer DIR --format json --fail-on never > a.json
mojoanalyzer DIR --format json --fail-on never > b.json
cmp a.json b.json
```
