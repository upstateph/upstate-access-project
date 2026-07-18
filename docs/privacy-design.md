# Privacy & ethics by design

This project handles data about where people seek care. Several Tier 2 destination
categories — substance-use treatment, HIV/Ryan White care, reproductive health —
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
   (Phase 4) and must fail *closed* — if the count can't be verified, suppress.
5. **Safety-critical address accuracy.** For reproductive health and HIV/Ryan White
   facilities, every address is verified manually before launch. An error here is a
   safety issue, not a UX bug.

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
logging, and persists nothing. FQHC (the launch category) is not stigma-sensitive; the
manual address-verification requirement applies before adding substance-use, HIV/Ryan
White, or reproductive-health categories.

## Tier 1 note

The statewide dashboard uses only NHTSA FARS (already public, no PII) and Census ACS
(already aggregated to county/tract). It introduces no privacy surface of its own.
County-level FARS pedestrian-fatality counts are already published; we display them
as-is. No small-count suppression is applied to FARS counts on the statewide view
because these are official published figures, but see `docs/data-sources.md` for the
caveat about interpreting small annual county counts.
