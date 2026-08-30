"""The flyer's COPY table must not carry duplicate keys, and every language
must define the same set.

Why this exists: on 29 Aug two sessions each added a "contact" line to the
same dict literal. Python does not complain about a duplicate key in a dict
literal, it silently keeps the last one, so the file said one thing and the
printed PDF said another. A flyer is printed and handed out; text that does
not match its source is the kind of error nobody catches until it is on a
wall.
"""
from __future__ import annotations

import ast
import collections
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
FLYER = REPO / "advocacy" / "build_flyer.py"


def _copy_table() -> dict[str, list[str]]:
    tree = ast.parse(FLYER.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "COPY" for t in node.targets):
            return {lang.value: [k.value for k in d.keys]
                    for lang, d in zip(node.value.keys, node.value.values)}
    raise AssertionError("COPY table not found in build_flyer.py")


def test_no_duplicate_keys_in_any_language():
    for lang, keys in _copy_table().items():
        dupes = [k for k, n in collections.Counter(keys).items() if n > 1]
        assert not dupes, (
            f"{lang} defines {dupes} more than once; Python keeps only the last, "
            "so the rendered flyer will not match the source")


def test_languages_define_the_same_keys():
    table = _copy_table()
    reference = set(table["en"])
    for lang, keys in table.items():
        missing = reference - set(keys)
        extra = set(keys) - reference
        assert not missing, f"{lang} is missing {sorted(missing)}"
        assert not extra, f"{lang} has {sorted(extra)} that en does not"


def test_every_key_is_actually_drawn():
    """A copy string nobody draws is copy that silently never ships."""
    src = FLYER.read_text()
    for key in _copy_table()["en"]:
        assert f'c["{key}"]' in src, f'COPY key "{key}" is never drawn on the page'
