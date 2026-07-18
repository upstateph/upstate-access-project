"""Upstate Access Project — Tier 2 scoring engine.

Geocodes an address, finds the nearest facility of a category, and computes travel
time by walking and by Greenlink transit. Designed to be importable and testable
without any UI (spec §7, Phase 2).

Privacy: nothing in this package logs or persists the input address. Callers must
uphold the same contract (see docs/privacy-design.md).
"""
