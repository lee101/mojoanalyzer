from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence

from .core import CONFIDENCES, RISKS, SEVERITIES, Finding
from .engine import analyze_sources, collect, select_rules
from .report import llm, sarif, top
from .rules import ALL


def _csv(v: str) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["serve"]:
        from .server import main as serve_main

        return serve_main(args[1:])
    if args[:1] == ["--version"]:
        from . import __version__

        print(__version__)
        return 0
    ap = argparse.ArgumentParser(
        prog="mojoanalyzer", description="Conservative Mojo performance/idiom and correctness analyzer"
    )
    ap.add_argument("paths", nargs="*", help=".mojo files or directories")
    ap.add_argument("--format", choices=("text", "json", "llm", "sarif"), default="text")
    ap.add_argument("--top", type=int, metavar="N", help="keep the N highest-value findings (sev x conf x hot)")
    ap.add_argument("--hot-only", action="store_true", help="only findings in loops / loop-called functions")
    ap.add_argument("--select", type=_csv, help="comma-separated rule ids/prefixes to enable")
    ap.add_argument("--ignore", type=_csv, help="comma-separated rule ids/prefixes to disable")
    ap.add_argument("--min-confidence", choices=CONFIDENCES, default="medium")
    ap.add_argument("--min-severity", choices=SEVERITIES, default="info")
    ap.add_argument("--fail-on", choices=(*SEVERITIES, "never"), default="low", help="exit 1 if a finding >= this")
    ap.add_argument("--no-risk", choices=tuple(RISKS), action="append", default=[], help="drop findings with risk")
    ap.add_argument("--statistics", action="store_true", help="print per-rule counts")
    ap.add_argument("--jobs", type=int, metavar="N", help="worker processes (default: cpu count, max 16; 1 = serial)")
    ap.add_argument("--list-rules", action="store_true")
    ap.add_argument(
        "--explain", metavar="RULE", nargs="?", const="", help="describe RULE; bare: add why-line per finding"
    )
    ap.add_argument("--rule-option", action="append", default=[], metavar="RULE.key=val", help="e.g. MA203.strict=1")
    a = ap.parse_args(args)
    verbose = False
    if a.explain is not None and (a.explain == "" or not any(a.explain in (r.id, r.name) for r in ALL)):
        if a.explain:
            a.paths.insert(0, a.explain)
        a.explain, verbose = None, True
    for opt in a.rule_option:
        rid, _, kv = opt.partition(".")
        k, _, v = kv.partition("=")
        r = next((r for r in ALL if rid in (r.id, r.name)), None)
        if r is None or not k:
            print(f"bad --rule-option {opt}", file=sys.stderr)
            return 2
        r.options = {**r.options, k: v.lower() not in ("0", "false", "no", "")}
    if a.list_rules:
        for r in ALL:
            print(f"{r.id} {r.name:24} {r.severity:6} risk={r.risk:8} {(r.__doc__ or '').split(chr(10))[0]}")
        return 0
    if a.explain:
        r = next((r for r in ALL if a.explain in (r.id, r.name)), None)
        if r is None:
            print(f"unknown rule {a.explain}", file=sys.stderr)
            return 2
        doc = " ".join((r.__doc__ or "").split())
        print(f"{r.id} {r.name}\nseverity={r.severity} confidence={r.confidence} risk={r.risk} ({RISKS[r.risk]})")
        print(f"\n{doc}" + (f"\n\nwhy: {r.why}" if r.why else "") + f"\n\nbad:\n{r.bad}\n\ngood:\n{r.good}")
        return 0
    if not a.paths:
        ap.error("no paths")
    files = collect(a.paths)
    srcs = [(str(p), p.read_text(encoding="utf-8", errors="replace")) for p in files]
    found = analyze_sources(srcs, select_rules(a.select, a.ignore), a.min_confidence, a.min_severity, jobs=a.jobs)
    found = [f for f in found if f.risk not in a.no_risk]
    if a.hot_only:
        found = [f for f in found if f.hot > 0 or f.rule.startswith("MA4")]
    if a.format == "llm":
        print(llm(found, len(files), a.top))
        return _exit(a.fail_on, found)
    found = top(found, a.top)
    if a.format == "json":
        print(json.dumps([f.to_dict() for f in found], indent=1))
    elif a.format == "sarif":
        print(sarif(found, [(r.id, r.name, (r.__doc__ or "").split(chr(10))[0]) for r in ALL]))
    else:
        for f in found:
            print(f.format(verbose))
        if a.statistics:
            for k, v in sorted(Counter(f.rule for f in found).items()):
                print(f"{v:6} {k}", file=sys.stderr)
        print(f"{len(found)} finding(s) in {len(files)} file(s)", file=sys.stderr)
    return _exit(a.fail_on, found)


def _exit(fail_on: str, found: list[Finding]) -> int:
    if fail_on == "never":
        return 0
    lvl = SEVERITIES.index(fail_on)
    return 1 if any(SEVERITIES.index(f.severity) >= lvl for f in found) else 0


if __name__ == "__main__":
    raise SystemExit(main())
