from __future__ import annotations

import multiprocessing
import os
import re
from collections.abc import Iterable, Sequence
from pathlib import Path

from .core import CONFIDENCES, SEVERITIES, FileCtx, Finding, Index, annotate
from .rules import ALL, BY_ID

SUPPRESS = re.compile(r"#\s*mojoanalyzer:\s*ignore(?:\[([A-Z0-9, ]+)\])?")
SUPPRESS_FILE = re.compile(r"#\s*mojoanalyzer:\s*ignore-file(?:\[([A-Z0-9, ]+)\])?")


def collect(paths: Sequence[str | Path]) -> list[Path]:
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            out.extend(sorted(x for x in p.rglob("*") if x.suffix in (".mojo", ".🔥") and x.is_file()))
        elif p.is_file():
            out.append(p)
    return out


def _codes(m: re.Match[str]) -> set[str] | None:
    g = m.group(1)
    return None if g is None else {c.strip() for c in g.split(",") if c.strip()}


def suppressed(f: Finding, lines: list[str], file_codes: set[str] | bool | None) -> bool:
    if file_codes is None or (isinstance(file_codes, set) and f.rule in file_codes):
        return True
    if 0 < f.line <= len(lines):
        m = SUPPRESS.search(lines[f.line - 1])
        if m and not SUPPRESS_FILE.search(lines[f.line - 1]):
            codes = _codes(m)
            return codes is None or f.rule in codes
    return False


def select_rules(select: Iterable[str] | None = None, ignore: Iterable[str] | None = None) -> list[str]:
    ids = [r.id for r in ALL]
    if select:
        sel = list(select)
        ids = [i for i in ids if any(i.startswith(s) for s in sel)]
    if ignore:
        ign = list(ignore)
        ids = [i for i in ids if not any(i.startswith(s) for s in ign)]
    return ids


def analyze_sources(
    sources: Sequence[tuple[str, str]],
    rule_ids: Sequence[str] | None = None,
    min_confidence: str = "low",
    min_severity: str = "info",
    jobs: int | None = None,
) -> list[Finding]:
    index = Index()
    ctxs = []
    for name, src in sources:
        ctx = FileCtx(Path(name), src, index, display=name)
        index.add(name, ctx.mod)
        index.structs.update(ctx.structs)
        ctxs.append(ctx)
    rules = [BY_ID[i]() for i in (rule_ids if rule_ids is not None else [r.id for r in ALL])]
    cmin, smin = CONFIDENCES.index(min_confidence), SEVERITIES.index(min_severity)
    jobs = _jobs(len(ctxs)) if jobs is None else jobs
    if jobs > 1 and len(ctxs) >= PARALLEL_MIN:
        out = _check_parallel(ctxs, rules, cmin, smin, jobs)
    else:
        out = [f for ctx in ctxs for f in _check_one(ctx, rules, cmin, smin)]
    out.sort(key=lambda f: (f.path, f.line, f.col, f.rule))
    return out


PARALLEL_MIN = 12
_STATE: list[tuple[list[FileCtx], list, int, int]] = []


def _jobs(nfiles: int) -> int:
    if not hasattr(os, "fork"):
        return 1
    env = os.environ.get("MOJOANALYZER_JOBS")
    n = int(env) if env and env.isdigit() else len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else 1
    return max(1, min(n, nfiles // 4, 16))


def _check_one(ctx: FileCtx, rules: list, cmin: int, smin: int) -> list[Finding]:
    file_codes: set[str] | bool | None = False
    for ln in ctx.lines:
        m = SUPPRESS_FILE.search(ln)
        if m:
            file_codes = _codes(m)
            break
    seen: set[tuple[int, int, str]] = set()
    mine: list[Finding] = []
    for r in rules:
        for f in r.check(ctx):
            key = (f.line, f.col, f.rule)
            if key in seen or suppressed(f, ctx.lines, file_codes):
                continue
            if CONFIDENCES.index(f.confidence) < cmin or SEVERITIES.index(f.severity) < smin:
                continue
            seen.add(key)
            mine.append(f)
    annotate(ctx, mine)
    return mine


def _work(i: int) -> list[Finding]:
    ctxs, rules, cmin, smin = _STATE[0]
    return _check_one(ctxs[i], rules, cmin, smin)


def _check_parallel(ctxs: list[FileCtx], rules: list, cmin: int, smin: int, jobs: int) -> list[Finding]:
    _STATE.append((ctxs, rules, cmin, smin))
    try:
        order = sorted(range(len(ctxs)), key=lambda i: -len(ctxs[i].lines))
        with multiprocessing.get_context("fork").Pool(jobs) as pool:
            res = pool.map(_work, order, chunksize=1)
    finally:
        _STATE.clear()
    return [f for r in res for f in r]


def analyze_paths(
    paths: Sequence[str | Path],
    rule_ids: Sequence[str] | None = None,
    min_confidence: str = "low",
    min_severity: str = "info",
) -> list[Finding]:
    srcs = [(str(p), p.read_text(encoding="utf-8", errors="replace")) for p in collect(paths)]
    return analyze_sources(srcs, rule_ids, min_confidence, min_severity)
