"""Shared helpers for the Upstate Access Project data pipeline.

Path conventions, caching, and small utilities used by the fetch/build scripts.
No PII passes through here — Phase 0/1 data is all public and aggregated.
"""
from __future__ import annotations

import json
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
# repo/
#   data-pipeline/   <- this file lives here
#   data/raw/        <- cached raw pulls (gitignored)
#   data/processed/  <- small JSON outputs (tracked)
#   dashboard/data/  <- copy of processed JSON the static site reads
PIPELINE_DIR = Path(__file__).resolve().parent
REPO_DIR = PIPELINE_DIR.parent
DATA_DIR = REPO_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
DASHBOARD_DATA_DIR = REPO_DIR / "dashboard" / "data"

# South Carolina
SC_STATE_FIPS = "45"

# Canonical SC county FIPS (5-digit GEOID) -> county name. All 46 counties.
# Lets the dashboard label counties even before the ACS pull runs, and is the
# authoritative name source (FARS pre-2018 lacks COUNTYNAME).
SC_COUNTIES = {
    "45001": "Abbeville", "45003": "Aiken", "45005": "Allendale",
    "45007": "Anderson", "45009": "Bamberg", "45011": "Barnwell",
    "45013": "Beaufort", "45015": "Berkeley", "45017": "Calhoun",
    "45019": "Charleston", "45021": "Cherokee", "45023": "Chester",
    "45025": "Chesterfield", "45027": "Clarendon", "45029": "Colleton",
    "45031": "Darlington", "45033": "Dillon", "45035": "Dorchester",
    "45037": "Edgefield", "45039": "Fairfield", "45041": "Florence",
    "45043": "Georgetown", "45045": "Greenville", "45047": "Greenwood",
    "45049": "Hampton", "45051": "Horry", "45053": "Jasper",
    "45055": "Kershaw", "45057": "Lancaster", "45059": "Laurens",
    "45061": "Lee", "45063": "Lexington", "45065": "McCormick",
    "45067": "Marion", "45069": "Marlboro", "45071": "Newberry",
    "45073": "Oconee", "45075": "Orangeburg", "45077": "Pickens",
    "45079": "Richland", "45081": "Saluda", "45083": "Spartanburg",
    "45085": "Sumter", "45087": "Union", "45089": "Williamsburg",
    "45091": "York",
}

# Census ACS "jam"/sentinel values that mean "not available/suppressed".
# These must be treated as null before any arithmetic (never averaged in).
CENSUS_SENTINELS = {
    -666666666,
    -999999999,
    -888888888,
    -222222222,
    -333333333,
    -555555555,
}


def ensure_dirs() -> None:
    """Create the data directories if they don't exist yet."""
    for d in (RAW_DIR, PROCESSED_DIR, DASHBOARD_DATA_DIR):
        d.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, obj, *, label: str | None = None) -> None:
    """Write `obj` as pretty JSON and print a short confirmation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
    what = label or path.name
    print(f"  wrote {what} -> {path.relative_to(REPO_DIR)}")


def read_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def clean_census_value(raw):
    """Convert a raw Census API string estimate to a float, or None.

    All ACS API values arrive as strings; sentinel values like -666666666 mean
    'not available' and must become None rather than a huge negative number.
    """
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if int(val) in CENSUS_SENTINELS:
        return None
    return val
