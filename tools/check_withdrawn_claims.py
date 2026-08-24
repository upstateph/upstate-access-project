#!/usr/bin/env python3
"""Fail if a withdrawn finding is asserted anywhere in the project.

THE CLAIM: "70 of Greenville County's 182 pedestrian deaths (38.5%) fell within
150 m of a modeled walking route to a health center", and its companion "every
nearby death happened in darkness". Both are WITHDRAWN. A null model refutes the
first — routing every tract to a RANDOMLY CHOSEN health center captures more
deaths (~59%) than the real nearest one, so the statistic measures how much
arterial road a route covers, not risk. The second is 84.1% of all county
pedestrian deaths in darkness versus 85.7% near these corridors: a 1.6-point
difference, which is noise.

WHY THIS FILE EXISTS: the claim has come back twice, both times because
ACTION-PLAN.md was regenerated wholesale from a stale base, and both times into
the practitioner review email — the worst possible place, since that email goes
to physicians whose trust is the entire point of sending it, and onward to a
neighbor being asked for a personal favor. A grep only helps if someone
remembers to run it. This runs in the test suite and in a pre-commit hook.

    python3 tools/check_withdrawn_claims.py            # public repo
    python3 tools/check_withdrawn_claims.py outreach   # or any paths

TWO DESIGN CHOICES, both learned from a checker that got them wrong:

1. Exemption is WINDOW-based, not line-based. The retraction in
   docs/project-writeup.md spans four lines: the numbers land on one line and
   "This claim has been withdrawn" on the next. A same-line rule flags the
   retraction itself — and a checker that fires on your own correction is one
   people switch off, which is worse than no checker.

2. Patterns match the ASSERTION, not the numbers. README describes the pipeline
   step as "150 m proximity"; that is a code comment about what a script
   computes, not a claim about the world. Matching a bare "150 m" makes this
   noisy, and noisy checks get ignored.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Where to look when no paths are given. outreach/ is a separate private repo
# cloned in place; it is included because that is where the regressions happened.
DEFAULT_TARGETS = ["docs", "dashboard", "README.md", "outreach", "advocacy"]


def _docx_text(path: Path) -> str:
    """Visible text of a .docx, one line per paragraph."""
    import zipfile

    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    return re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml))


def _pdf_text(path: Path) -> str:
    """Rough text of a PDF: inflate streams, keep the shown strings.

    Not a real parser — enough to catch a sentence. Returned as ONE line, so
    window-based exemption degrades to whole-document exemption here. That is
    the right failure direction: a PDF that discusses the withdrawal anywhere
    is almost certainly the write-up, and a false alarm on a generated artifact
    would train someone to ignore the check."""
    import base64
    import zlib

    # A PDF stream may be Flate, ASCII85, or ASCII85-then-Flate, and the order
    # varies by producer. The advocacy briefs are a85+Flate, which a zlib-only
    # attempt fails to read — silently, yielding an empty document that passes
    # every check. Vacuous coverage is worse than none, so try the combinations.
    CONTENT_OP = re.compile(rb"BT\b.{0,400}?\bTf\b", re.S)

    def candidates(raw: bytes):
        yield raw
        for decoded in (lambda: base64.a85decode(raw, adobe=True),
                        lambda: base64.a85decode(raw.strip(b"\r\n "), adobe=False)):
            try:
                stage = decoded()
            except (ValueError, TypeError):
                continue
            yield stage
            try:
                yield zlib.decompress(stage)
            except zlib.error:
                pass
        try:
            yield zlib.decompress(raw)
        except zlib.error:
            pass

    def inflate(raw: bytes) -> str | None:
        # SCORE the candidates rather than taking the first that looks plausible.
        # 200 KB of undecoded ASCII85 contains the bytes "Tj" by coincidence, so
        # a presence test accepts the garbage and reports a healthy character
        # count while having read nothing. Require a real text-showing sequence
        # (BT ... Tf) and keep whichever candidate has the most of them.
        best, best_score = None, 0
        for cand in candidates(raw):
            score = len(CONTENT_OP.findall(cand))
            if score > best_score:
                best, best_score = cand, score
        return best.decode("latin-1", "ignore") if best else None

    chunks = []
    for m in re.finditer(rb"stream\r?\n?(.*?)endstream", path.read_bytes(), re.S):
        text = inflate(m.group(1))
        if text:
            chunks.append(text)
    blob = " ".join(chunks)
    # Text-showing operators carry their strings in (parens); also handle the
    # hex form <...> that some producers emit.
    shown = re.findall(r"\((?:\\.|[^()\\])*\)", blob)
    return " ".join(_unescape_pdf_string(s[1:-1]) for s in shown)


# PDF literal strings escape any non-ASCII byte as a THREE-DIGIT OCTAL code, so
# a curly apostrophe arrives as the four characters \222 and an em dash as \227.
# Leaving those literal made the guard blind in exactly the file type that burned
# this project twice: "70 of the county’s 182 pedestrian deaths" is caught in
# markdown and MISSED in a PDF, because the pattern's ['’] class can never match
# a backslash. The claim then ships in the attachment while every scan reads
# clean — the same vacuous-coverage failure as the a85+Flate bug above, one layer
# further in.
_PDF_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f",
                "(": "(", ")": ")", "\\": "\\"}


def _unescape_pdf_string(raw: str) -> str:
    """Resolve PDF string escapes, including \ddd octal, to real characters.

    Bytes are interpreted as cp1252, a close stand-in for the WinAnsiEncoding
    reportlab writes. Anything unmappable is dropped rather than raising: this
    runs inside a pre-send check, and a decoding error must not be the reason a
    document goes out unscanned.
    """
    out, i, n = [], 0, len(raw)
    while i < n:
        ch = raw[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        nxt = raw[i + 1:i + 2]
        if nxt and nxt in "01234567":
            digits = ""
            j = i + 1
            while j < n and len(digits) < 3 and raw[j] in "01234567":
                digits += raw[j]
                j += 1
            out.append(bytes([int(digits, 8) & 0xFF]).decode("cp1252", "ignore"))
            i = j
        elif nxt in _PDF_ESCAPES:
            out.append(_PDF_ESCAPES[nxt])
            i += 2
        elif nxt:
            out.append(nxt)      # \<other> is that literal character in PDF
            i += 2
        else:
            i += 1
    return "".join(out)


# Scan everything a recipient could actually READ, not just markdown. The
# drop-in letter is a .docx and the partner briefs are .pdf, so a markdown-only
# scan passes while a withdrawn claim sits in the attachment that gets sent.
READERS = {
    ".md": lambda p: p.read_text(encoding="utf-8"),
    ".js": lambda p: p.read_text(encoding="utf-8"),
    ".html": lambda p: p.read_text(encoding="utf-8"),
    ".txt": lambda p: p.read_text(encoding="utf-8"),
    # Published data files carry prose too — `model_notes` is what a regenerated
    # write-up gets rebuilt from, and a statistic sitting in JSON with its
    # original framing is how a retracted interpretation quietly survives a
    # rewrite. The raw counts are fine; the patterns match assertions, not
    # numbers.
    ".json": lambda p: p.read_text(encoding="utf-8"),
    ".docx": _docx_text,
    ".pdf": _pdf_text,
}

# Each pattern must match a claim being ASSERTED, not a number in passing.
CLAIM_PATTERNS = [
    # "70 of the county's 182 pedestrian deaths"
    (re.compile(r"\b70\s+of\s+(?:the\s+\w+['’]s\s+|Greenville\s+County['’]s\s+)?182\b", re.I),
     "the 70-of-182 corridor overlap"),
    # "within 150 meters of a modeled walking route" — the assertion, not "150 m proximity"
    (re.compile(r"within\s+(?:about\s+)?150\s*(?:m\b|meters|metres)[^.]{0,60}?"
                r"(?:walking\s+route|route\s+to|modeled\s+route)", re.I),
     "the 150 m proximity claim"),
    # "38.5% ... pedestrian deaths" in either order, same sentence-ish span
    (re.compile(r"38\.5\s*%[^.]{0,80}(?:pedestrian|deaths?)|"
                r"(?:pedestrian|deaths?)[^.]{0,80}38\.5\s*%", re.I),
     "the 38.5% figure"),
    (re.compile(r"\bdeaths?\s+(?:happened\s+|occurred\s+)?in\s+darkness\b", re.I),
     "the deaths-in-darkness companion claim"),
    (re.compile(r"\b(?:84\.1|85\.7)\s*%", re.I),
     "the darkness base-rate figures"),
    # The exact framing that survived in the data file and fed the PDF briefs.
    (re.compile(r"evidence of overlap", re.I),
     "the 'evidence of overlap' framing (reads as a caveat, not a retraction)"),
]

# FILE-LEVEL INVARIANT, separate from the line patterns above.
#
# The corridor counts are legitimate data — the map is kept as descriptive
# geography — so the bare numbers must NOT be flagged line by line. But a data
# file carrying `deaths_near_any_corridor` with no trace of the withdrawal is
# how the retracted interpretation travels: prose gets regenerated from data,
# and the PDF briefs built their lead statistic straight out of this field.
# So any file publishing the statistic must also carry the withdrawal.
REQUIRE_WITHDRAWAL_MARKER = [
    (re.compile(r"deaths_near_any_corridor|pct_deaths_near_any_corridor"),
     "publishes the corridor statistic"),
]

# Words that mean the surrounding passage is ABOUT the withdrawal.
EXEMPT = re.compile(
    r"withdraw|retract|null model|do not quote|don't quote|regression|reintroduc|"
    r"didn['’]t survive|not a decision|runs backwards|refut|no longer|"
    r"previously reported|base rate|not a signal",
    re.I,
)
# Lines within this many lines of exempting language are treated as retraction
# context. Four covers a wrapped markdown paragraph without swallowing a
# neighbouring one.
WINDOW = 4


def iter_files(targets: list[str]):
    for t in targets:
        p = (REPO / t) if not Path(t).is_absolute() else Path(t)
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix in READERS and ".git" not in f.parts:
                    yield f


def check_file(path: Path) -> list[tuple[int, str, str]]:
    reader = READERS.get(path.suffix)
    if reader is None:
        return []
    try:
        text = reader(path)
    except (UnicodeDecodeError, OSError, KeyError, ValueError):
        return [(0, "UNREADABLE — could not be scanned, so it is unverified",
                 f"{path.name} could not be parsed")]

    # A document that yields almost no text is UNVERIFIED, not clean. This has
    # already bitten once: a zlib-only PDF reader returned "" for the partner
    # briefs and that empty string sailed through every pattern, so both briefs
    # were reported clean while asserting the withdrawn claim on page one.
    # Chrome-printed PDFs (Skia/PDF, Type0/CIDFontType2) are the other case —
    # their text is CID glyph indices that need the font's ToUnicode CMap, which
    # this deliberately does not implement. Either way, silence must not read as
    # a pass: the whole point of this check is outbound attachments.
    if path.suffix in {".pdf", ".docx"} and len(text.strip()) < 200 <= path.stat().st_size:
        return [(0, "UNVERIFIED — almost no extractable text, so the check is "
                    "vacuous for this file (image-only, or CID-encoded fonts "
                    "from a browser 'Print to PDF')",
                 f"{path.name}: {len(text.strip())} chars from "
                 f"{path.stat().st_size:,} bytes")]

    lines = text.splitlines()
    # This checker quotes the claim in its own docstring; exempt it explicitly
    # rather than contorting the patterns to avoid describing what they match.
    if path.resolve() == Path(__file__).resolve():
        return []
    exempt_near = [bool(EXEMPT.search(l)) for l in lines]
    hits = []

    # File-level check first: a file may publish the statistic only if it also
    # says, somewhere, that the interpretation was withdrawn.
    if not any(exempt_near):
        for pattern, why in REQUIRE_WITHDRAWAL_MARKER:
            for i, line in enumerate(lines):
                if pattern.search(line):
                    hits.append((i + 1, f"{why} without any withdrawal note in the file",
                                 line.strip()[:110]))
                    break
    for i, line in enumerate(lines):
        lo, hi = max(0, i - WINDOW), min(len(lines), i + WINDOW + 1)
        if any(exempt_near[lo:hi]):
            continue
        for pattern, label in CLAIM_PATTERNS:
            if pattern.search(line):
                hits.append((i + 1, label, line.strip()[:110]))
                break
    return hits


def main(argv: list[str]) -> int:
    targets = argv[1:] or DEFAULT_TARGETS
    findings = []
    for path in iter_files(targets):
        for lineno, label, text in check_file(path):
            rel = path.relative_to(REPO) if REPO in path.parents else path
            findings.append((rel, lineno, label, text))

    if not findings:
        print("OK — no withdrawn claim is asserted.")
        return 0

    print("WITHDRAWN CLAIM REAPPEARED — do not send or publish until fixed:\n")
    for rel, lineno, label, text in findings:
        print(f"  {rel}:{lineno} — {label}")
        print(f"    {text}\n")
    print("The crash-corridor overlap and its darkness companion are withdrawn:")
    print("a null model captures MORE deaths (~59%) routing to a RANDOM clinic")
    print("than to the real nearest one, so the statistic tracks arterial road")
    print("coverage, not risk. Retraction wording: docs/project-writeup.md §3.")
    print("\nIf a passage is legitimately about the withdrawal, say so in it —")
    print("nearby wording like 'withdrawn' or 'null model' exempts it.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
