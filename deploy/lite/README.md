# Lite preview

A single self-contained page: click anywhere in Greenville County (or type an address)
to see the nearest FQHC by walking and driving time, in miles. **No backend, no build,
no external calls in click-mode** — the health-center locations and county outline are
embedded.

Regenerate from the current data with:

```bash
python deploy/build_lite.py     # -> deploy/lite/index.html (+ artifact.html)
```

## Deploy it

- **Open it:** double-click `index.html` (or drag it into a browser).
- **Host it:** upload `index.html` to any static host — Netlify drop, Cloudflare Pages,
  GitHub Pages, S3, etc. That's the whole site.
- **Share a link now:** it's also published as a private Claude Artifact —
  https://claude.ai/code/artifact/9bdd3acd-2ac1-445d-8337-a4f2a3f98358
  (share it from the artifact's share menu).

## Notes

- **Address search** calls the Census Geocoder, which works on a normally-hosted page
  but is blocked in the sandboxed Artifact — there, use click-to-locate (the page says
  so if a search is blocked).
- Walk (3 mph) / drive (25 mph) times are straight-line estimates with a 1.3× road
  detour factor — good for a gut check, not turn-by-turn.
- Left out on purpose (the "bells and whistles"): Greenlink transit, equity overlays,
  tract/ZIP rollups, and the other service categories. Those live in the full stack
  (`deploy/README.md`).
