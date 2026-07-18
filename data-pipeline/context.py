#!/usr/bin/env python3
"""Emit framing/context for the Tier 1 dashboard from Smart Growth America's
*Dangerous by Design 2026* report.

Per spec §4, this report is used for state-ranking context and national framing,
NOT as a raw data source. All figures here are transcribed from the published 2026
edition and its coverage; update this file when a new edition lands.

Verified July 2026 against Smart Growth America's Dangerous by Design 2026 and
Post & Courier's coverage. Cross-check: SGA reports 893 SC pedestrian deaths
2020-2024 — the FARS pipeline in fetch_fars.py independently sums to the same 893
for those years, which validates both.

Usage:
    python context.py
"""
from __future__ import annotations

from common import PROCESSED_DIR, ensure_dirs, write_json

CONTEXT = {
    "report": "Dangerous by Design 2026",
    "publisher": "Smart Growth America",
    "edition_year": 2026,
    "coverage_period": "2020-2024",
    "state": "South Carolina",
    "state_rank": 4,
    "state_rank_note": (
        "4th most dangerous state for people walking (after New Mexico, Louisiana, "
        "and Arizona). Down one spot from the prior edition, but a better rank does "
        "NOT mean safer roads — SC fatalities rose; other states' rates rose faster."
    ),
    "state_deaths_2020_2024": 893,
    "state_annual_deaths_per_100k": 3.37,
    "metros": [
        {"name": "Charleston-North Charleston", "national_rank": 12},
        {"name": "Columbia", "national_rank": 18},
    ],
    "framing": (
        "South Carolina consistently ranks among the most dangerous states in the "
        "nation for people walking. Pedestrian deaths are concentrated in, but not "
        "limited to, its largest metros; the county view below shows the statewide "
        "distribution."
    ),
    "sources": [
        {
            "title": "Dangerous by Design 2026",
            "url": "https://www.smartgrowthamerica.org/knowledge-hub/resources/dangerous-by-design-2026-americas-most-dangerous-places-for-people-walking-are-still-getting-more-dangerous/",
        },
        {
            "title": "SC drops to 4th most-dangerous state for pedestrians, but fatalities are on the rise (Post & Courier)",
            "url": "https://www.postandcourier.com/news/crime/south-carolina-deadliest-pedestrian-states-charleston-columbia/article_d5037bb9-e288-473e-a800-8c91c29ccb0b.html",
        },
    ],
}


def main() -> None:
    ensure_dirs()
    write_json(PROCESSED_DIR / "context.json", CONTEXT, label="Dangerous by Design context")
    print("Done.")


if __name__ == "__main__":
    main()
