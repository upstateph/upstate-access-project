# Registered categories with no bulk source: what each one needs

**`free_clinic` is done as of 31 Aug 2026** and is live in the menu: five SC Free
Clinic Association member sites, seeded by `fetch_free_clinics.py`. Three remain
below.

Four categories were registered on 24 Aug as `available: false`.
They are **not sensitive**: none carries the being-seen risk that gates abortion,
HIV care and substance-use treatment. They are simply unavailable in any
machine-readable feed, so each needs a seed list built by hand.

**Every one was checked against NPPES before being scaffolded.** The dead ends are
recorded so nobody repeats them.

| Category | Why NPPES failed | What it needs |
|---|---|---|
| `free_clinic` | "Voluntary or Charitable" returns 12 orgs county-wide: one free clinic, plus churches, home-care agencies, a children's charity | SC Free Clinic Association member list; NPPES term is a *candidate* source, not a category |
| `health_department` | "Public Health or Welfare" returns COSTCO, CVS PHARMACY and "STATE OF SOUTH CAROLINA" | SC DPH published county locations, small list, a handful of sites |
| `wic` | Absent entirely; WIC clinics are a state program, not enumerated providers | SC DPH WIC clinic directory |
| `community_mental_health` | The taxonomy exists and 58 records carry it, but NPPES returns zero for the exact query string | Either SC DMH's own list, or a broad `Clinic/Center` pull with a post-filter, a fetcher change, not config |

## Ranked by value, not by ease

1. ~~**`free_clinic`**~~ **DONE 31 Aug 2026.** Seeded from the SC Free Clinic
   Association member directory, not NPPES: five sites, of which three are
   satellites open one afternoon a week. That last fact turned out to matter more
   than the addresses, because a travel-time answer that omits it sends someone on
   an hour-long bus trip to a locked door, so every record carries its published
   hours and the category ships with a coverage_note. Two phone numbers are stored
   blank on purpose: the association lists the Greer and Simpsonville satellites
   with an 843 Lowcountry area code against an 864 parent clinic, which is almost
   certainly a typo on their site. **Verify those two by phone before anyone
   relies on them.**
2. **`wic`**: mandatory in-person visits, income-eligible by definition, and the
   caregivers are disproportionately without a car. Small, stable list.
3. **`community_mental_health`**: takes everyone, unlike the private practices
   in the current behavioral-health count. Needs the fetcher change.
4. **`health_department`**: few sites, easy, lower marginal value since the
   services overlap what is already mapped.

## The rule that applies to all four

**A category with no data is absent from the menu, not shown empty.** The
manifest already enforces this. Do not publish any of them with a partial list:
a category that shows three of eleven free clinics is worse than one that shows
none, because absence reads as "there are none nearby".
