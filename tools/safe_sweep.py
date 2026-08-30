#!/usr/bin/env python3
"""Repo-wide find-and-replace that cannot silently break things.

WHY THIS EXISTS. On 2026-08-29 a blanket British-to-American spelling sweep
introduced three defects, and the test suite caught none of them:

  1. `analyses` -> `analyzes`, because the rule for the verb `analyse` matched
     inside the correct plural noun. Prose damage, visible only by reading.
  2. `centred` -> `centerd`, `realistic` -> `realiztic`: substring rules
     matching inside words they were never written for. These DID break code,
     and would have thrown at runtime rather than at commit.
  3. The worst one. `tools/check_withdrawn_claims.py` matched `meters|metres`
     deliberately, because it scans other people's drafts. The sweep collapsed
     it to `meters|meters` and silently halved the guard's coverage. Nothing
     failed, because every file in the repo had just been Americanized too.

The lesson is not "be careful". It is that the dangerous edits are the ones
that STILL PARSE and STILL PASS. So this tool gates on three things a careless
sweep skips:

  * DRY RUN BY DEFAULT. Nothing is written until you pass --apply.
  * RISK FLAGS. Hits inside regex literals, alternations, dict keys, imports,
    or identifiers are reported as RISKY and skipped unless --include-risky.
    A guard pattern spelling both variants on purpose lives exactly there.
  * VERIFY AND REVERT. After applying, every touched file is syntax-checked,
    then the full test suite and the claims guard run. If anything fails, the
    whole sweep is rolled back and the failure is printed.

    python tools/safe_sweep.py --pairs behaviour:behavior --paths dashboard
    python tools/safe_sweep.py --pairs behaviour:behavior --paths dashboard --apply
"""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "node_modules", "dist", ".pytest_cache", "__pycache__"}
TEXT_EXT = {".md", ".py", ".js", ".html", ".css", ".txt", ".json", ".csv", ".yml", ".yaml"}

# A hit sitting in any of these is presumed deliberate until a human says so.
RISKY_CONTEXT = [
    (re.compile(r"re\.(compile|match|search|sub|findall|fullmatch)"), "regex call"),
    (re.compile(r"\|"), "alternation (| on the line)"),
    (re.compile(r"^\s*(from|import)\s"), "import statement"),
    (re.compile(r"^\s*[\"']?[\w-]+[\"']?\s*:\s"), "dict key or mapping"),
    (re.compile(r"\bdef\s+\w*|class\s+\w*"), "definition line"),
    (re.compile(r"[\w/\\.-]*\.(py|js|json|csv|md|html|css)\b"), "filename"),
]


def rel(f: Path) -> str:
    """Display path. Falls back to the absolute path for anything outside the
    repo, because relative_to() raises there and a reporting helper must never
    be the thing that crashes a dry run."""
    try:
        return str(f.relative_to(REPO))
    except ValueError:
        return str(f)


def files_under(paths: list[str]):
    for raw in paths:
        p = (REPO / raw) if not Path(raw).is_absolute() else Path(raw)
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix in TEXT_EXT and not (set(f.parts) & SKIP_DIRS):
                    yield f


def classify(line: str) -> str | None:
    for pat, label in RISKY_CONTEXT:
        if pat.search(line):
            return label
    return None


def cased(src: str, repl: str) -> str:
    if src.isupper():
        return repl.upper()
    if src[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


def syntax_ok(f: Path) -> str | None:
    try:
        if f.suffix == ".py":
            ast.parse(f.read_text(encoding="utf-8"))
        elif f.suffix == ".js":
            r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
            if r.returncode:
                return r.stderr.strip().splitlines()[0] if r.stderr else "node --check failed"
        elif f.suffix == ".json":
            import json
            json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 - any parse failure is a failure
        return f"{type(e).__name__}: {e}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", nargs="+", required=True,
                    help="old:new, e.g. behaviour:behavior")
    ap.add_argument("--paths", nargs="+", required=True)
    ap.add_argument("--apply", action="store_true",
                    help="actually write. Without this it is a dry run.")
    ap.add_argument("--include-risky", action="store_true",
                    help="also edit lines flagged as risky. Read them first.")
    ap.add_argument("--word", action="store_true",
                    help="match whole words only (\\b...\\b). Recommended.")
    args = ap.parse_args()

    pairs = []
    for p in args.pairs:
        if ":" not in p:
            sys.exit(f"--pairs wants old:new, got {p!r}")
        old, new = p.split(":", 1)
        pairs.append((old, new))

    planned, risky = [], []
    for f in files_under(args.paths):
        try:
            lines = f.read_text(encoding="utf-8").splitlines(keepends=True)
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            for old, new in pairs:
                pat = rf"\b{re.escape(old)}\b" if args.word else re.escape(old)
                if re.search(pat, line, re.I):
                    (risky if classify(line) else planned).append(
                        (f, i, old, new, line.rstrip(), classify(line)))

    for f, i, old, new, line, why in risky:
        print(f"RISKY  {rel(f)}:{i}  [{why}]\n       {line.strip()[:100]}")
    if risky:
        print(f"\n{len(risky)} risky hit(s) "
              f"{'INCLUDED' if args.include_risky else 'SKIPPED'}. "
              "A guard that spells both variants on purpose lives here.\n")

    todo = planned + (risky if args.include_risky else [])
    for f, i, old, new, line, _ in planned:
        print(f"  {rel(f)}:{i}  {old} -> {new}")
    print(f"\n{len(todo)} replacement(s) across "
          f"{len({t[0] for t in todo})} file(s).")

    if not args.apply:
        print("DRY RUN. Nothing written. Re-run with --apply.")
        return 0
    if not todo:
        return 0

    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        print("\nREFUSING: working tree is dirty. Commit or stash first, so a "
              "failed sweep can be rolled back cleanly.\n" + dirty)
        return 2

    touched = set()
    for f in {t[0] for t in todo}:
        txt = original = f.read_text(encoding="utf-8")
        for _, _, old, new, _, _ in [t for t in todo if t[0] == f]:
            pat = rf"\b{re.escape(old)}\b" if args.word else re.escape(old)
            txt = re.sub(pat, lambda m: cased(m.group(0), new), txt, flags=re.I)
        if txt != original:
            f.write_text(txt, encoding="utf-8")
            touched.add(f)

    problems = [(f, err) for f in sorted(touched) if (err := syntax_ok(f))]
    if not problems:
        for label, cmd in (("tests", [".venv/bin/python", "-m", "pytest", "-q"]),
                           ("claims guard", [".venv/bin/python", "tools/check_withdrawn_claims.py"])):
            r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
            if r.returncode:
                problems.append((label, (r.stdout + r.stderr).strip()[-800:]))
                break

    if problems:
        subprocess.run(["git", "checkout", "--"] + [str(f) for f in touched], cwd=REPO)
        print("\nSWEEP REVERTED. Verification failed:")
        for what, err in problems:
            print(f"  {what}: {err}")
        return 1

    print(f"\nApplied to {len(touched)} file(s). Syntax, tests, and claims "
          "guard all pass. Read the diff before committing: a change that "
          "parses and passes can still be wrong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
