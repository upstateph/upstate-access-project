# The Upstate Access Project — a short introduction

**One sentence:** A free, open public tool that measures how long it *actually* takes
people in Greenville County to reach essential services — on foot, by bike, by car,
and by Greenlink transit — benchmarked by income and race.

**The working tool:** https://upstate-access-beta.onrender.com (free hosting, so
the first load can take up to a minute while the server wakes)
**Project pages / source:** https://upstateph.github.io/upstate-access-project/
**Author:** Nikhil Jain, DO, MPH

## Why this exists

Directories that list where clinics *are* say nothing about whether people can
*get there*. This project fills that gap with real travel-time computation
instead of pins on a map: routed on the actual road network and against
Greenlink's published timetable, and benchmarked against county demographics.

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
3. **Access tracks income.** The lowest-income third of tracts averages a shorter
   walk to care but far higher transit dependence; the tool benchmarks every
   neighborhood against county demographics (income, race/ethnicity, and — coming
   with the next data refresh — households without a vehicle).

## What the tool does

- **Greenville County access map** — modeled walk / drive / transit time from every
  census tract and ZIP to the nearest community health center, with time-of-day
  and route-level frequency analysis.
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
computes walking and driving times with real road-network routing (OSRM);
the county-wide tract and ZIP maps use a
straight-line estimate (3 mph walking, 25 mph effective driving, 1.3× detour
factor) so the whole county can be modeled without hammering a public routing
server — each map labels which method produced it. Facility locations come from HRSA, CMS, and
NPPES public registries; demographics from Census ACS 2024 5-year. Everything is modeled from public
data and labeled as such — modeled estimates, not observed trips — and the full
methodology and code are open at https://github.com/upstateph/upstate-access-project.

## What's next

Stigma-sensitive service categories (reproductive health, HIV care, substance-use
treatment) are scaffolded but withheld until every facility address is manually
verified — for those categories, accuracy is a safety issue. The rollup design
extends to other Upstate counties, and the analysis is structured to plug directly
into Greenlink's Transit Development Plan conversation.

**A note on scope.** Earlier versions of this project included a statewide
pedestrian-safety tracker (NHTSA FARS) and a crash-corridor overlay; a corridor
claim from that analysis was publicly withdrawn after a null-model check. That
entire line of work was removed from the site on 2026-08-27 and is planned as a
separate future project (preserved in `archive/pedestrian-safety-tracker/`). No
travel-time figure here is derived from crash data.

*Modeled estimates from public data — verify critical details with providers.
Feedback and collaboration welcome: nikhilajain@gmail.com.*
