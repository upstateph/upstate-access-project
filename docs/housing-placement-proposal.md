# Scoring the unit, not the person

**A proposal for Greenville Together, and it is already built.**

The Upstate Access Project measures how long it takes to reach health services
from any address in Greenville County, on foot, by bike, by car, and by Greenlink
bus. This is the same engine pointed at a different question.

Instead of asking how far a *person* is from care, it asks: **can a household
placed at this address reach the things that keep a placement from failing,
without a car?**

Four destinations, checked from any prospective unit:

| | Why it is on the list |
|---|---|
| Primary care (FQHC) | Sliding scale, takes Medicaid and the uninsured |
| DSS benefits office | SNAP, Medicaid and TANF enrollment. **One office serves the county.** |
| Workforce services (SC Works) | Job search and training. Three sites. |
| Grocery store | SNAP-accepting supermarket or grocery store, 106 in the county |

Type an address, get four travel times. Running now at
`/housing-access.html`.

## What the county actually looks like

Every one of Greenville County's 123 census tracts, scored the same way.
Reachable means within a 20-minute walk, or a Greenlink trip with at most one
transfer and at most a 30-minute wait, taken as the median across the
weekday-midday hour.

- **32.5% of tracts** can reach all four without a car.
- Those tracts hold **22.8% of county residents**.
- **49.6% of tracts can reach none of the four.**

**There is almost no middle ground.** 61 tracts reach zero, 40 reach all four,
and only 22 sit anywhere in between. A unit is usually either connected or
stranded. That is what makes checking one worth doing before a lease is signed
rather than after.

| Destination | Tracts that can reach it | By bus only | Within a 20-min walk | Median trip when reachable |
|---|---|---|---|---|
| Grocery store | 50.4% | 42.3% | 35.0% | 17 min |
| Primary care (FQHC) | 42.3% | 40.7% | 5.7% | 65 min |
| Workforce services | 36.6% | 36.6% | 4.9% | 71 min |
| DSS benefits office | 33.3% | 32.5% | 0.8% | **100 min** |

The DSS row is the one I would look at hardest. One office serves the whole
county, at 352 Halton Rd. For the third of tracts that can reach it at all, the
median trip is an hour and forty minutes each way. Enrolling in SNAP or Medicaid
is a whole day, and it is a whole day for the people least able to give one up.

## Why a neighborhood average cannot answer this

| Tracts | Count | Median household income | Households with no vehicle |
|---|---|---|---|
| Reach all four car-free | 40 | $66,886 | **7.6%** |
| Reach none of the four | 61 | $85,869 | **3.5%** |

The places with no car-free access are the places where nearly everyone drives.
That is not a paradox, it is the whole problem. A household leaving homelessness
is unlikely to have a car regardless of what its new neighbors own. Placing one
into a tract where 96% of households drive puts them somewhere the transit
answer was never designed for, and the neighborhood statistics will look
reassuring the entire time.

The average describes the neighborhood. Only the unit describes the household.

## What it deliberately does not do

**It returns four travel times. It does not return a score, a rating, or a
recommendation on a unit.**

A composite number would hide which of the four failed, and that is the only part
anyone can act on. "3 out of 4" is useless; "everything except DSS, and DSS is
a 222-minute walk" tells a navigator what to solve. A pass/fail stamped on a
housing unit is also a placement decision, and that belongs to the person who
knows the household, not to a model that knows an address.

This is enforced in the code and in a test, not just in a README.

## Limits, stated up front

- **One county.** Greer, Piedmont and Fountain Inn straddle county lines, so a
  real local address can fall outside the model. The tool names the county it
  landed in rather than reporting a failure, but it cannot answer for that unit.
- **Modeled, not observed.** Travel times come from the road network and
  Greenlink's published timetable, not from watching anyone travel.
- **Weekday midday**, which is the thinnest service of the day and the hour when
  appointments are most often scheduled. Early morning looks better.
- **It takes an address.** That works for a unit or a shelter and does not work
  for someone unsheltered, which means the population with the worst access is
  the one this method currently cannot describe. If that gap is the interesting
  one, I would rather hear it from you than guess.
- **Grocery means grocery.** 443 retailers in the county accept SNAP; 106 of
  them sell a week of food. Counting gas stations and dollar stores would make
  food access look about four times better than it is, in exactly the
  neighborhoods that have no supermarket.
- **The 20-minute walk cap is a judgment call**, not a finding. It is about a
  mile. Change it and the numbers move; the tool records which cap produced them.

## What I would want from you

1. **Are these the right four?** I picked them from the outside. If a placement
   lives or dies on school access, a pharmacy, or a specific clinic, the list is
   wrong and the fix is small.
2. **Is 20 minutes the right walk?** For someone carrying groceries, in August,
   in South Carolina, it may be generous.
3. **Where would this sit in your process?** Screening a list of candidate units
   is a different tool than checking one unit at lease signing.
4. **Would a navigator use it, and would you want to watch one try?** Everyone
   who has reviewed this project so far is a clinician or an analyst. Nobody who
   would actually use it has touched it.

## Sources

HRSA health center sites, USDA FNS SNAP retailer data, verified official .gov
office listings, Greenlink GTFS (service through August 2027), Census ACS 2024
5-year. Code and method are open.
