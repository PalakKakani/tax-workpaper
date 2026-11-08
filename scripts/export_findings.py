"""Writes every finding from the live checks to findings.json (used for the written report).
Run from the repo root: python scripts/export_findings.py"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
from workpaper.packet import get_packet  # noqa: E402
from workpaper.state import build_state  # noqa: E402

st = build_state(get_packet(), [])
out = [{k: f.get(k) for k in ("id", "kind", "severity", "area", "engine", "title", "plain", "detail", "fix", "lines", "sources", "tax_effect", "payment_effect")} for f in st["findings"]]
json.dump(out, open(os.path.join(os.path.dirname(__file__), "findings.json"), "w"), indent=1)
print(len(out), "findings")
