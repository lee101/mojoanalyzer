from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import dataclass, field

from .core import RISKS, Finding

RISK_TAG = {"fp": "fp", "unsafe": "unsafe", "threads": "threads", "api": "api", "codesize": "size"}


@dataclass
class Group:
    path: str
    rule: str
    msg: str
    fix: str
    risk: str
    lines: list[int] = field(default_factory=list)
    score: float = 0.0


def _short(s: str) -> str:
    return s.replace("`", "")


def groups(found: list[Finding]) -> list[Group]:
    out: dict[tuple[str, str, str, str, str], Group] = {}
    for f in found:
        key = (f.path, f.scope, f.rule, f.message, f.suggestion)
        g = out.get(key)
        if g is None:
            g = out[key] = Group(f.path, f.rule, _short(f.message), _short(f.suggestion), f.risk)
        g.lines.append(f.line)
        g.score = max(g.score, f.score)
    return list(out.values())


def top(found: list[Finding], n: int | None) -> list[Finding]:
    if not n:
        return found
    return sorted(found, key=lambda f: (-f.score, f.path, f.line))[:n]


def llm(found: list[Finding], nfiles: int, n: int | None = None) -> str:
    gs = groups(found)
    if n:
        gs = sorted(gs, key=lambda g: (-g.score, g.path, g.lines[0]))[:n]
    counts = Counter(f.rule for f in found)
    head = " ".join(f"{k}:{v}" for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))
    shown = f" top {len(gs)}" if n else ""
    lines = [f"mojoanalyzer {len(found)} findings {nfiles} files{shown} | {head}".rstrip(" |")]
    cur = None
    for g in sorted(gs, key=lambda g: (g.path, g.lines[0], g.rule)):
        if g.path != cur:
            cur = g.path
            rel = os.path.relpath(cur) if os.path.isabs(cur) else cur
            lines.append(cur if rel.startswith("..") else rel)
        locs = ",".join(f"L{ln}" for ln in sorted(set(g.lines)))
        tag = f" [{RISK_TAG[g.risk]}]" if g.risk in RISK_TAG else ""
        lines.append(f" {locs} {g.rule} {g.msg} -> {g.fix}{tag}")
    return "\n".join(lines)


SARIF_LEVEL = {"info": "note", "low": "note", "medium": "warning", "high": "error"}


def sarif(found: list[Finding], rules: list[tuple[str, str, str]]) -> str:
    doc = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "mojoanalyzer",
                        "rules": [
                            {"id": rid, "name": name, "shortDescription": {"text": desc}} for rid, name, desc in rules
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": f.rule,
                        "level": SARIF_LEVEL[f.severity],
                        "message": {
                            "text": f"{f.message} -> {f.suggestion}"
                            + ("" if f.risk == "none" else f" [risk: {RISKS[f.risk]}]")
                        },
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": f.path},
                                    "region": {"startLine": f.line, "startColumn": f.col + 1},
                                }
                            }
                        ],
                        "properties": {"confidence": f.confidence, "risk": f.risk, "hot": f.hot},
                    }
                    for f in found
                ],
            }
        ],
    }
    return json.dumps(doc, indent=1)
