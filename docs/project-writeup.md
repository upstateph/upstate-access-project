# The Upstate Access Project — a short introduction

**One sentence:** A free, open public tool that measures how long it *actually* takes
people in Greenville County to reach essential services — on foot, by car, and by
Greenlink transit — and connects that access to pedestrian safety and equity data.

**Live site:** https://upstateph.github.io/upstate-access-project/ · **Author:** Nikhil Jain, DO, MPH

## Why this exists

South Carolina ranks **#4 in the nation for pedestrian danger** (Smart Growth
America, *Dangerous by Design* 2026), with 1,750 pedestrian deaths statewide from
2014–2024 — 182 of them in Greenville County. At the same time, directories that
list where clinics *are* say nothing about whether people can *get there*. This
project fills that gap with real travel-time computation instead of pins on a map.

## What it shows (key findings so far)

1. **Transit rarely connects people to care.** Only 41% of Greenville County's
   123 census tracts can reach a community health center (FQHC) with at most one
   Greenlink transfer, a 30-minute cap on any single wait, and a trip that exists
   from most departures in the hour — 73 tracts have no such trip at all.
2. **Where transit does connect, waiting dominates, and midday is the worst time
   to need it.** From downtown's Main Street, the nearest community health center
   (an FQHC Look-Alike) is a 14-minute walk — but the modeled transit trip takes
   about 50 minutes, 26 of them waiting. Across the day the median trip runs
   51 minutes at its best (weekday 8am) and 65 minutes at its worst (weekday
   midday): the hour when a routine appointment is most likely to be scheduled is
   the thinnest service of the day. Which tracts are reachable barely moves
   (a 2.4-point spread), so this is a frequency problem, not a coverage one.
3. **Walking routes to care overlap with where pedestrians die.** 70 of the
   county's 182 pedestrian deaths (38.5%) occurred within 150 meters of a modeled
   walking route to a community health center. **This claim has been withdrawn.**
   A null model refutes it: routing every tract to a *randomly chosen* health center
   captures more deaths (~59%), and at matched route length an arbitrary destination
   always overlaps more. The statistic mostly measures how much arterial road a route
   covers. The companion "every nearby death happened in darkness" claim was also
   withdrawn — 84.1% of all county pedestrian deaths occur in darkness versus 85.7%
   near these corridors, which is not a signal. Establishing a real link would require
   road-network exposure as the denominator.
4. **Access tracks income.** The lowest-income third of tracts averages a shorter
   walk to care but far higher transit dependence; the tool benchmarks every
   neighborhood against county demographics (income, race/ethnicity, and — coming
   with the next data refresh — households without a vehicle).

## What the tool does

- **Statewide tracker** — pedestrian fatality trends and rankings for all 46 SC
  counties (NHTSA FARS), with income and demographic overlays (Census ACS).
- **Greenville County access map** — modeled walk / drive / transit time from every
  census tract and ZIP to the nearest community health center, with time-of-day
  analysis and the crash-corridor overlay described above.
- **Address lookup (pilot)** — type an address, pick a service type (health
  centers, hospitals, urgent care, pharmacies, government services, food
  assistance), and get real travel times plus a neighborhood equity snapshot.
  Privacy-first: no accounts, no address logging, aggregate statistics only ever
  published above a k-anonymity threshold.

## Methods, briefly

Greenlink GTFS schedule data powers a transit router (walk + wait + ride + up to
one transfer, a 30-minute cap on any single wait, and the median taken over
departures sampled every 10 minutes across an hour — a single departure instant is
a coin flip on where it lands in the headway). The address lookup
computes walking and driving times with real road-network routing (OSRM), as do
the crash-corridor walking routes; the county-wide tract and ZIP maps use a
straight-line estimate (3 mph walking, 25 mph effective driving, 1.3× detour
factor) so the whole county can be modeled without hammering a public routing
server — each map labels which method produced it. Facility locations come from HRSA, CMS, and
NPPES public registries; demographics from Census ACS 2024 5-year; crash records
from NHTSA FARS (2014–2024, incident-level). Everything is modeled from public
data and labeled as such — modeled estimates, not observed trips — and the full
methodology and code are open at https://github.com/upstateph/upstate-access-project.

## What's next

Stigma-sensitive service categories (reproductive health, HIV care, substance-use
treatment) are scaffolded but withheld until every facility address is manually
verified — for those categories, accuracy is a safety issue. The rollup design
extends to other Upstate counties, and the analysis is structured to plug directly
into Greenlink's Transit Development Plan conversation and Greenville's Pedestrian
Safety Action Plan.

*Modeled estimates from public data — verify critical details with providers.
Feedback and collaboration welcome: [EMAIL].*
