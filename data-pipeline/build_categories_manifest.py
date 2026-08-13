#!/usr/bin/env python3
"""Publish dashboard/data/categories.json — the menu the lookup UI reads.

Combines the category registry (categories.py) with a scan of which categories
actually have data (data/processed/facilities_<key>.json). Sensitive categories that
aren't verified are marked so the UI can gate them.

Usage:
    python build_categories_manifest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from categories import CATEGORY_REGISTRY
from common import DASHBOARD_DATA_DIR, PROCESSED_DIR, ensure_dirs, read_json, write_json
from engine.facilities import verification_status  # noqa: E402


def facility_count(key: str) -> int | None:
    """Count only the records the engine will actually serve.

    Must apply the same filters as engine.facilities, or the menu advertises a
    count the lookup cannot deliver — "Community health center (11)" when six of
    those are mobile units at a dispatch base and a dental-only site.
    """
    path = PROCESSED_DIR / f"facilities_{key}.json"
    if not path.exists():
        return None
    payload = read_json(path)
    facs = payload["facilities"] if isinstance(payload, dict) else payload
    required = CATEGORY_REGISTRY.get(key, {}).get("require_service_line")
    servable = [f for f in facs
                if f.get("routable") is not False
                and not (required and f.get("service_lines") is not None
                         and required not in f["service_lines"])]
    return len(servable)


def non_routable_note(key: str) -> str | None:
    """Describe destinations that exist but are excluded from travel times."""
    path = PROCESSED_DIR / f"facilities_{key}.json"
    if not path.exists():
        return None
    payload = read_json(path)
    facs = payload["facilities"] if isinstance(payload, dict) else payload
    mobile = [f for f in facs if f.get("mobile")]
    if not mobile:
        return None
    hours = [float(f["operating_hours_per_week"]) for f in mobile
             if f.get("operating_hours_per_week")]
    span = (f" ({min(hours):.0f}–{max(hours):.0f} hours a week)"
            if len(hours) > 1 and min(hours) != max(hours) else "")
    n = len(mobile)
    subject = f"{n} mobile units also serve" if n != 1 else "1 mobile unit also serves"
    return (f"{subject} this county{span}, and {'are' if n != 1 else 'is'} not "
            "included in these travel times — HRSA publishes only their dispatch "
            "address, not where they park. Ask the health center for the schedule.")


def main() -> None:
    ensure_dirs()
    # Members must be evaluated before the composites that reference them.
    ready_members: dict[str, bool] = {}
    for key, meta in CATEGORY_REGISTRY.items():
        if meta.get("members"):
            continue
        n = facility_count(key)
        cleared = (n or 0) > 0 and not (meta.get("sensitive") and meta.get("verification_required"))
        vs = verification_status(key) if meta.get("sensitive") else None
        ready_members[key] = bool(cleared and not (vs and vs["stale"]))

    cats = []
    for key, meta in CATEGORY_REGISTRY.items():
        members = meta.get("members") or []
        if members:
            live = [m for m in members if ready_members.get(m)]
            withheld = [m for m in members if not ready_members.get(m)]
            counts = [facility_count(m) or 0 for m in live]
            cats.append({
                "key": key, "label": meta["label"], "group": meta.get("group", "Other"),
                "sensitive": False, "verification_required": False,
                "source": meta.get("source"), "members": members,
                "members_live": live, "members_withheld": withheld,
                "available": bool(live), "count": sum(counts) or None,
                # Servable as soon as one member is. Withheld members are absent
                # from results, so the UI must SAY so — a search that silently
                # omits every treatment center reads as "there are none nearby".
                "public_ready": bool(live),
                # A composite's caveats are its members' caveats — they are what
                # the user actually gets — plus anything about withheld members.
                "coverage_note": " ".join(filter(None, [
                    ("Does not yet include substance-use treatment sites — those "
                     "addresses are being verified individually before publication."
                     if "substance_use" in withheld else None),
                    *[non_routable_note(m) for m in live],
                ])) or None,
            })
            continue

        n = facility_count(key)
        available = n is not None and n > 0
        sensitive = bool(meta.get("sensitive"))
        cleared = available and not (sensitive and meta.get("verification_required"))
        # Sensitive categories additionally need CURRENT verification: a list checked
        # once and left to rot is exactly the failure this gate exists to prevent.
        vs = verification_status(key) if sensitive else None
        stale = bool(vs and vs["stale"])
        entry = {
            "key": key,
            "label": meta["label"],
            "group": meta.get("group", "Other"),
            "sensitive": sensitive,
            "verification_required": bool(meta.get("verification_required")),
            "source": meta.get("source"),
            "available": available,
            "count": n,
            # Load-time filter: the engine drops records lacking this service line.
            "require_service_line": meta.get("require_service_line"),
            # Excluded-but-real destinations get said out loud. A mobile unit that
            # is simply absent looks like it does not exist; naming it turns a
            # silent omission into a question the user can go ask the operator.
            "coverage_note": non_routable_note(key),
            # Backing store for a composite: has its own gate, but is not offered
            # as its own menu option.
            "hidden": bool(meta.get("hidden")),
            # Offered publicly only if it has data, is non-sensitive or explicitly
            # cleared, AND (for sensitive categories) its verification is current.
            "public_ready": cleared and not stale,
        }
        if sensitive:
            # Publishable freshness signal — dates and counts only. The verifier's
            # name stays in the server-side facilities file, never in this manifest.
            entry["verification"] = {
                "oldest_verified_on": vs["oldest_verified_on"],
                "age_days": vs["age_days"],
                "stale": stale,
                "reason": vs["reason"],
            }
            if stale and cleared:
                print(f"  WITHHELD {key}: {vs['reason']}")
        cats.append(entry)

    out = {
        "county": "Greenville County",
        "note": ("Sensitive categories are scaffolded but withheld from the public menu "
                 "until every address is verified (spec §6)."),
        "categories": cats,
    }
    write_json(DASHBOARD_DATA_DIR / "categories.json", out, label="categories.json")
    # Report the MENU, not just the ready flag — a hidden member is public_ready
    # but is not an option anyone can pick, and conflating the two makes the menu
    # look one item longer than it is.
    menu = [c["key"] for c in cats if c["public_ready"] and not c.get("hidden")]
    backing = [c["key"] for c in cats if c["public_ready"] and c.get("hidden")]
    scaffolded = [c["key"] for c in cats if c["sensitive"]]
    print(f"Menu options ({len(menu)}): {', '.join(menu) or '(none)'}")
    if backing:
        print(f"Backing a composite (not offered alone): {', '.join(backing)}")
    print(f"Sensitive scaffolded (withheld): {', '.join(scaffolded)}")
    for c in cats:
        if c.get("members_withheld"):
            print(f"  {c['key']}: withheld member(s) {', '.join(c['members_withheld'])}")


if __name__ == "__main__":
    main()
