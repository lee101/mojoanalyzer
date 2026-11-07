from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from pathlib import Path

from .core import CONFIDENCES, SEVERITIES, FileCtx, Finding, Index
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
) -> list[Finding]:
    index = Index()
    ctxs = []
    for name, src in sources:
        ctx = FileCtx(Path(name), src, index, display=name)
        index.add(name, ctx.mod)
        ctxs.append(ctx)
    rules = [BY_ID[i]() for i in (rule_ids if rule_ids is not None else [r.id for r in ALL])]
    cmin, smin = CONFIDENCES.index(min_confidence), SEVERITIES.index(min_severity)
    out: list[Finding] = []
    for ctx in ctxs:
        file_codes: set[str] | bool | None = False
        for ln in ctx.lines:
            m = SUPPRESS_FILE.search(ln)
            if m:
                file_codes = _codes(m)
                break
        seen: set[tuple[int, int, str]] = set()
        for r in rules:
            for f in r.check(ctx):
                key = (f.line, f.col, f.rule)
                if key in seen or suppressed(f, ctx.lines, file_codes):
                    continue
                if CONFIDENCES.index(f.confidence) < cmin or SEVERITIES.index(f.severity) < smin:
                    continue
                seen.add(key)
                out.append(f)
    out.sort(key=lambda f: (f.path, f.line, f.col, f.rule))
    return out


def analyze_paths(
    paths: Sequence[str | Path],
    rule_ids: Sequence[str] | None = None,
    min_confidence: str = "low",
    min_severity: str = "info",
) -> list[Finding]:
    srcs = [(str(p), p.read_text(encoding="utf-8", errors="replace")) for p in collect(paths)]
    return analyze_sources(srcs, rule_ids, min_confidence, min_severity)
