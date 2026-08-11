# Pedestrian safety & health-center access in Upstate South Carolina
### A data brief from the Upstate Access Project

*Generated from NHTSA FARS, Census/HRSA/Greenlink data, and Smart Growth America's
Dangerous by Design. Figures regenerate from the pipeline; see `docs/data-sources.md`.*

---

## The problem, in numbers

- **South Carolina is the #4 most dangerous state in the nation for people
  walking** (Dangerous by Design 2026, Smart Growth America),
  at 3.37 pedestrian deaths per 100,000 residents per year.
- **1,750 people were killed while walking in South Carolina from 2014–2024** (NHTSA FARS),
  up 46% over the period.
- The Charleston and Columbia metros rank #12, #18 nationally; the Upstate is not spared.
- **Greenville County alone recorded 182 pedestrian fatalities** over 2014–2024.

Pedestrian risk and health-care access are two sides of the same coin: the residents
least able to drive are the most exposed on foot **and** the most dependent on transit
to reach care.

## What our access analysis found (Greenville County)

Modeling travel time from every census tract to the nearest Federally Qualified Health
Center (FQHC):

- **Median walking time to the nearest FQHC is 92.8 minutes** — far beyond a
  reasonable walk for most residents.
- **Only 40.7% of tracts can reach an FQHC by Greenlink within a single
  transfer** (weekday midday). **73 of 123 tracts have no such trip at all.**
- Where transit does reach an FQHC, it takes a median of **64.9 minutes** one way.

FQHCs are concentrated in the urban core; large parts of the county are effectively
cut off from them without a car.

## Why this matters

FQHCs exist specifically to serve low-income and uninsured patients. If reaching one
requires a car, the safety-net is out of reach for exactly the people it was built for —
the same people most exposed to pedestrian danger on Upstate roads.

## Recommendations

1. **Transit frequency and coverage where the safety-net is.** Prioritize Greenlink
   service improvements on corridors connecting underserved tracts to FQHC locations.
   The 2026 Greenlink Transit Development Plan is the natural vehicle.
2. **Pedestrian-safety investment on the deadliest corridors,** aligned with the city's
   Pedestrian Safety Action Plan, focused where fatalities and low car-access overlap.
3. **Co-locate or extend clinic access** (mobile/satellite FQHC sites, or siting new
   service-delivery sites) in transit-reachable, currently-underserved tracts.
4. **Publish access as a standing metric.** Track "share of residents who can reach an
   FQHC within 30 minutes by transit" over time as service and siting change.

## Method & caveats

Travel times are **modeled** estimates (walking at 3 mph with a 1.3× street detour;
transit via a RAPTOR-style ≤1-transfer search of the Greenlink GTFS feed, weekday
midday) from one representative point per tract — not observed individual trips. They
are directionally reliable for identifying gaps, not exact door-to-door times. FQHC
locations are HRSA service-delivery sites. This is a pilot; verify specifics with
providers and the agency before acting.

## Sources

1. Dangerous by Design 2026 — https://www.smartgrowthamerica.org/knowledge-hub/resources/dangerous-by-design-2026-americas-most-dangerous-places-for-people-walking-are-still-getting-more-dangerous/
2. SC drops to 4th most-dangerous state for pedestrians, but fatalities are on the rise (Post & Courier) — https://www.postandcourier.com/news/crime/south-carolina-deadliest-pedestrian-states-charleston-columbia/article_d5037bb9-e288-473e-a800-8c91c29ccb0b.html
3. NHTSA FARS (Fatality Analysis Reporting System), 2014–2024
4. HRSA Health Center Service Delivery Sites; Greenlink GTFS feed
