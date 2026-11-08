# mojoanalyzer

Fast, conservative static analyzer for [Mojo](https://www.modular.com/mojo). Finds performance problems,
numeric correctness bugs and Mojo 1.2 dialect breakage, and tells you the risk of every suggested fix.
Think ruff for Mojo. Pure Python, zero dependencies.

- 66 rules in four families: performance (MA1xx), correctness and math safety for numeric and trading code (MA2xx),
  heap allocation churn (MA3xx), Mojo 1.2 dialect errors (MA4xx)
- Precision over recall: a rule fires only when the parser can prove the preconditions for its rewrite
- Every finding carries severity, confidence and a risk class (`none`, `fp`, `unsafe`, `threads`, `api`, `codesize`)
- Suggested rewrites are benchmarked with the real toolchain: 1.06x to over 500x, see [examples/RESULTS.md](examples/RESULTS.md)
- Output for humans, JSON, SARIF (GitHub code scanning) and a token-lean format for LLM agents
- Parallel: a 323-file, 100k-line trading tree analyzes in about 4 s on 32 cores
- HTTP API and Python API, deployable to [mojojojo](deploy/mojojojo/README.md) or Docker

## Install

```
uv tool install git+https://github.com/lee101/mojoanalyzer
```

Standalone binaries, Docker and CI snippets: [docs/install.md](docs/install.md).

## Use

```
mojoanalyzer src                                   # default: confidence >= medium
mojoanalyzer src --select MA2 --min-confidence high   # correctness only
mojoanalyzer src --no-risk fp --no-risk unsafe        # only bit-exact, safe rewrites
mojoanalyzer src --format llm --top 40 --hot-only     # agent-friendly, hottest findings first
mojoanalyzer src --format sarif --fail-on never > out.sarif
mojoanalyzer --explain MA201                          # what a rule checks, with bad and good code
mojoanalyzer src --explain                            # add a why-line with the concrete failing value
```

```
tests/fixtures/MA115/positive.mojo:4:18 MA115 high high `xs.insert(0, ...)` in a loop shifts every element -> Deque + appendleft()
tests/fixtures/MA201/positive.mojo:16:23 MA201 medium high divisor `Float64(hits)` (a counter starting at 0) is never checked in this function -> guard: `if hits == 0: return <fallback>` or divide by `max(Float64(hits), eps)`
```

Format: `path:line:col RULE severity confidence message -> suggestion [risk]`.

Flags: `--select` / `--ignore` (ids or prefixes), `--min-confidence`, `--min-severity`, `--no-risk CLASS`,
`--top N`, `--hot-only`, `--fail-on`, `--jobs N`, `--statistics`, `--rule-option MA203.strict=1`, `--version`.
Exit code 1 when a finding is at or above `--fail-on` (default `low`).

Suppress with `# mojoanalyzer: ignore[MA106]` on the line, a bare `# mojoanalyzer: ignore` for all rules, or
`# mojoanalyzer: ignore-file[MA107]` for the file.

## Rules

Full list with bad and good examples: [docs/rules.md](docs/rules.md).

| family | what | examples |
|---|---|---|
| MA1xx (30) | performance and idiom | vectorize, SIMD reductions, `parallelize`, list reserve, loop interchange, `List.insert(0)`, membership in `List` |
| MA2xx (15) | correctness and math safety | unguarded division, `Int(float)` truncation, float equality, NaN compares, `sqrt` of a negative variance, Int `/` flooring, swapped clamps, off-by-one indexes, bps vs fraction |
| MA3xx (9) | allocation churn | allocation inside hot loops, invariant allocation, missed moves, dict capacity |
| MA4xx (12) | Mojo 1.2 dialect | removed or renamed syntax that fails to compile |

## Trading code

The MA2xx family is built for numeric and trading code, where a silent NaN or a floored division costs money.
Run `mojoanalyzer src --select MA2 --min-confidence high` in CI. Every message says what is wrong, the rewrite,
and with `--explain` the concrete bad value (for example `1.0 / n` with `n == 0` returns inf for Float64 and 0 for Int).

## API and deploy

```
mojoanalyzer serve --port 8080
curl -s localhost:8080/analyze -H 'Content-Type: application/json' -d '{"code": "..."}'
```

```python
from mojoanalyzer import analyze_text

analyze_text(src, min_confidence="low")
```

[docs/api.md](docs/api.md). Deploy to mojojojo as a Python function: [deploy/mojojojo](deploy/mojojojo/README.md).
Docker: `docker build -t mojoanalyzer . && docker run -p 8080:8080 mojoanalyzer`.

## Speed

Parsing is serial and the rule pass is forked across files. Findings are byte-identical for any `--jobs`.
A 323-file trading codebase: 12.2 s serial, 4.7 s parallel on 32 cores. `MOJOANALYZER_JOBS=1` forces serial.

## More

[docs/design.md](docs/design.md), [CONTRIBUTING.md](CONTRIBUTING.md), [examples/](examples/), [LICENSE](LICENSE) (MIT).
Target dialect: Mojo 1.2 nightly.
