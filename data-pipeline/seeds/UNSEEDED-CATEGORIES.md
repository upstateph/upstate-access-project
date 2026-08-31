# Registered categories with no bulk source: what each one needs

Four categories were registered on 24 Aug and are deliberately `available: false`.
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

1. **`free_clinic`**: this week's calls established that acceptance, not
   distance, decides where people go. Free clinics are the other half of the
   "will see you regardless" destination set; right now the tool only knows the
   FQHC half. Greenville Free Medical Clinic is already confirmed present in
   NPPES under "Voluntary or Charitable", so this is verification work rather
   than discovery.
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
