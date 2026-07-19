#!/usr/bin/env python3
"""Generate the LITE single-file app: a zero-backend "nearest health center" finder.

A stripped-down taste of the tool: click anywhere on the Greenville County map (or type
an address) to see the nearest FQHC by walking and driving, in miles. Everything —
the FQHC locations and the county outline — is embedded, and click-mode makes NO
external calls, so the file runs by itself: open it locally, drop it on any static host,
or publish it as a shareable link.

Omitted vs. the full tool (the "bells and whistles"): Greenlink transit routing, the
equity overlays, tract/ZIP rollups, and the other service categories.

Outputs:
  deploy/lite/index.html    — full standalone page (self-host or open locally)
  deploy/lite/artifact.html — same page as body-content only (for a shareable Artifact)

    python deploy/build_lite.py
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "deploy" / "lite"


def load_data():
    fac = json.loads((REPO / "data" / "processed" / "facilities_fqhc.json").read_text())["facilities"]
    slim = [{"name": f["name"], "address": f["address"], "city": f["city"],
             "zip": f["zip"], "phone": f.get("phone", ""),
             "lat": f["lat"], "lon": f["lon"]} for f in fac if f.get("lat")]
    gj = json.loads((REPO / "dashboard" / "data" / "sc_counties.geojson").read_text())
    geom = next(x["geometry"] for x in gj["features"] if x["id"] == "45045")
    return slim, geom


CSS = """
:root{
  --bg:#f6f7f9; --panel:#fff; --ink:#1a1f2b; --ink-soft:#5b6472; --line:#e4e7ec;
  --accent:#1f6feb; --accent-soft:#e8f0fe; --good:#197a3d; --danger:#b4232a;
  --shadow:0 1px 3px rgba(16,24,40,.06),0 1px 2px rgba(16,24,40,.04); --radius:12px;
  --land:#e8edf3; --land-line:#c7d0da;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0f1218; --panel:#171b24; --ink:#e8ebf1; --ink-soft:#9aa4b2; --line:#262c38;
  --accent:#4f8cff; --accent-soft:#182338; --good:#4ec27e; --danger:#ff6b6b; --shadow:none;
  --land:#1c2430; --land-line:#33404f;
}}
:root[data-theme=dark]{color-scheme:dark;--bg:#0f1218;--panel:#171b24;--ink:#e8ebf1;--ink-soft:#9aa4b2;--line:#262c38;--accent:#4f8cff;--accent-soft:#182338;--good:#4ec27e;--danger:#ff6b6b;--shadow:none;--land:#1c2430;--land-line:#33404f;}
:root[data-theme=light]{color-scheme:light;--bg:#f6f7f9;--panel:#fff;--ink:#1a1f2b;--ink-soft:#5b6472;--line:#e4e7ec;--accent:#1f6feb;--accent-soft:#e8f0fe;--good:#197a3d;--danger:#b4232a;--land:#e8edf3;--land-line:#c7d0da;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:960px;margin:0 auto;padding:0 20px}
header{background:linear-gradient(180deg,var(--panel),var(--bg));border-bottom:1px solid var(--line);padding:30px 0 24px}
.eyebrow{text-transform:uppercase;letter-spacing:.08em;font-size:12px;font-weight:600;color:var(--accent);margin:0 0 6px}
h1{font-size:24px;line-height:1.2;margin:0 0 8px;letter-spacing:-.01em;text-wrap:balance}
.sub{color:var(--ink-soft);margin:0;max-width:60ch}
main{padding:22px 0 44px;display:grid;grid-template-columns:1.1fr .9fr;gap:20px;align-items:start}
@media(max-width:760px){main{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:18px 20px}
.maphint{font-size:13px;color:var(--ink-soft);margin:0 0 10px}
svg.map{width:100%;height:auto;display:block;border-radius:10px;background:var(--panel)}
.county{fill:var(--land);stroke:var(--land-line);stroke-width:1}
.fqhc{fill:var(--accent);stroke:var(--panel);stroke-width:1.5;cursor:pointer}
.fqhc.near{fill:var(--good)}
.pin{fill:var(--danger);stroke:#fff;stroke-width:2}
.route{stroke:var(--good);stroke-width:2;stroke-dasharray:4 3;fill:none}
.form{display:flex;gap:8px;margin-bottom:12px}
input{flex:1;font:inherit;padding:9px 11px;border-radius:9px;border:1px solid var(--line);background:var(--bg);color:var(--ink)}
input:focus{outline:2px solid var(--accent);border-color:var(--accent)}
button{font:inherit;font-weight:600;padding:9px 15px;border:none;border-radius:9px;background:var(--accent);color:#fff;cursor:pointer}
.status{font-size:13px;color:var(--ink-soft);min-height:18px;margin:0 0 12px}
.status.warn{color:var(--danger)}
.result{margin-top:4px}
.result .lead{font-size:13px;color:var(--ink-soft);text-transform:uppercase;letter-spacing:.05em;margin:0 0 4px}
.result .fname{font-size:19px;font-weight:700;letter-spacing:-.01em;margin:0}
.result .faddr{color:var(--ink-soft);font-size:13.5px;margin:2px 0 12px}
.modes{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px}
.mode{border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.mode .lbl{font-size:12px;color:var(--ink-soft);text-transform:uppercase;letter-spacing:.05em}
.mode .big{font-size:26px;font-weight:700;letter-spacing:-.02em}
.mode .mi{font-size:12.5px;color:var(--ink-soft)}
.all{list-style:none;margin:6px 0 0;padding:0;font-size:13.5px}
.all li{display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-bottom:1px solid var(--line);cursor:pointer}
.all li:hover{color:var(--accent)}
.all li .r{color:var(--ink-soft);font-variant-numeric:tabular-nums;white-space:nowrap}
.empty{color:var(--ink-soft);font-size:14px}
footer{border-top:1px solid var(--line);padding:18px 0 40px;color:var(--ink-soft);font-size:12.5px}
footer a{color:var(--accent)}
"""

JS = r"""
const MI_PER_KM=0.621371, WALK_MPH=3.0, DRIVE_MPH=25.0, DETOUR=1.3;
function haversineKm(a,b,c,d){const R=6371.0088,p=Math.PI/180;
  const dphi=(c-a)*p,dl=(d-b)*p,s=Math.sin(dphi/2)**2+Math.cos(a*p)*Math.cos(c*p)*Math.sin(dl/2)**2;
  return 2*R*Math.asin(Math.sqrt(s));}
const fmtMin=m=>Math.round(m)+" min", fmt1=x=>x.toLocaleString(undefined,{maximumFractionDigits:1});

// ---- projection fitted to the county bbox ----
function bboxOf(geom){let a=[Infinity,Infinity,-Infinity,-Infinity];
  const polys=geom.type==="Polygon"?[geom.coordinates]:geom.coordinates;
  for(const poly of polys)for(const ring of poly)for(const[lo,la]of ring){
    if(lo<a[0])a[0]=lo;if(la<a[1])a[1]=la;if(lo>a[2])a[2]=lo;if(la>a[3])a[3]=la;}return a;}
const W=560,H=520,PAD=16;
const bb=bboxOf(GEOM), midLat=(bb[1]+bb[3])/2, kx=Math.cos(midLat*Math.PI/180);
const gw=(bb[2]-bb[0])*kx, gh=bb[3]-bb[1], scale=Math.min((W-2*PAD)/gw,(H-2*PAD)/gh);
const offX=(W-gw*scale)/2, offY=(H-gh*scale)/2;
const project=(lo,la)=>[offX+(lo-bb[0])*kx*scale, offY+(bb[3]-la)*scale];
const invert=(x,y)=>[(x-offX)/(kx*scale)+bb[0], bb[3]-(y-offY)/scale];
function pathFor(geom){const polys=geom.type==="Polygon"?[geom.coordinates]:geom.coordinates;let d="";
  for(const poly of polys)for(const ring of poly){ring.forEach(([lo,la],i)=>{const[x,y]=project(lo,la);
    d+=(i?"L":"M")+x.toFixed(1)+" "+y.toFixed(1);});d+="Z";}return d;}

const SVGNS="http://www.w3.org/2000/svg";
function el(t,a={}){const e=document.createElementNS(SVGNS,t);for(const k in a)e.setAttribute(k,a[k]);return e;}
const svg=document.getElementById("map");
svg.setAttribute("viewBox",`0 0 ${W} ${H}`);
svg.appendChild(el("path",{d:pathFor(GEOM),class:"county"}));
const markerLayer=el("g"); svg.appendChild(markerLayer);
const routeLayer=el("g"); svg.appendChild(routeLayer);
FQHC.forEach((f,i)=>{const[x,y]=project(f.lon,f.lat);
  const c=el("circle",{cx:x,cy:y,r:5,class:"fqhc","data-i":i});
  c.addEventListener("click",ev=>{ev.stopPropagation();});
  const title=el("title");title.textContent=f.name;c.appendChild(title);markerLayer.appendChild(c);f._xy=[x,y];});

let pin=null;
function setLocationXY(x,y){const[lon,lat]=invert(x,y);locate(lat,lon);}
svg.addEventListener("click",ev=>{const pt=svg.createSVGPoint();pt.x=ev.clientX;pt.y=ev.clientY;
  const loc=pt.matrixTransform(svg.getScreenCTM().inverse());setLocationXY(loc.x,loc.y);});

function locate(lat,lon,label){
  const ranked=FQHC.map(f=>{const km=haversineKm(lat,lon,f.lat,f.lon);
    return{f,walk:(km*DETOUR)/(WALK_MPH*1.609344)*60,drive:(km*DETOUR)/(DRIVE_MPH*1.609344)*60,mi:km*DETOUR*MI_PER_KM};})
    .sort((a,b)=>a.walk-b.walk);
  drawPin(lat,lon,ranked[0]); renderResult(ranked,label);
}
function drawPin(lat,lon,best){routeLayer.innerHTML="";
  const[px,py]=project(lon,lat);
  routeLayer.appendChild(el("line",{x1:px,y1:py,x2:best.f._xy[0],y2:best.f._xy[1],class:"route"}));
  if(pin)pin.remove(); pin=el("circle",{cx:px,cy:py,r:6,class:"pin"}); svg.appendChild(pin);
  markerLayer.querySelectorAll(".fqhc").forEach((c,i)=>c.classList.toggle("near",FQHC[i]===best.f));}

function renderResult(ranked,label){const best=ranked[0],r=document.getElementById("result");
  r.innerHTML=`<p class="lead">${label?label:"Nearest community health center"}</p>
    <p class="fname">${esc(best.f.name)}</p>
    <p class="faddr">${esc(best.f.address)}, ${esc(best.f.city)} ${esc(best.f.zip)}${best.f.phone?" · "+esc(best.f.phone):""}</p>
    <div class="modes">
      <div class="mode"><div class="lbl">🚶 Walk</div><div class="big">${fmtMin(best.walk)}</div><div class="mi">${fmt1(best.mi)} mi</div></div>
      <div class="mode"><div class="lbl">🚗 Drive</div><div class="big">${fmtMin(best.drive)}</div><div class="mi">${fmt1(best.mi)} mi</div></div>
    </div>
    <p class="lead">All ${ranked.length} locations</p>
    <ul class="all">${ranked.map(x=>`<li data-lat="${x.f.lat}" data-lon="${x.f.lon}"><span>${esc(x.f.name)}</span><span class="r">${fmtMin(x.walk)} walk · ${fmtMin(x.drive)} drive</span></li>`).join("")}</ul>`;
  r.querySelectorAll(".all li").forEach(li=>li.addEventListener("click",()=>{
    const[la,lo]=[parseFloat(li.dataset.lat),parseFloat(li.dataset.lon)];
    const[x,y]=project(lo,la); // pan? just re-center pin on the facility for context
  }));
}
function esc(s){return String(s??"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

// ---- optional address search (works on a hosted page; may be blocked in a sandbox) ----
const form=document.getElementById("addr-form"), status=document.getElementById("status");
form.addEventListener("submit",async e=>{e.preventDefault();
  const q=document.getElementById("addr").value.trim(); if(!q)return;
  status.className="status"; status.textContent="Looking up address…";
  try{
    const url="https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address="+encodeURIComponent(q)+"&benchmark=Public_AR_Current&format=json";
    const j=await (await fetch(url)).json();
    const m=j.result&&j.result.addressMatches&&j.result.addressMatches[0];
    if(!m){status.className="status warn";status.textContent="No match — try adding city, state, ZIP, or just click the map.";return;}
    status.textContent="From "+m.matchedAddress;
    locate(m.coordinates.y,m.coordinates.x,"Nearest to "+m.matchedAddress.split(",")[0]);
  }catch(err){status.className="status warn";
    status.textContent="Address search isn’t available here — click the map to drop your location instead.";}
});

// theme toggle honoring stamped attribute already handled by CSS.
"""

BODY_TMPL = """<title>Greenville County — Nearest Health Center (lite)</title>
<style>{css}</style>
<header><div class="wrap">
  <p class="eyebrow">Upstate Access Project · lite preview</p>
  <h1>Can you reach a health center from here?</h1>
  <p class="sub">Click anywhere in Greenville County to drop your location — or type an address —
  and see the nearest Federally Qualified Health Center by walking and driving.</p>
</div></header>
<main class="wrap">
  <section class="card">
    <p class="maphint">Tap the map to set your location. Blue dots are health centers; the nearest turns green.</p>
    <svg id="map" class="map" role="img" aria-label="Greenville County map — click to set your location"></svg>
  </section>
  <section class="card">
    <form id="addr-form" class="form">
      <input id="addr" type="text" autocomplete="off" placeholder="e.g. 206 S Main St, Greenville, SC 29601" />
      <button type="submit">Find</button>
    </form>
    <p id="status" class="status">No account, no tracking. Your location is used only to compute the result.</p>
    <div id="result" class="result"><p class="empty">Pick a spot on the map (or search an address) to see the nearest health center.</p></div>
  </section>
</main>
<footer><div class="wrap">
  Lite preview — walking (3&nbsp;mph) and driving (25&nbsp;mph) times are straight-line estimates with a
  road-detour factor, in miles. Health-center locations: HRSA. The full tool adds Greenlink transit,
  equity comparisons, and more service types.
</div></footer>
<script>
const FQHC={fqhc};
const GEOM={geom};
{js}
</script>
"""


def main() -> None:
    fac, geom = load_data()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    body = BODY_TMPL.format(css=CSS, js=JS, fqhc=json.dumps(fac), geom=json.dumps(geom))

    # Artifact version = body-content only.
    (OUT_DIR / "artifact.html").write_text(body)
    # Standalone version = wrapped so it opens/hosts on its own.
    standalone = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                  '<meta name="viewport" content="width=device-width,initial-scale=1">'
                  '</head><body>\n' + body + '\n</body></html>\n')
    (OUT_DIR / "index.html").write_text(standalone)
    print(f"Wrote deploy/lite/index.html ({len(standalone)//1024} KB, standalone) and artifact.html.")
    print(f"  {len(fac)} FQHCs embedded; zero external calls in click-mode.")


if __name__ == "__main__":
    main()
