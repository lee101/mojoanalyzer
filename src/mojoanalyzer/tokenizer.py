from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class K(Enum):
    NAME = "NAME"
    NUMBER = "NUMBER"
    STRING = "STRING"
    OP = "OP"
    COMMENT = "COMMENT"
    NEWLINE = "NEWLINE"
    NL = "NL"
    INDENT = "INDENT"
    DEDENT = "DEDENT"
    END = "END"


@dataclass(frozen=True, slots=True)
class Token:
    kind: K
    value: str
    line: int
    col: int

    def is_op(self, *vals: str) -> bool:
        return self.kind is K.OP and self.value in vals

    def is_name(self, *vals: str) -> bool:
        return self.kind is K.NAME and (not vals or self.value in vals)

    def __repr__(self) -> str:
        return f"{self.kind.value}({self.value!r}@{self.line}:{self.col})"


OPS = sorted(
    [
        "**=", "//=", ">>=", "<<=", "...", "->", "**", "//", "<<", ">>", "<=", ">=", "==", "!=", "+=", "-=",
        "*=", "/=", "%=", "&=", "|=", "^=", "@=", ":=",
        "+", "-", "*", "/", "%", "@", "&", "|", "^", "~", "<", ">", "(", ")", "[", "]", "{", "}", ",", ":",
        ";", ".", "=", "!", "?",
    ],
    key=len,
    reverse=True,
)  # fmt: skip
OP_RE = re.compile("|".join(re.escape(o) for o in OPS))
OPEN = {"(": ")", "[": "]", "{": "}"}
CLOSE = {")", "]", "}"}
STR_PREFIX = {"r", "b", "f", "u", "t", "rb", "br", "fr", "rf", "tr", "rt"}


def _is_id_start(c: str) -> bool:
    return c == "_" or c.isalpha()


def _is_id_char(c: str) -> bool:
    return c == "_" or c.isalnum()


def tokenize(src: str) -> list[Token]:
    out: list[Token] = []
    lines = src.splitlines(keepends=True)
    if not lines:
        return [Token(K.END, "", 1, 0)]
    indents = [0]
    depth: list[str] = []
    cont = False
    i_line = 0
    pending_str: tuple[str, int, int, list[str], bool] | None = None
    while i_line < len(lines):
        line = lines[i_line]
        ln = i_line + 1
        pos = 0
        n = len(line)
        if pending_str is not None:
            quote, sl, sc, parts, raw = pending_str
            end = _find_close(line, 0, quote, raw)
            if end < 0:
                parts.append(line)
                i_line += 1
                continue
            parts.append(line[:end])
            out.append(Token(K.STRING, "".join(parts), sl, sc))
            pending_str = None
            pos = end
        elif not depth and not cont:
            col = 0
            while pos < n and line[pos] in " \t\f":
                col = (col // 8 + 1) * 8 if line[pos] == "\t" else col + 1
                pos += 1
            if pos >= n or line[pos] in "\r\n":
                out.append(Token(K.NL, "", ln, pos))
                i_line += 1
                continue
            if line[pos] == "#":
                out.append(Token(K.COMMENT, line[pos:].rstrip("\r\n"), ln, pos))
                out.append(Token(K.NL, "", ln, n))
                i_line += 1
                continue
            if col > indents[-1]:
                indents.append(col)
                out.append(Token(K.INDENT, "", ln, 0))
            else:
                while col < indents[-1]:
                    indents.pop()
                    out.append(Token(K.DEDENT, "", ln, col))
                if col > indents[-1]:
                    indents.append(col)
                    out.append(Token(K.INDENT, "", ln, 0))
        cont = False
        while pos < n:
            c = line[pos]
            if c in " \t\f":
                pos += 1
                continue
            if c in "\r\n":
                break
            if c == "#":
                out.append(Token(K.COMMENT, line[pos:].rstrip("\r\n"), ln, pos))
                pos = n
                break
            if c == "\\" and line[pos + 1 : pos + 2] in ("\n", "\r", ""):
                cont = True
                pos = n
                break
            start = pos
            if _is_id_start(c):
                while pos < n and _is_id_char(line[pos]):
                    pos += 1
                word = line[start:pos]
                if pos < n and line[pos] in "'\"" and word.lower() in STR_PREFIX:
                    pos, tok, pend = _read_string(line, pos, ln, start, "r" in word.lower())
                    if pend is not None:
                        pending_str = pend
                        break
                    if tok is not None:
                        out.append(Token(K.STRING, line[start:pos], ln, start))
                    continue
                out.append(Token(K.NAME, word, ln, start))
                continue
            if c.isdigit() or (c == "." and line[pos + 1 : pos + 2].isdigit()):
                pos = _read_number(line, pos)
                out.append(Token(K.NUMBER, line[start:pos], ln, start))
                continue
            if c in "'\"":
                pos, tok, pend = _read_string(line, pos, ln, start, False)
                if pend is not None:
                    pending_str = pend
                    break
                out.append(Token(K.STRING, line[start:pos], ln, start))
                continue
            if c == "`":
                end = line.find("`", pos + 1)
                pos = n if end < 0 else end + 1
                out.append(Token(K.NAME, line[start:pos], ln, start))
                continue
            m = OP_RE.match(line, pos)
            op = m.group(0) if m else c
            pos += len(op)
            if op in OPEN:
                depth.append(op)
            elif op in CLOSE and depth:
                depth.pop()
            out.append(Token(K.OP, op, ln, start))
        if pending_str is not None:
            i_line += 1
            continue
        if not depth and not cont:
            last = out[-1] if out else None
            if last is not None and last.kind not in (K.NEWLINE, K.NL, K.INDENT, K.DEDENT):
                if last.kind is K.COMMENT and (len(out) < 2 or out[-2].kind in (K.NEWLINE, K.NL, K.DEDENT, K.INDENT)):
                    out.append(Token(K.NL, "", ln, n))
                else:
                    out.append(Token(K.NEWLINE, "", ln, n))
        else:
            out.append(Token(K.NL, "", ln, n))
        i_line += 1
    if pending_str is not None:
        quote, sl, sc, parts, _ = pending_str
        out.append(Token(K.STRING, "".join(parts), sl, sc))
    if out and out[-1].kind not in (K.NEWLINE, K.NL, K.DEDENT):
        out.append(Token(K.NEWLINE, "", len(lines), 0))
    last_ln = len(lines) + 1
    out.extend(Token(K.DEDENT, "", last_ln, 0) for _ in indents[1:])
    out.append(Token(K.END, "", last_ln, 0))
    return out


def _find_close(line: str, pos: int, quote: str, raw: bool) -> int:
    n = len(line)
    while pos < n:
        c = line[pos]
        if c == "\\" and not raw:
            pos += 2
            continue
        if c == "\\" and raw:
            pos += 2
            continue
        if line.startswith(quote, pos):
            return pos + len(quote)
        pos += 1
    return -1


def _read_string(
    line: str, pos: int, ln: int, start: int, raw: bool
) -> tuple[int, str | None, tuple[str, int, int, list[str], bool] | None]:
    q = line[pos]
    if line.startswith(q * 3, pos):
        quote = q * 3
        end = _find_close(line, pos + 3, quote, raw)
        if end < 0:
            return len(line), None, (quote, ln, start, [line[start:]], raw)
        return end, line[start:end], None
    end = _find_close(line, pos + 1, q, raw)
    if end < 0:
        end = len(line.rstrip("\r\n"))
    return end, line[start:end], None


def _read_number(line: str, pos: int) -> int:
    n = len(line)
    if line[pos] == "0" and pos + 1 < n and line[pos + 1] in "xXoObB":
        pos += 2
        while pos < n and (line[pos].isalnum() or line[pos] == "_"):
            pos += 1
        return pos
    while pos < n and (line[pos].isdigit() or line[pos] == "_"):
        pos += 1
    if pos < n and line[pos] == "." and not line.startswith("..", pos):
        nxt = line[pos + 1 : pos + 2]
        if not _is_id_start(nxt) or nxt in "eE":
            pos += 1
            while pos < n and (line[pos].isdigit() or line[pos] == "_"):
                pos += 1
    if pos < n and line[pos] in "eE":
        j = pos + 1
        if j < n and line[j] in "+-":
            j += 1
        if j < n and line[j].isdigit():
            pos = j
            while pos < n and line[pos].isdigit():
                pos += 1
    if pos < n and line[pos] in "jJ":
        pos += 1
    return pos
