"""The send packet is generated, has been hand-edited since, and rebuilding it
would silently revert the edits.

`outreach/letters/send-packet-partners.md` is written wholesale by
`outreach/build_send_packet.py` from `outreach/letters/outreach-letters-full-set.md`.
It has also been edited by hand ever since: sent-and-to-whom markers, and
corrections made after a letter went out, including one from eleven live service
types to eighteen.

On 2026-09-01 the two had diverged completely: every letter body in the packet
differed from the source. A rebuild would have reverted all of them and erased
the record of what had already been sent, while printing "ready to send".

So the builder now refuses instead, and these tests hold that refusal in place.
They exercise the guard on synthetic text rather than on the letters: outreach/
is a separate private repo, gitignored and absent on a fresh checkout, and no
test here may depend on private content or reproduce any of it.

This does NOT decide whether the packet should still be generated at all. That
is a design call: either the builder learns to preserve the annotations, or the
packet stops being generated and becomes the record. The guard only stops the
question being answered by destroying one side of it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
OUTREACH = REPO / "outreach"


def _builder():
    """The builder module, or a skip reason if outreach/ is not cloned here."""
    if not (OUTREACH / "build_send_packet.py").exists():
        pytest.skip("outreach/ is gitignored and not cloned in this checkout")
    sys.path.insert(0, str(OUTREACH))
    import build_send_packet                                    # noqa: PLC0415
    return build_send_packet


LONG = "x" * 400          # a letter body: one long unwrapped line
SHORT = "y" * 80          # an annotation: hard-wrapped commentary


def test_only_long_lines_count_as_letter_bodies():
    """The guard has to tell letter text from commentary without understanding
    either. Length is the whole discriminator, so it is the thing to pin."""
    b = _builder()
    assert b._bodies(f"{LONG}\n{SHORT}\n") == {LONG}


def test_refuses_when_a_body_would_be_lost(tmp_path, monkeypatch):
    """The real failure: the packet holds letter text the rebuild does not."""
    b = _builder()
    packet = tmp_path / "send-packet-partners.md"
    packet.write_text(f"{LONG}\n{SHORT}\n")
    monkeypatch.setattr(b, "OUT", packet)

    with pytest.raises(SystemExit) as e:
        b.refuse_if_it_would_revert(f"{SHORT}\n")

    msg = str(e.value)
    assert "REFUSING TO WRITE" in msg
    assert "Nothing was written" in msg
    assert LONG not in msg          # never echo letter prose into a failure
    assert packet.read_text() == f"{LONG}\n{SHORT}\n"


def test_allows_a_rebuild_that_keeps_every_body(tmp_path, monkeypatch):
    """Rewrapped commentary is fine. Losing a body is not."""
    b = _builder()
    packet = tmp_path / "send-packet-partners.md"
    packet.write_text(f"{LONG}\n{SHORT}\n")
    monkeypatch.setattr(b, "OUT", packet)

    b.refuse_if_it_would_revert(f"{LONG}\ndifferent commentary\n")


def test_a_missing_packet_is_not_a_conflict(tmp_path, monkeypatch):
    """First generation on a fresh clone has nothing to protect."""
    b = _builder()
    monkeypatch.setattr(b, "OUT", tmp_path / "does-not-exist.md")

    b.refuse_if_it_would_revert(f"{LONG}\n")


def test_the_builder_actually_calls_the_guard():
    """A guard the writer does not call protects nothing, and the call sits one
    line above the write, where an edit could drop it without failing anything
    else."""
    b = _builder()
    src = Path(b.__file__).read_text()
    guard_at = src.index("refuse_if_it_would_revert(new_text)")
    write_at = src.index("OUT.write_text(new_text)")
    assert guard_at < write_at
