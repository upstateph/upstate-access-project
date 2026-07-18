# Manual seed lists for safety-sensitive categories

Categories like **abortion clinics, reproductive/women's health, HIV/Ryan White care,
and substance-use treatment** are stigma- and safety-sensitive. Per the project's
privacy design (spec §6), an incorrect address for these is a *safety* issue, not just
a UX bug — so they are **never auto-scraped**. They can only be populated from a CSV of
addresses **you have personally verified**.

## How to add a verified sensitive category

1. Fill in a CSV with this header (see `template.csv`):
   ```
   name,address,city,state,zip,phone
   ```
   Verify **every** address against the provider directly before adding it.

2. Geocode it into the standard facilities file:
   ```bash
   python seed_facilities.py reproductive_health data-pipeline/seeds/reproductive_health.csv
   ```

3. Rebuild the manifest:
   ```bash
   python build_categories_manifest.py
   ```
   The category now has data but is **still withheld** from the public menu.

4. Only when you are confident every address is correct, clear the gate: set
   `verification_required` to `False` (or remove it) for that category in
   `categories.py`, then rebuild the manifest. Now it appears in the public menu.

> These seed CSVs are **gitignored** by default — verified sensitive-facility lists
> should be handled deliberately, not committed casually. Move a file out of `seeds/`
> or adjust `.gitignore` if you intend to track it.
