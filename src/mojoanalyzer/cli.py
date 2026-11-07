from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence

from .core import CONFIDENCES, RISKS, SEVERITIES
from .engine import analyze_sources, collect, select_rules
from .rules import ALL


def _csv(v: str) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mojoanalyzer", description="Conservative Mojo performance/idiom analyzer")
    ap.add_argument("paths", nargs="*", help=".mojo files or directories")
    ap.add_argument("--format", choices=("text", "json"), default="text")
    ap.add_argument("--select", type=_csv, help="comma-separated rule ids/prefixes to enable")
    ap.add_argument("--ignore", type=_csv, help="comma-separated rule ids/prefixes to disable")
    ap.add_argument("--min-confidence", choices=CONFIDENCES, default="medium")
    ap.add_argument("--min-severity", choices=SEVERITIES, default="info")
    ap.add_argument("--fail-on", choices=(*SEVERITIES, "never"), default="low", help="exit 1 if a finding >= this")
    ap.add_argument("--no-risk", choices=tuple(RISKS), action="append", default=[], help="drop findings with risk")
    ap.add_argument("--statistics", action="store_true", help="print per-rule counts")
    ap.add_argument("--list-rules", action="store_true")
    ap.add_argument("--explain", metavar="RULE")
    a = ap.parse_args(argv)
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
        print(f"\n{doc}\n\nbad:\n{r.bad}\n\ngood:\n{r.good}")
        return 0
    if not a.paths:
        ap.error("no paths")
    files = collect(a.paths)
    srcs = [(str(p), p.read_text(encoding="utf-8", errors="replace")) for p in files]
    found = analyze_sources(srcs, select_rules(a.select, a.ignore), a.min_confidence, a.min_severity)
    found = [f for f in found if f.risk not in a.no_risk]
    if a.format == "json":
        print(json.dumps([f.to_dict() for f in found], indent=1))
    else:
        for f in found:
            print(f.format())
        if a.statistics:
            for k, v in sorted(Counter(f.rule for f in found).items()):
                print(f"{v:6} {k}", file=sys.stderr)
        print(f"{len(found)} finding(s) in {len(files)} file(s)", file=sys.stderr)
    if a.fail_on == "never":
        return 0
    lvl = SEVERITIES.index(a.fail_on)
    return 1 if any(SEVERITIES.index(f.severity) >= lvl for f in found) else 0


if __name__ == "__main__":
    raise SystemExit(main())
