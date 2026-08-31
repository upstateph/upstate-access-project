# Privacy & ethics by design

This project handles data about where people seek care. Several Tier 2 destination
categories, substance-use treatment, HIV/Ryan White care, reproductive health,
carry real stigma and safety risk if a search were ever tied to an identity. The
design below is a hard requirement, not a nice-to-have.

## Principles

1. **No accounts, no login.** Nothing about a user is needed to run a lookup.
2. **No server-side logging of searched addresses.** Geocoding and routing happen
   without persisting the input address anywhere. If a serverless lookup function is
   used, it must not write the address to logs, analytics, or storage.
3. **Aggregated views only, never individual-level.** The dashboard and equity panel
   only ever display statistics computed over groups.
4. **k-anonymity threshold.** Suppress any tract-level statistic computed from fewer
   than **k = 25** lookups. 25 is a placeholder to tune once real usage volume is
   known (spec §6, §10). The suppression logic lives with the aggregation code
   (Phase 4) and must fail *closed*: if the count can't be verified, suppress.
5. **Safety-critical address accuracy.** For reproductive health and HIV/Ryan White
   facilities, every address is verified manually before launch, and that
   verification is **recorded and expires** (see below). An error here is a safety
   issue, not a UX bug.

## Where each principle is enforced

| Principle | Enforced in | Status |
|---|---|---|
| No accounts / no login | whole app design | ✅ Tier 1 static; Tier 2 lookup has no auth |
| No address logging | Phase 3 lookup server | ✅ POST body only; request logging disabled (verified) |
| Aggregated only | dashboard + equity panel | ✅ Tier 1 shows county-level only |
| k = 25 suppression | Phase 4 rollup | ✅ `engine/aggregate.py` (fail-closed; tested) |
| Verified sensitive addresses | Phase 3 data seed | n/a for FQHC; ⬜ before sensitive categories |

**Phase 3 lookup server enforcement:** `lookup-tool/server.py` takes the address in a
POST body (never a query string), overrides `log_message` to suppress all request
logging, and persists nothing about the request except the de-identified usage record
below. FQHC (the launch category) is not stigma-sensitive; the manual
address-verification requirement applies before adding substance-use, HIV/Ryan
White, or reproductive-health categories.

## The sensitive-category gate, and why verification expires

Stigma-sensitive categories (abortion, reproductive/women's health, HIV/Ryan White
care, substance-use treatment) are enforced in **`engine/facilities.py`**, not in the
UI menu; an earlier version filtered only the `/api/categories` menu, so the scoring
endpoint would serve any category whose data file existed on disk. The gate now:

- runs **before** the file-existence check, so a response can never reveal whether a
  seed file for a sensitive category exists;
- **fails closed**: an unreadable manifest still blocks every sensitive key;
- requires an explicit, deliberate edit (`verification_required`) to open;
- requires the verification to be **current**.

Verification is a record, not an assertion. `seed_facilities.py` **rejects** any
sensitive-category row lacking `verified_on` (ISO date, not in the future) and
`verification_method`, so the published file cannot claim more than was checked. A
missing, unparseable, or future date all count as unverified.

Freshness is enforced at request time: once the **oldest** `verified_on` in a
category passes `VERIFICATION_MAX_AGE_DAYS` (default 180), the category is withdrawn
from public serving automatically, even if it was previously cleared and even if the
manifest wasn't rebuilt. Clinic locations and which site of an organization actually
provides a service both change; making freshness depend on someone remembering to
check is the failure mode this prevents. `check_verification.py` reports status and
exits non-zero when anything is stale, so it can run on a schedule.

Note also that verification must cover the **geocoded coordinate**, not just the
address text: routing uses the coordinate, and a correct address can geocode to a
street centroid or the wrong side of a block.

## Third parties that receive the address or coordinates

Computing a result requires two external services, and honesty demands naming them
(the UI does too):

1. **US Census Geocoder**: receives the typed address as a GET query string
   (`engine/geocode.py`). Census's servers can log that request like any web
   request; we do not control their retention. This is inherent to geocoding
   without shipping a local address database.
2. **OSRM public demo servers** (routing.openstreetmap.de, FOSSGIS): receive the
   geocoded coordinates (not the address text) in GET URLs for walk/drive routing
   (`engine/osrm.py`). Coordinates of a home are equivalent to the address, so this
   matters. **Before any real public launch, self-host OSRM** (`OSRM_CAR_URL` /
   `OSRM_FOOT_URL` env vars are already supported) or set `OSRM_DISABLE=1` to fall
   back to offline estimates. Error messages from either service are never echoed
   to clients (`GeocoderUnavailable` carries a fixed string; handlers return only
   exception class names).

Residual metadata note: the telemetry file stores no timestamps, but its
filesystem mtime reveals when the *most recent* lookup happened and line order
preserves sequence. Local-only file, small risk; a shuffle-on-rollup would remove
ordering if it ever matters.

## De-identified usage telemetry

To eventually replace the modeled rollup with observed usage (principle 4), each
**successful** lookup appends one record to a local, gitignored file
(`data/usage/lookups.jsonl`): the **service category, tract FIPS, and travel
times**, nothing else. Explicitly excluded: the searched address, the matched
address, coordinates, the chosen facility, any timestamp, and anything about the
requester. The record passes through `engine/aggregate.anonymize_result`, the same
fail-closed reduction used everywhere else.

- The raw counts file never leaves the machine and is never published; only the
  k-anonymity-suppressed rollup (`build_usage_rollup.py`) may be shared.
- The UI discloses this ("an anonymous, area-level count … is kept").
- Set `UAP_NO_TELEMETRY=1` to disable recording entirely.
- No timestamp is stored by design: it adds re-identification surface (a rare
  category + small tract + known search time could narrow to a person) and the
  rollup doesn't need it.

## Tier 1 note

The statewide dashboard uses only NHTSA FARS (already public, no PII) and Census ACS
(already aggregated to county/tract). It introduces no privacy surface of its own.
County-level FARS pedestrian-fatality counts are already published; we display them
as-is. No small-count suppression is applied to FARS counts on the statewide view
because these are official published figures, but see `docs/data-sources.md` for the
caveat about interpreting small annual county counts.
