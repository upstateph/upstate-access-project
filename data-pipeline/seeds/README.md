# Manual seed lists for safety-sensitive categories

Categories like **abortion clinics, reproductive/women's health, HIV/Ryan White care,
and substance-use treatment** are stigma- and safety-sensitive. Per the project's
privacy design (spec §6), an incorrect address for these is a *safety* issue, not just
a UX bug, so they are **never auto-scraped**. They can only be populated from a CSV of
addresses **you have personally verified**.

## Substance-use treatment has a head start

`substance_use` is a **priority** category, not a reluctant one; people with SUD are
core to who this tool is for, and opioid treatment programs require near-daily dosing
visits, so travel burden directly drives whether someone stays in treatment. It is
gated only because a wrong address here is a safety problem.

So the candidate list is assembled for you, and only the calling is left:

```bash
python build_sud_candidates.py     # -> seeds/substance_use_candidates.csv
```

It merges the **SAMHSA N-SUMHSS National Directory** (state-licensed facilities, with
service codes telling you which sites are OTP/methadone vs outpatient counseling)
with **NPPES addiction-taxonomy organizations** (counseling practices too small to be
state-licensed). The `_services` column is there to prioritize your calls: dosing
sites matter most, because those are the daily trips.

The three verification columns are left blank on purpose: `seed_facilities.py`
rejects rows without them, so the worksheet cannot accidentally become a published
list. Nothing in it reaches the public menu until you have made the calls.

Note that `substance_use` is **not offered as its own menu option**. It is served
through the `behavioral_health` composite alongside `mental_health`, so nobody has to
select "Substance-use treatment" from a visible dropdown to use it. Each member keeps
its own gate; see `engine/facilities.py`.

## How to add a verified sensitive category

1. Fill in a CSV with this header (see `template.csv`):
   ```
   name,address,city,state,zip,phone,verified_on,verified_by,verification_method
   ```
   Verify **every** address against the provider directly before adding it, and
   record how and when: `verified_on` is an ISO date (`YYYY-MM-DD`, not in the
   future) and `verification_method` says what you actually did (e.g. "phone call
   to clinic front desk"). Rows missing either are **rejected**, not seeded; the
   file records that a human checked, rather than asserting it.

   What to confirm on the call, beyond the street address:
   - that **this specific site** provides the service (multi-site organizations
     frequently list an administrative office that provides no clinical care,
     common with Ryan White subrecipients);
   - suite/floor and any entrance detail a person on foot would need.

2. Geocode it into the standard facilities file:
   ```bash
   python seed_facilities.py reproductive_health data-pipeline/seeds/reproductive_health.csv
   ```

3. Rebuild the manifest:
   ```bash
   python build_categories_manifest.py
   ```
   The category now has data but is **still withheld** from the public menu.

4. **Check the geocoded coordinates**, not just the addresses. `seed_facilities.py`
   prints a lat/lon per row, and everything downstream (walk time, transit
   itinerary, nearest-facility ranking) routes on that coordinate; a correct
   address can still geocode to a street centroid or the wrong side of a block.

5. Only when you are confident every address *and coordinate* is correct, clear the
   gate: set `verification_required` to `False` (or remove it) for that category in
   `categories.py`, then rebuild the manifest. Now it appears in the public menu.

## Verifications expire

A list checked once and never revisited rots silently, so freshness is enforced
rather than trusted. A sensitive category is **withdrawn from public serving
automatically** once its oldest `verified_on` passes
`engine.facilities.VERIFICATION_MAX_AGE_DAYS` (default **180 days**; override with
`UAP_VERIFICATION_MAX_AGE_DAYS`). This is checked at request time, so it applies even
if the manifest hasn't been rebuilt, and the oldest entry governs the whole category.

```bash
python check_verification.py                  # status report; exit 1 if anything stale
python check_verification.py --max-age-days 90
```

Run it on a schedule. To restore a stale category: re-verify, update `verified_on` in
the CSV, then re-run `seed_facilities.py` and `build_categories_manifest.py`.

> These seed CSVs are **gitignored** by default: verified sensitive-facility lists
> should be handled deliberately, not committed casually. Move a file out of `seeds/`
> or adjust `.gitignore` if you intend to track it.
