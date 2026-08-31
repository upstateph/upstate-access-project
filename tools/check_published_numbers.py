"""Cross-check every published number against the data that produced it."""
import json, re, sys
from pathlib import Path

R = Path(".")
def J(p): return json.load(open(R/p))

roll  = J("data/processed/access_rollup_tract_45045.json")
hous  = J("data/processed/housing_access_tract_45045.json")
groc  = J("data/processed/facilities_grocery.json")
gov   = J("data/processed/facilities_gov_social.json")
dss   = J("data/processed/facilities_dss.json")
work  = J("data/processed/facilities_workforce.json")
fqhc  = J("data/processed/facilities_fqhc.json")

rs, hs = roll["summary"], hous["summary"]
issues, checks = [], 0

def chk(label, claimed, actual, tol=0.05):
    global checks; checks += 1
    ok = abs(float(claimed) - float(actual)) <= tol
    if not ok: issues.append(f"{label}: doc says {claimed}, data says {actual}")
    print(f"  {'OK ' if ok else 'MISMATCH'}  {label:52s} claimed={claimed:<9} actual={actual}")

print("=== A. FQHC access numbers (used in all 5 partner letters) ===")
chk("41% of tracts reach an FQHC", 41, round(rs["pct_units_transit_reachable"]), 0.5)
chk("31% of residents", 31, round(rs["pct_population_transit_reachable"]), 0.5)
chk("73 of 123 tracts have no transit trip", 73, rs["n_units_no_transit"], 0)
chk("123 tracts total", 123, rs["n_units"], 0)
chk("median walk 92.8 min", 92.8, rs["walk_min_median"])
chk("median drive 11.1 min", 11.1, rs["drive_min_median"])
chk("median transit 65 min midday", 65, round(rs["transit_min_median"]), 0.5)

print("\n=== B. Housing numbers (proposal + housing-access.html + README) ===")
chk("32.5% of tracts reach all four", 32.5, hs["pct_units_all_four"])
chk("22.8% of residents", 22.8, hs["pct_population_all_four"])
chk("49.6% of tracts reach none", 49.6, hs["pct_units_none_of_four"])
h = hs["n_reachable_histogram"]
chk("61 tracts reach zero", 61, h["0"], 0)
chk("40 tracts reach all four", 40, h["4"], 0)
chk("22 tracts in between", 22, h["1"]+h["2"]+h["3"], 0)
for key, cl_r, cl_t, cl_w, cl_m in [
    ("grocery", 50.4, 42.3, 35.0, 16.8), ("fqhc", 42.3, 40.7, 5.7, 64.5),
    ("workforce", 36.6, 36.6, 4.9, 70.5), ("dss", 33.3, 32.5, 0.8, 99.8)]:
    d = hs["per_need"][key]
    chk(f"{key}: reachable", cl_r, d["pct_units_reachable"])
    chk(f"{key}: transit only", cl_t, d["pct_units_transit_reachable"])
    chk(f"{key}: walkable", cl_w, d["pct_units_walkable"])
    chk(f"{key}: median trip", cl_m, d["median_min_when_reachable"], 0.01)

print("\n=== C. The income / vehicle table (the proposal's core argument) ===")
u = hous["units"]
ok4 = [x for x in u if x["access"]["all_four"]]
no4 = [x for x in u if x["access"]["n_reachable"] == 0]
def avg(rows, k):
    v = [r[k] for r in rows if r.get(k) is not None]
    return round(sum(v)/len(v), 1) if v else None
chk("all-four tracts: n", 40, len(ok4), 0)
chk("all-four: median income $66,885", 66885, avg(ok4, "median_household_income"), 0.5)
chk("all-four: 7.6% no vehicle", 7.6, avg(ok4, "pct_no_vehicle"))
chk("none-of-four tracts: n", 61, len(no4), 0)
chk("none: median income $85,869", 85869, avg(no4, "median_household_income"), 0.5)
chk("none: 3.5% no vehicle", 3.5, avg(no4, "pct_no_vehicle"))

print("\n=== D. Facility counts ===")
chk("106 grocery destinations", 106, len(groc["facilities"]), 0)
chk("ONE DSS office in the county", 1, len(dss["facilities"]), 0)
chk("3 workforce sites", 3, len(work["facilities"]), 0)
chk("5 gov_social records", 5, len(gov["facilities"]), 0)
print(f"  info      fqhc destinations: {len(fqhc['facilities'])}")

print("\n=== E. Data integrity ===")
def dupes(recs, label):
    global checks; checks += 1
    seen, dup = set(), []
    for r in recs:
        k = (round(r["lat"], 5), round(r["lon"], 5), r["name"].lower())
        if k in seen: dup.append(r["name"])
        seen.add(k)
    print(f"  {'OK ' if not dup else 'WARN    '}  {label:52s} {len(dup)} exact duplicates")
    if dup: issues.append(f"{label}: {len(dup)} duplicate facilities: {dup[:3]}")
for nm, d in (("grocery", groc), ("fqhc", fqhc), ("dss", dss), ("workforce", work)):
    dupes(d["facilities"], f"{nm}: duplicate coordinates+name")

checks += 1
bad = [f["name"] for d in (groc, fqhc, dss, work) for f in d["facilities"]
       if not (34.4 <= f["lat"] <= 35.3 and -82.9 <= f["lon"] <= -82.0)]
print(f"  {'OK ' if not bad else 'FAIL    '}  {'all facility coords inside county bbox':52s} {len(bad)} outside")
if bad: issues.append(f"facilities outside county bbox: {bad[:5]}")

checks += 1
missing = [f.get("name","?") for d in (groc, fqhc, dss, work) for f in d["facilities"]
           if f.get("county_fips") != "45045"]
print(f"  {'OK ' if not missing else 'FAIL    '}  {'all facilities tagged county 45045':52s} {len(missing)} wrong")
if missing: issues.append(f"wrong county_fips: {missing[:5]}")

print(f"\n=== {checks} checks run, {len(issues)} problems ===")
for i in issues: print("  !", i)
sys.exit(1 if issues else 0)
