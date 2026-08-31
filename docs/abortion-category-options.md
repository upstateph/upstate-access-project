# Publishing abortion locations: what actually protects anyone

Written 31 Aug 2026 in response to "build it out, with some privacy measure or a
warning popup." The short version: **a popup protects nobody, and there is a
design that does far more than one, for less work.**

## First, separate three risks that get discussed as one

**1. Risk to the person searching.** Not the network. Addresses already travel in
POST bodies, never query strings, and nothing is logged. The exposure is on the
person's own device and in their own life: a page title in browser history on a
shared phone, a back button pressed in front of the wrong person, an autofilled
address box. A popup does not touch any of that.

**2. Risk to the facility.** South Carolina has three abortion clinics
(Charleston, Columbia, Greenville). Publishing a structured, machine-readable
layer whose entire content is "here are the abortion providers" is a different
act from publishing 106 grocery stores, even though the address is already on the
clinic's own website. The concern is not disclosure, it is **aggregation**: a
scrapable list is an artifact that did not previously exist.

**3. Risk of being wrong.** Under a six-week limit, a stale address does not cost
an inconvenience, it can cost eligibility. And the likeliest error is not
omission but **mis-listing a crisis pregnancy center as a provider**, which sends
someone somewhere that will not help and burns days they do not have.

## The options, worst to best

### A warning or interstitial popup. Weakest, and it feels like the strongest.

It changes nothing about what is in the page, the HTML, the API response, the
browser history, or a scraper's take. It is friction shown to the one person who
already decided to look. **Do not mistake it for a privacy control.** It has one
legitimate use, covered below, and that use is accuracy rather than privacy.

### Map the place, not the procedure. Strongest, and cheapest.

**Do not create an `abortion` category at all.** Greenville Women's Clinic is a
reproductive health facility; list it as one. Someone searching for it finds it,
because they know what they are looking for and they are searching by need, not
by category label.

What this buys:
- No machine-readable "abortion providers" layer exists to scrape, so risk 2
  largely disappears.
- No page, title, or history entry names the procedure, so risk 1 shrinks
  without a single popup.
- The tool still answers the question the person actually asked, which is how
  long it takes to get there.

**This is not a new idea in this project.** It is branch C of the Scott Brown
script, written weeks ago for HIV care: *"list the health center, not the
program."* It was the most likely and most useful answer then, and it is the
right answer here. Adopting it settles `abortion` and probably
`reproductive_health` and `hiv_ryan_white` too.

### Measures that are real, if smaller

- **A quick-exit control.** Standard on domestic-violence and reproductive health
  sites: one visible button that navigates away immediately and replaces the
  history entry. Directly addresses the shared-device threat, which is the
  realistic one. Cheap.
- **`Referrer-Policy: no-referrer`** so an outbound click to a clinic's site does
  not carry the origin, plus a page title that names the tool rather than the
  category.
- **Never ship the facility file statically.** Sensitive categories should be
  reachable only through the API, one nearest-result at a time, never as a
  downloadable list and never as an enumeration endpoint. This is the difference
  between answering a question and publishing a directory.
- **No logging**, which is already true and already the strongest protection in
  place.

### The one good use of a warning

Not privacy. **Accuracy and law.** If any of this publishes, the result should
say plainly that South Carolina restricts abortion after roughly six weeks, that
timing is therefore critical, and that the reader should call before travelling.
That is information someone genuinely needs and cannot get from a travel time.

## What still gates all of it

**Verification.** `abortion` has zero candidate addresses today and
`reproductive_health` has six with none verified. Nothing publishes on inference,
whatever design is chosen. And the crisis-pregnancy-center hazard means this
category must never be auto-sourced from a directory: every entry needs a human
who confirmed what the facility actually provides.

**And the conversation on 2 September.** Evie is being asked exactly this
question. Deciding it two days early makes the question rhetorical.

## Recommendation

1. **Do not build an `abortion` category.** Fold the facility into reproductive
   health, verified by phone first.
2. **Build the protective infrastructure now**, because it helps every sensitive
   category and commits to nothing: quick-exit control, no-referrer, no static
   file for sensitive categories, API returns nearest-only.
3. **Add the six-week accuracy notice** to whatever publishes.
4. **Ask Evie on Wednesday**, and let her answer decide whether step 1 happens at
   all.

**One thing outside my competence:** whether a directory listing carries any
liability under South Carolina law is a question for a lawyer, not for me. It is
probably nothing, and "probably" is doing work in that sentence that five minutes
of actual advice would remove.
