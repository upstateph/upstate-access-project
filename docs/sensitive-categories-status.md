# The four withheld categories: where each one actually stands

Status as of 2 September 2026. This exists because "why are these excluded?" is a
reasonable question with a specific answer per category, and the general answer
("they're sensitive") is not good enough to act on.

| Category | Candidate addresses | Verified by a human | Live? |
|---|---|---|---|
| `hiv_ryan_white` | 3 | 2 | no |
| `reproductive_health` | 7 | 1 | no |
| `substance_use` | 41 | 0 | no |
| `abortion` | 0 | 0 | no |

**`reproductive_health` gained a row on 2 Sep**, executing the 31 Aug decision in
`abortion-category-options.md`: do not build an `abortion` category, list
Greenville Women's Clinic as the reproductive health facility it is. That
decision had been recorded and never carried out, so the facility the whole
"map the place, not the procedure" argument depends on was in no candidate list
at all. It is now a candidate, unverified like the rest. **Its address is
deliberately not written here**; it lives only in the gitignored seed CSV.

**Two of those seven are excluded and will never be called.** Planned Parenthood
in Columbia and Asheville fail the rule set on 2 Sep: an out-of-county service is
listed only when it is genuinely the nearest of its category, and four in-county
reproductive-health providers are nearer for every address in Greenville County.
They are **marked in the seed CSV rather than deleted**, so the reasoning survives
where the next person looks, and their `verified_on` stays blank permanently.

So the table counts candidates, not work: **seven rows, five callable.**

**48 of 51 candidate addresses have never been checked by a person.** That is the
operative reason, not squeamishness. For these categories a wrong address is a
safety problem rather than a bad user experience: someone who takes an hour-long
bus trip to an address that moved has lost a day they may not have, and in three
of the four categories has also been seen looking.

## Per category

**`hiv_ryan_white`.** Three candidates, two verified. Closest to publishable of
the four, and still blocked on the question below rather than on data.

**`reproductive_health`.** Seven candidates, one verified: the Greenville Free
Medical Clinic, confirmed by a named person on the phone on 3 Sep 2026. That is
one row, not a milestone, and it does not start a countdown to launch. This
category stays withheld even if all seven clear, because `verification_required`
in the registry forces `cleared` to false in `build_categories_manifest.py`
whatever the dates say. Opening it is a separate, deliberate edit, not something
verification accumulates its way into. **The specific hazard
here is crisis pregnancy centers**, which present as reproductive health
providers, appear in the same searches and directories, and do not provide the
services someone is looking for. Any automated population of this category will
pull them in. That is an argument against ever auto-sourcing it, not just against
publishing today.

**`substance_use`.** Forty-one candidates, none verified, the largest list and
the least verified. Also the category where a listed "administrative office that
provides no clinical care" is most common, which the seeds README already flags.

**`abortion`.** No candidate list at all.

## On abortion specifically, correcting a reasonable assumption

The assumption that Greenville County has no abortion facilities is **wrong**.
South Carolina enforces a six-week ban (the Fetal Heartbeat and Protection from
Abortion Act, upheld by the state Supreme Court in August 2023), and as of late
2025 the state has **three** abortion clinics: Charleston, Columbia, and
**Greenville**. Planned Parenthood South Atlantic and Greenville Women's Clinic
operate them.

So the category would not be empty. It would contain roughly one facility, and
that changes the risk calculation rather than removing it:

- **Timing is the whole problem.** Under a six-week limit, a wrong or stale
  address does not cost an inconvenience, it can cost eligibility.
- **A one-entry category is a pointer to a named clinic.** Publishing a map layer
  whose entire content is "here is the abortion provider" is a different act from
  publishing a layer of 106 grocery stores, whatever the underlying address's
  public availability.
- **The likeliest failure is mis-listing, not under-listing.** A crisis pregnancy
  center rendered as an abortion provider would send someone somewhere that will
  not help and will cost them days.

None of that is a decision this document makes. It is the reason the decision
should be made deliberately by people who work in this field.

## What would change any of this

Not a data fix. A judgment, then verification, in that order:

1. **The judgment**, which is on Wednesday's agenda for the QWC conversation:
   does publishing these locations help people find care, or expose the people
   using them? A no settles it. A yes moves a category from *closed* to *open
   pending verification*, which is not the same as live.
2. **Then the phone calls.** Forty-eight addresses, one at a time, and the
   verification expires and re-blocks automatically, which is already enforced in
   `engine/facilities.py`.

**Nothing here ships on inference.** The categories with no verified addresses
stay withheld regardless of how the judgment lands.
