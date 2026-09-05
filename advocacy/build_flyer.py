#!/usr/bin/env python3
"""One-page patient-facing flyer for a waiting room, counter, or notice board.

Five partner letters promise this flyer, the New Horizon marketing thread is
about it, and the plan for reaching Medicaid patients depends on it, but it had
never been built (found 29 Aug 2026).

DESIGN RULES, each one paid for by a reviewer:

* Almost no words. Four reviewers (TM, KD, SS-prof twice) said the site is too
  text heavy, and SS-prof's mechanism applies hardest here: text presence
  creates an obligation to read, and that obligation produces avoidance. A wall
  flyer gets about two seconds. Everything that is not the offer is cut.
* The URL is the GITHUB PAGES one, deliberately, and this is the decision most
  likely to be second-guessed later. Print cannot be edited. Pages is permanent
  and under our control; it survives the beta being renamed, rate-limited, or
  moved to a VPS, because Pages can be repointed and a printed flyer cannot.
  Pages shows a single "Check my address" button through to the working tool.
* A QR code, because this audience reads it on a phone and nobody types a
  40-character URL off a wall. The URL is printed too, for anyone whose camera
  will not do it.
* No promise the tool cannot keep: no service is named that is not live, and
  the accuracy hedge stays on the page.

    python advocacy/build_flyer.py            # English
    python advocacy/build_flyer.py --lang es  # Spanish, SEE THE WARNING BELOW
"""
from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

REPO = Path(__file__).resolve().parent.parent
URL = "https://upstateph.github.io/upstate-access-project/"
URL_DISPLAY = "upstateph.github.io/upstate-access-project"
CONTACT = "nikhilajain@gmail.com"

INK = HexColor("#1a1f2b")
SOFT = HexColor("#5b6472")
# ACCENT deepened 5 Sep 2026, #1f6feb to #0B3D91, to match the community flyer.
#
# TWO REASONS, and the second is the one that actually drove it.
#
# Contrast. #1f6feb is 4.63:1 on white, which passes WCAG AA for normal text by
# a hair and is weak on a wall across a room. #0B3D91 is 10.04:1. ACCENT is only
# ever a text fill here, in three places, never a background, so darkening it
# improves every use and risks none: the 18pt mode labels, the 13pt URL, and the
# 7pt line at the foot, which was the marginal one.
#
# The pair. The community flyer moved to #0B3D91 on 4 Sep for distance
# visibility. Both families can end up on the same gym board, and two sheets
# from one person in two different blues do not read as one project. They read
# as two, or as a template somebody downloaded, and a stranger deciding in two
# seconds reads that before any word.
#
# NOT COPIED WHOLESALE. The community flyer also gained a filled headline band,
# which is what makes it register past reading distance. This flyer keeps its
# 56pt headline on white, which already carries further than the community
# flyer's 48pt. The band here is a design change, not a defect fix.
ACCENT = HexColor("#0B3D91")
LINE = HexColor("#e4e7ec")

# VOICE RULE, Nikhil 4 Sep 2026: public-facing material must sound like one
# person who lives in Greenville County, not like a marketer, and not like a
# promotion or a scam. Two things here were breaking it and both were
# structural rather than a word choice.
#
# "We never save your address" was the worse one. There is no we. It is one
# person, and the corporate plural is exactly what makes a flyer read as an
# organisation with something to sell. Now "I".
#
# The flyer also named nobody. A project name, an email, a QR code and the word
# Free, with no human on it, is the silhouette of a promotion whatever the words
# say, and it sat oddly against a positioning rule that his credibility comes
# from being local. The footer now carries his name in both languages.
#
# "No app" went too: it is a differentiator against apps, which is a marketer's
# frame. What a reader needs to know is that there is nothing to sign up for.
COPY = {
    "en": {
        "headline": "Getting there is",
        "headline2": "the hard part.",
        "sub": "See how long it really takes to reach a health center,",
        "sub2": "pharmacy, dentist, or food help from your address.",
        "modes": ["WALK", "BIKE", "DRIVE", "BUS"],
        "bus": "Bus times too, not just driving.",
        "scan": "Scan with your phone camera",
        "or_type": "or type this address:",
        "trust1": "Free. Nothing to sign up for.",
        "trust2": "I never save your address.",
        "foot": "Nikhil Jain  ·  Greenville County  ·  Upstate Access Project",
        "fine": "Travel times are estimates. Call ahead to check hours and whether they take your insurance.",
        "contact": "Is a listing wrong, or something missing?  " + CONTACT,
    },
    # ⚠️ NOT REVIEWED BY A NATIVE SPEAKER. Do not print this version until
    # someone who speaks Spanish reads it. A clumsy translation on a health
    # flyer signals that the audience was an afterthought, which is worse than
    # having no Spanish version at all.
    "es": {
        "headline": "Llegar es",
        "headline2": "lo más difícil.",
        "sub": "Vea cuánto tiempo toma realmente llegar a un centro de salud,",
        "sub2": "farmacia, dentista o ayuda con comida desde su dirección.",
        "modes": ["A PIE", "EN BICI", "EN AUTO", "EN BUS"],
        "bus": "También el tiempo en autobús, no solo en auto.",
        "scan": "Escanee con la cámara de su teléfono",
        "or_type": "o escriba esta dirección:",
        "trust1": "Gratis. No hay que registrarse.",
        "trust2": "Nunca guardo su dirección.",
        "foot": "Nikhil Jain  ·  Condado de Greenville  ·  Upstate Access Project",
        "fine": "Los tiempos son estimados. Llame antes para confirmar el horario y si aceptan su seguro.",
        "contact": "¿Hay un error o falta algo?  " + CONTACT,
    },
}


def build(lang: str, out: Path, tabs: bool = False) -> None:
    c = COPY[lang]
    W, H = letter
    m = 0.85 * inch
    pdf = canvas.Canvas(str(out), pagesize=letter)

    # Tear-off strip reserves the bottom of the page. Off by default: a clinic
    # wall or a counter wants a clean sheet, and tabs read as "lost cat" in a
    # waiting room. On for community boards, laundromats, and libraries, where
    # someone without their phone out needs to take the address away with them.
    # Strip geometry: the tabs hang DOWN from `floor`, so the floor has to sit
    # a full tab height above the footer rule or the tabs print over it.
    TAB_H = 2.15 * inch
    # FOOTER_H is the band reserved below `floor` for the footer, and it is now
    # a named number because the footer needs three lines rather than two.
    # It used to be 44 without tabs and 46 with, for no reason anyone recorded,
    # and 44pt could not hold what was being drawn into it.
    FOOTER_H = 62
    floor = (m + FOOTER_H + TAB_H) if tabs else (m + FOOTER_H)

    y = H - m - 30
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 56)
    pdf.drawString(m, y, c["headline"])
    y -= 60
    pdf.drawString(m, y, c["headline2"])

    y -= 54
    pdf.setFillColor(SOFT)
    pdf.setFont("Helvetica", 19)
    pdf.drawString(m, y, c["sub"])
    y -= 26
    pdf.drawString(m, y, c["sub2"])

    # Modes. Words rather than icons: the PDF base fonts have no emoji, and a
    # missing glyph on a printed flyer is a black box.
    y -= 54
    x = m
    pdf.setFont("Helvetica-Bold", 18)
    for i, mode in enumerate(c["modes"]):
        pdf.setFillColor(ACCENT)
        pdf.drawString(x, y, mode)
        w = pdf.stringWidth(mode, "Helvetica-Bold", 18)
        if i < len(c["modes"]) - 1:
            pdf.setFillColor(LINE)
            pdf.drawString(x + w + 12, y, "|")
        x += w + 32

    y -= 30
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Oblique", 16)
    pdf.drawString(m, y, c["bus"])

    # QR is the call to action, so it is large and sits on the text margin
    # rather than tucked in a corner. Block is centered in the space that is
    # left, so the page has no dead zone whether or not tabs are on.
    # The QR takes whatever vertical room is left. With the tear-off strip on,
    # that is much less, so it is sized to fit rather than fixed: an oversized
    # QR silently ran off the bottom of the tabs variant.
    block_top = y - 40
    # ASSERT ON THE SPACE, NOT ON THE CLAMPED RESULT.
    #
    # This used to read `assert qr_size >= 1.7 * inch`, which cannot fail: the
    # max() below floors qr_size at 1.8in, so the assertion was comparing a
    # clamped value against a smaller bound and was true by construction. Dead
    # code that reads like a guard is worse than no guard, because the failure
    # it was written for still happens and now looks impossible.
    #
    # The failure it was written for is real. When the space runs out the QR
    # does not shrink, it clamps at 1.8in and starts overlapping whatever is
    # below it, which is the footer, silently. Checking the space available
    # before the clamp is the check that would actually catch that.
    qr_space = block_top - floor - 24
    assert qr_space >= 1.8 * inch, (
        f"only {qr_space/inch:.2f}in of vertical room for the QR "
        f"(tabs={tabs}); it would clamp to 1.8in and overlap the footer")
    qr_size = min(2.9 * inch, max(1.8 * inch, qr_space))
    qr_y = floor + (block_top - floor - qr_size) / 2
    widget = qr.QrCodeWidget(URL, barLevel="M")
    b = widget.getBounds()
    d = Drawing(qr_size, qr_size,
                transform=[qr_size / (b[2] - b[0]), 0, 0, qr_size / (b[3] - b[1]),
                           -b[0] * qr_size / (b[2] - b[0]), -b[1] * qr_size / (b[3] - b[1])])
    d.add(widget)
    renderPDF.draw(d, pdf, m, qr_y)

    tx = m + qr_size + 34
    # 🔴 THE TEXT COLUMN IS TALLER THAN THE QR IT SITS BESIDE, and until 5 Sep
    # only the QR was ever measured against `floor`. The column hangs from the
    # QR's top edge and runs 133pt from its first baseline to its last, against
    # a QR that is 135pt tall in the tabs variant, so its final line, the typed
    # URL, ended up BELOW the QR and inside the tear-off strip: the dashed tab
    # lines ran straight through the address.
    #
    # It was already touching before this was noticed, by 0.2pt, and raising
    # FOOTER_H from 46 to 62 to fix the footer overlap turned that near-miss
    # into a 16pt collision. One fix uncovering the next is fine; shipping it
    # is not.
    #
    # Shrinking the strip cannot fix this. The rotated tab text is 143.1pt of
    # the 154.8pt strip, so there is 11.7pt of slack there and 24pt was needed.
    # The column has to be anchored instead: it starts where it wants, and is
    # pushed up if its LAST baseline would not clear the floor.
    COL_DROP = 40 + 25 + 46 + 22      # scan -> trust1 -> trust2 -> or_type -> URL
    ty = qr_y + qr_size - 30
    shortfall = (floor + 10) - (ty - COL_DROP)
    if shortfall > 0:
        ty += shortfall
    assert ty <= block_top, (
        f"text column needs to start at {ty:.0f} but the content above ends at "
        f"{block_top:.0f} (tabs={tabs}); the page is out of room")
    pdf.setFillColor(SOFT)
    pdf.setFont("Helvetica", 14)
    pdf.drawString(tx, ty, c["scan"])
    ty -= 40
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(tx, ty, c["trust1"])
    ty -= 25
    pdf.drawString(tx, ty, c["trust2"])
    ty -= 46
    pdf.setFillColor(SOFT)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(tx, ty, c["or_type"])
    ty -= 22
    pdf.setFillColor(ACCENT)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(tx, ty, URL_DISPLAY)

    # The guarantee, checked against the value actually used rather than the
    # COL_DROP estimate above. If someone changes one of the four gaps, the
    # estimate goes stale and this still catches it.
    assert ty >= floor + 8, (
        f"the typed URL sits at y={ty:.0f} but the content floor is {floor:.0f} "
        f"(tabs={tabs}); it would be drawn inside the tear-off strip")

    if tabs:
        _tear_tabs(pdf, m, W, floor, TAB_H)

    # Footer: THREE stacked lines, left aligned, one idea each.
    #
    # 🔴 THE OLD LAYOUT OVERLAPPED, and not marginally. The identity line and the
    # contact line were drawn on the SAME baseline, one left-aligned and one
    # right-aligned, on the theory that contact is wanted only after someone has
    # decided to act and so must not compete with the QR. The theory is fine.
    # The arithmetic was never done. Measured at 12pt and 9.5pt against the
    # 490pt of usable width:
    #
    #     EN   329.5 + 271.0 = 600.5   ->  overlapping by 110.8pt
    #     ES   357.5 + 212.9 = 570.4   ->  overlapping by  80.8pt
    #
    # So the two strings ran through each other in the middle of the page, in
    # both languages, on every copy ever produced. Right-aligning something does
    # not make it fit; it only moves where the collision happens.
    #
    # Stacking removes the failure mode rather than tuning it. Nothing here
    # depends on two strings staying short, so no future copy edit can
    # reintroduce it, and the widths are asserted below in any case.
    #
    # A wrong address on this flyer is the failure the whole project is about,
    # so the invitation to report one keeps its own line rather than being
    # squeezed onto the identity line or dropped into the fine print.
    ident_y, contact_y, fine_y = m + 42, m + 27, m + 10
    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(0.8)
    pdf.line(m, m + 58, W - m, m + 58)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(m, ident_y, c["foot"])
    pdf.setFillColor(SOFT)
    pdf.setFont("Helvetica", 9.5)
    pdf.drawString(m, contact_y, c["contact"])
    pdf.setFont("Helvetica", 9)
    pdf.drawString(m, fine_y, c["fine"])

    # Fail the build rather than ship an overlap again. Every footer line is
    # left-aligned from the same margin, so "fits" is simply "narrower than the
    # text column". This is the check that would have caught the original.
    for label, text, font, size in (
            ("foot", c["foot"], "Helvetica-Bold", 12),
            ("contact", c["contact"], "Helvetica", 9.5),
            ("fine", c["fine"], "Helvetica", 9)):
        w = pdf.stringWidth(text, font, size)
        assert w <= W - 2 * m, (
            f"footer line {label!r} is {w:.0f}pt wide but only "
            f"{W - 2 * m:.0f}pt is available; shorten it in COPY[{lang!r}]")

    pdf.save()
    print(f"wrote {out.relative_to(REPO)}")


def _tear_tabs(pdf, m, W, top, height):
    """Vertical tear-off strip: the low-tech path for someone who sees this
    without a phone in hand, or with no data.

    The URL is set rotated, so the tab HEIGHT is the line length. At 7pt the
    address runs about 124pt, which is why the strip is 1.9in (137pt) rather
    than the 1.35in first tried, where every tab overflowed into the QR code.
    """
    n = 8
    usable = W - 2 * m
    tabw = usable / n
    bottom = top - height
    pdf.setStrokeColor(LINE)
    pdf.setLineWidth(0.7)
    pdf.setDash(2, 2)
    pdf.line(m, top, W - m, top)
    for i in range(1, n):
        pdf.line(m + i * tabw, bottom, m + i * tabw, top)
    pdf.setDash()
    pdf.setFillColor(ACCENT)
    pdf.setFont("Helvetica-Bold", 7)
    text_len = pdf.stringWidth(URL_DISPLAY, "Helvetica-Bold", 7)
    assert text_len < height, f"tab text {text_len:.0f}pt exceeds tab {height:.0f}pt"
    for i in range(n):
        pdf.saveState()
        # After rotate(90) the baseline runs upward and glyphs extend left, so
        # nudge right of center by half the cap height to sit centered in the tab.
        pdf.translate(m + i * tabw + tabw / 2 + 3.5,
                      bottom + (height - text_len) / 2)
        pdf.rotate(90)
        pdf.drawString(0, 0, URL_DISPLAY)
        pdf.restoreState()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="en", choices=sorted(COPY))
    ap.add_argument("--tabs", action="store_true",
                    help="add a tear-off strip (community boards, not clinic walls)")
    args = ap.parse_args()
    outdir = REPO / "advocacy" / "flyers"
    outdir.mkdir(exist_ok=True)
    suffix = "-tabs" if args.tabs else ""
    build(args.lang, outdir / f"flyer-{args.lang}{suffix}.pdf", tabs=args.tabs)
    if args.lang == "es":
        print("  ⚠️  Spanish copy is UNREVIEWED. Do not print until a native "
              "speaker has read it.")


if __name__ == "__main__":
    main()
