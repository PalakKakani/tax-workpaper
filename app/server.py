"""Workpaper API. Run: uvicorn server:app --reload  (then open http://localhost:8000)."""
from __future__ import annotations

import os
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import base64
import hashlib
import json

from workpaper import views
from workpaper.commands import CommandError, execute
from workpaper.packet import AREAS, area_of_line, get_packet, mask_text
from workpaper.seed import seed_demo, seed_filed
from workpaper.state import ROLE_CAN, PermissionError_, _h, actors, build_state, check_permission
from workpaper.store import EventStore

app = FastAPI(title="Workpaper")
P = get_packet()
STORE = EventStore()


def state_for(viewer: str | None, upto: int | None = None) -> dict:
    return build_state(P, STORE.all(), upto=upto, viewer=viewer)


@app.get("/api/health")
def health():
    return {"ok": True, "events": len(STORE.all()), "chain": STORE.verify()}


@app.get("/api/meta")
def meta():
    r = P.raw
    v3 = P.versions["v3"]
    py = r["prior_years"]["return_2024"]
    lines = [{"key": l["key"], "j": l["jurisdiction"], "form": l["form"], "label": l["label"], "value": l["value"],
              "rule": l.get("rule"), "area": area_of_line(l["key"]), "v1": P.lines["v1"].get(l["key"], {}).get("value"),
              "v2": P.lines["v2"].get(l["key"], {}).get("value"), "py": py["lines"].get(l["key"]),
              "n_sources": len(l.get("sources") or []), "note": l.get("note")} for l in v3["lines"]]
    people = [{k: (mask_text(v) if isinstance(v, str) and k in ("ssn",) else ("••••••" if k == "ip_pin" and v else v))
               for k, v in p.items()} for p in r["household"]["people"]]
    return {
        "client": {"name": "Okafor-Lindqvist", "year": r["household"]["tax_year"], "filing_status": r["household"]["filing_status"],
                   "people": people, "addresses": r["household"]["addresses"], "residency": r["household"]["residency"],
                   "related_returns": r["household"]["related_returns"]},
        "actors": list(actors(P).values()),
        "areas": [{"id": a, "label": l} for a, l in AREAS],
        "versions": [{"version": v["version"], "computed_at": v["computed_at"], "trigger": v["trigger"], "summary": v["summary"],
                      "changes": len(v["changes_from_previous"]), "documents_superseded": v["documents_superseded"]} for v in r["return_versions"]],
        "prior_year": {"summary": {k: py["lines"].get(k) for k in ("F1040.11", "F1040.15", "F1040.24", "F1040.33")},
                       "prepared_by": py["prepared_by"], "residency": py["residency"]},
        "lines": lines,
        "documents": [P.doc_summary(d) for d in r["documents"]],
        "deadlines": r["firm"]["deadlines"], "budget": r["firm"]["budget_hours"], "firm": {"name": r["firm"]["name"]},
        "what_if": [{"id": a["id"], "description": a["description"], "federal": a["federal"]["total_tax_change"],
                     "california": a["california"]["total_tax_change"], "penalty": a["federal"].get("penalty_change"),
                     "changed_lines": a["changed_lines"]} for a in r["what_if"]["alternatives"]],
        "extension": r["what_if"]["extension"],
        "timeline": r["timeline"],
        "planning": r["planning_reference_2026"], "post_filing_rates": r["post_filing_rates"],
        "carryovers_out": v3["carryovers_out"], "carryovers_in": r["prior_years"]["carryovers_into_2025"],
        "assets": v3["assets"], "rates": v3["tax_effect_rates"], "rules": r["engine_reference"]["rules"],
        "questionnaire": r["client"]["questionnaire"], "messages": r["client"]["messages"], "calls": r["client"]["call_notes"],
        "agency": {"notices": r["tax_agency_records"]["notices"], "efile": r["tax_agency_records"]["efile"]},
        "diagnostics": {v["version"]: v["diagnostics"] for v in r["return_versions"]},
        "permissions": {k: sorted(v) for k, v in ROLE_CAN.items()},
        "counts": {"values": len(r["extracted_values"]), "documents": len(r["documents"]), "lines": len(v3["lines"])},
        "packet": r["packet"],
    }


@app.get("/api/state")
def get_state(viewer: str, upto: int | None = None):
    return state_for(viewer, upto)


@app.get("/api/line/{key}")
def line_passport(key: str, viewer: str):
    if key not in P.lines["v3"]:
        raise HTTPException(404, "No such line")
    l = P.lines["v3"][key]
    st = state_for(viewer)
    py = P.raw["prior_years"]["return_2024"]["lines"].get(key)
    return {
        "line": {**l, "area": area_of_line(key), "rule_text": P.raw["engine_reference"]["rules"].get(l.get("rule"), "")},
        "history": [{"version": v, "value": P.lines[v].get(key, {}).get("value"), "computed_at": P.versions[v]["computed_at"]} for v in ("v1", "v2", "v3")],
        "prior_year": py,
        "current": st["current_values"].get(key, l["value"]),
        "inputs": [{"key": i, "label": P.lines["v3"][i]["label"], "value": st["current_values"].get(i, P.lines["v3"][i]["value"])} for i in l.get("inputs") or [] if i in P.lines["v3"]],
        "used_by": [{"key": u, "label": P.lines["v3"][u]["label"], "value": P.lines["v3"][u]["value"]} for u in P.line_used_by.get(key, [])],
        "sources": [P.resolve(s) for s in l.get("sources") or []],
        "adjustments": [a for a in st["adjustments"] if a["line"] == key],
        "findings": [{"id": f["id"], "title": f["title"], "status": f["status"], "severity": f["severity"]} for f in st["findings"] if key in f["lines"]],
        "verifications": [v for v in st["verifications"] if v["target"] == key],
        "notes": [n for n in st["notes"] if n.get("target") == key],
        "evidence": [e for e in st["evidence"] if e.get("target") == key],
    }


@app.get("/api/doc/{doc_id}")
def document(doc_id: str, viewer: str):
    if doc_id not in P.docs:
        raise HTTPException(404, "No such document")
    d = P.docs[doc_id]
    st = state_for(viewer)
    pages = [{"page": pg["page"], "text": mask_text(pg["printed_content"])} for pg in d["pages"]]
    hl = P.highlight_spans(doc_id)
    for h in hl:  # masking keeps the same length for SSNs, so spans stay valid
        pass
    return {"summary": P.doc_summary(d), "pages": pages, "highlights": hl,
            "superseded_by": "D31" if doc_id == "D30" else None, "supersedes": "D30" if doc_id == "D31" else None,
            "findings": [{"id": f["id"], "title": f["title"], "status": f["status"]} for f in st["findings"]
                         if any(s == doc_id or s.startswith(f"doc:{doc_id}") or (s in P.ev and P.ev[s]["document_id"] == doc_id) for s in f["sources"])],
            "verifications": [v for v in st["verifications"] if v["target"] == doc_id],
            "notes": [n for n in st["notes"] if n.get("target") == doc_id],
            "evidence": [e for e in st["evidence"] if e.get("target") == doc_id],
            "not_used_reason": None if P.doc_used_by.get(doc_id) else _why_not_used(doc_id)}


def _why_not_used(doc_id: str) -> str:
    d = P.docs[doc_id]
    if doc_id in P.versions["v3"]["documents_superseded"]:
        return "Superseded by a corrected document."
    if d["extraction"]["status"] == "not_extracted":
        return d["extraction"]["reason"] or "Not extracted."
    if d["document_type"] in ("identity_document", "irs_ip_pin_notice", "engagement_letter", "consent"):
        return "Identity/engagement record: supports the return, no amounts on it."
    return "No value from this document is a source of any return line. Check it is accounted for."


@app.get("/api/reveal")
def reveal(viewer: str, ref: str):
    """Unmask one sensitive value. Allowed only with clearance; every view is logged."""
    st = state_for(viewer)
    try:
        check_permission(P, st, viewer, "sensitive.view", {})
    except PermissionError_ as e:
        raise HTTPException(403, str(e))
    m = re.fullmatch(r"household:(\w+)\.(ssn|ip_pin)", ref)
    if m:
        value = P.people[m.group(1)][m.group(2)]
    elif re.fullmatch(r"D\d\d", ref):
        value = "\n\n".join(pg["printed_content"] for pg in P.docs[ref]["pages"])
    else:
        raise HTTPException(400, "Unknown sensitive field")
    STORE.append(viewer, "sensitive.view", {"ref": ref}, target=ref)
    return {"ref": ref, "value": value}


class EventIn(BaseModel):
    actor: str
    type: str
    payload: dict = {}
    batch: str | None = None


@app.post("/api/events")
def post_event(ev: EventIn):
    try:
        execute(P, STORE, ev.actor, ev.type, ev.payload, batch=ev.batch)
    except PermissionError_ as e:
        raise HTTPException(403, str(e))
    except CommandError as e:
        raise HTTPException(400, str(e))
    return state_for(ev.actor)


@app.get("/api/search")
def search(q: str, viewer: str):
    ql = q.lower().strip()
    if len(ql) < 2:
        return []
    out = []
    for l in P.versions["v3"]["lines"]:
        if ql in l["key"].lower() or ql in l["label"].lower() or ql == str(l["value"]):
            out.append({"kind": "line", "id": l["key"], "title": l["label"], "subtitle": f"{l['key']} · {l['value']}"})
    for d in P.raw["documents"]:
        if ql in d["title"].lower() or ql == d["id"].lower() or any(ql in pg["printed_content"].lower() for pg in d["pages"]):
            out.append({"kind": "doc", "id": d["id"], "title": d["title"], "subtitle": d["id"]})
    for f in state_for(viewer)["findings"]:
        if ql in f["title"].lower() or ql in f["plain"].lower():
            out.append({"kind": "finding", "id": f["id"], "title": f["title"], "subtitle": f["area"]})
    for src in (P.raw["client"]["questionnaire"], P.raw["client"]["messages"]):
        for x in src:
            txt = (x.get("question", "") + " " + x.get("answer", "") + x.get("text", "")).lower()
            if ql in txt:
                out.append({"kind": "client", "id": x["id"], "title": (x.get("question") or x.get("text"))[:90], "subtitle": x["id"]})
    for e in P.raw["extracted_values"]:
        if ql == str(e["value"]).lower() or ql == str(e["text_as_read"]).lower():
            out.append({"kind": "value", "id": e["id"], "title": e["label"], "subtitle": f"{e['document_id']} · {e['text_as_read']}", "doc": e["document_id"]})
    return out[:60]


@app.get("/api/ref")
def ref(r: str):
    return P.resolve(r)


@app.get("/api/audit")
def audit():
    return {"chain": STORE.verify(), "events": STORE.all()}


@app.post("/api/demo/reset")
def demo_reset(scenario: str = "midseason"):
    """midseason: late June 2026, work in progress. filed: the whole season played through. empty: no events."""
    STORE.reset()
    if scenario in ("midseason", "filed"):
        seed_demo(P, STORE)
    if scenario == "filed":
        seed_filed(P, STORE)
    return {"ok": True, "events": len(STORE.all())}


# ---------------------------------------------------------------- derived read models
def _st(viewer):
    return state_for(viewer)


@app.get("/api/recon")
def recon(viewer: str):
    return views.reconciliations(P, _st(viewer))


@app.get("/api/sales")
def sales(viewer: str):
    return views.sales_summary(P, _st(viewer))


@app.get("/api/books")
def books(viewer: str):
    return views.books_to_tax(P, _st(viewer))


@app.get("/api/statesplit")
def statesplit(viewer: str):
    return views.state_split(P, _st(viewer))


@app.get("/api/variance")
def variance(viewer: str):
    return views.variance(P, _st(viewer))


@app.get("/api/completeness")
def completeness(viewer: str):
    return views.completeness(P, _st(viewer), [P.doc_summary(d) for d in P.raw["documents"]])


@app.get("/api/records")
def records(viewer: str):
    return views.records(P, _st(viewer))


@app.get("/api/notice/{notice_id}")
def notice(notice_id: str, viewer: str):
    return views.notice_packet(P, _st(viewer), notice_id)


@app.get("/api/rollforward")
def rollforward(viewer: str):
    return views.rollforward(P, _st(viewer))


@app.get("/api/compare")
def compare(viewer: str, a: int, b: int | None = None):
    """Compare the workpaper at two moments (event seq numbers)."""
    sa, sb = state_for(viewer, a), state_for(viewer, b)
    keys = sorted(set(sa["current_values"]) | set(sb["current_values"]))
    lines = [{"key": k, "label": P.lines["v3"].get(k, {}).get("label", k), "a": sa["current_values"].get(k, P.lines["v3"].get(k, {}).get("value")),
              "b": sb["current_values"].get(k, P.lines["v3"].get(k, {}).get("value"))} for k in keys]
    fa = {f["id"]: f["status"] for f in sa["findings"]}
    return {"a": a, "b": sb["seq"], "working": {"a": sa["working"], "b": sb["working"]},
            "lines": [l for l in lines if l["a"] != l["b"]],
            "findings": [{"id": f["id"], "title": f["title"], "a": fa.get(f["id"]), "b": f["status"]} for f in sb["findings"] if fa.get(f["id"]) != f["status"]],
            "events": [e for e in STORE.all() if a < e["seq"] <= sb["seq"]]}


# ---------------------------------------------------------------- evidence files
UPLOADS = os.path.join(os.path.dirname(__file__), "data", "uploads")


class UploadIn(BaseModel):
    actor: str
    name: str
    type: str = "application/octet-stream"
    data_b64: str


@app.post("/api/upload")
def upload(u: UploadIn):
    st = state_for(u.actor)
    try:
        check_permission(P, st, u.actor, "evidence.attach", {})
    except PermissionError_ as e:
        raise HTTPException(403, str(e))
    raw = base64.b64decode(u.data_b64)
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(413, "Files up to 8 MB.")
    sha = hashlib.sha256(raw).hexdigest()
    os.makedirs(UPLOADS, exist_ok=True)
    with open(os.path.join(UPLOADS, sha), "wb") as f:
        f.write(raw)
    with open(os.path.join(UPLOADS, sha + ".json"), "w") as f:
        json.dump({"name": u.name, "type": u.type}, f)
    return {"id": sha[:16], "sha256": sha, "name": u.name, "type": u.type, "size": len(raw)}


@app.get("/api/file/{sha}")
def get_file(sha: str):
    if not re.fullmatch(r"[0-9a-f]{16,64}", sha):
        raise HTTPException(400, "Bad id")
    hits = [f for f in os.listdir(UPLOADS) if f.startswith(sha) and not f.endswith(".json")] if os.path.isdir(UPLOADS) else []
    if not hits:
        raise HTTPException(404, "No such file")
    meta = json.load(open(os.path.join(UPLOADS, hits[0] + ".json")))
    return FileResponse(os.path.join(UPLOADS, hits[0]), media_type=meta["type"], filename=meta["name"])


if not STORE.all():
    seed_demo(P, STORE)

STATIC = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"), headers={"Cache-Control": "no-cache"})
