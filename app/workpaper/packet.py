"""Read-only access to the delivered packet.

The packet is loaded exactly as delivered and never modified. Everything the firm
does (adjustments, notes, sign-offs...) lives in the event log (store.py) and is
layered on top by state.py. That separation is the core of the design: the
pipeline's output is evidence, the workpaper is a record of decisions about it.
"""
from __future__ import annotations

import json
import os
import re
from functools import cached_property
from typing import Any

PACKET_PATH = os.environ.get("PACKET_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "packet.json"))

# Workpaper areas = the firm's budget areas (firm.budget_hours) plus payments/filing.
AREAS = [
    ("intake_and_engagement", "Intake & engagement"),
    ("wages_and_stock_compensation", "Wages & stock comp"),
    ("investments_and_digital_assets", "Investments & crypto"),
    ("business", "Business (Sch C)"),
    ("rentals_and_sale", "Rentals & condo sale"),
    ("pass_throughs_and_basis", "K-1s & basis"),
    ("deductions_and_credits", "Deductions & credits"),
    ("california", "California"),
    ("payments", "Payments & penalty"),
]
AREA_PREFIXES = [
    ("pass_throughs_and_basis", ["F7203", "F8949.F.SCORP", "SchE.28", "SchE.32", "SchB.1.7", "SchB.1.8", "SchD.12"]),
    ("california", ["F540NR", "SchCA540NR", "FTB", "ScheduleS"]),
    ("payments", ["F1040.25", "F1040.26", "F1040.31", "F1040.33", "F1040.34", "F1040.37", "F1040.38", "Sch3.10", "Sch3.15", "F2210"]),
    ("wages_and_stock_compensation", ["F1040.1", "Sch3.11", "F8959", "F6251", "Sch2.1", "Sch2.3", "F8889", "F1040.4", "F8606"]),
    ("investments_and_digital_assets", ["SchB", "SchD", "F8949", "F8938", "F1040.2", "F1040.3", "F1040.7", "Sch3.1", "Sch3.8", "F1040.20", "F8960", "Sch2.12"]),
    ("business", ["SchC", "SchSE", "F4562-C", "F8995", "Sch1", "Sch2.4", "F1040.8", "F1040.10", "F1040.13"]),
    ("rentals_and_sale", ["SchE", "F4797", "F8582", "F4562-E"]),
    ("deductions_and_credits", ["SchA", "F8283", "F8812", "F8863", "F2441", "F8867", "F1040.12", "F1040.14", "F1040.19"]),
]
DOC_AREA = {
    **{d: "intake_and_engagement" for d in ["D01", "D02", "D03", "D04", "D05", "D06", "D07", "D69", "D70", "D71", "D72"]},
    **{d: "wages_and_stock_compensation" for d in ["D08", "D09", "D10", "D11", "D12", "D13", "D41", "D42", "D43", "D44", "D45", "D73"]},
    **{d: "investments_and_digital_assets" for d in ["D28", "D29", "D30", "D31", "D32", "D33", "D34", "D35", "D36", "D74"]},
    **{f"D{i}": "business" for i in range(14, 28)},
    **{d: "pass_throughs_and_basis" for d in ["D37", "D38", "D39", "D40"]},
    **{f"D{i}": "rentals_and_sale" for i in range(46, 54)},
    **{d: "deductions_and_credits" for d in ["D54", "D55", "D56", "D57", "D58", "D59", "D60", "D61", "D62", "D63", "D64", "D65", "D66"]},
    **{d: "payments" for d in ["D67", "D68"]},
}

SENSITIVE_FIELDS = {"ssn", "ip_pin", "routing", "account"}
SSN_RE = re.compile(r"\b(666)-(\d{2})-(\d{4})\b")
BANK_RE = re.compile(r"\b(SE\d{2} [\d ]{14,})\b")


def area_of_line(key: str) -> str:
    def match(p: str) -> bool:
        if "." not in p:  # a whole form, e.g. "SchC" or "FTB"
            return key.split(".")[0].startswith(p)
        if key == p or key.startswith(p + "."):
            return True
        return key.startswith(p) and not key[len(p)].isdigit()  # F1040.1 matches F1040.1a, not F1040.10

    for area, prefixes in AREA_PREFIXES:
        if any(match(p) for p in prefixes):
            return area
    return "intake_and_engagement"


def mask_text(text: str) -> str:
    text = SSN_RE.sub(lambda m: f"XXX-XX-{m.group(3)}", text)
    text = BANK_RE.sub(lambda m: m.group(1)[:4] + " **** " + m.group(1)[-4:], text)
    text = re.sub(r"(Identity Protection PIN[^0-9]*)(\d{6})", r"\1••••••", text)
    return text


class Packet:
    def __init__(self, path: str = PACKET_PATH):
        with open(path) as f:
            self.raw: dict[str, Any] = json.load(f)
        r = self.raw
        self.docs = {d["id"]: d for d in r["documents"]}
        self.ev = {e["id"]: e for e in r["extracted_values"]}
        self.ev_by_doc: dict[str, list] = {}
        for e in r["extracted_values"]:
            self.ev_by_doc.setdefault(e["document_id"], []).append(e)
        self.versions = {v["version"]: v for v in r["return_versions"]}
        self.current_version = "v3"
        self.lines = {v: {l["key"]: l for l in self.versions[v]["lines"]} for v in self.versions}
        self.qa = {q["id"]: q for q in r["client"]["questionnaire"]}
        self.msgs = {m["id"]: m for m in r["client"]["messages"]}
        self.calls = {c["id"]: c for c in r["client"]["call_notes"]}
        self.staff = {s["id"]: s for s in r["firm"]["staff"]}
        self.people = {p["id"]: p for p in r["household"]["people"]}
        self.timeline = {t["id"]: t for t in r["timeline"]}
        self.rates = self.versions["v3"]["tax_effect_rates"]
        # reverse index: where did each extracted value / document land on the return?
        self.ev_used_by: dict[str, list[str]] = {}
        self.doc_used_by: dict[str, set[str]] = {}
        self.ref_used_by: dict[str, list[str]] = {}
        for l in self.versions["v3"]["lines"]:
            for s in l.get("sources") or []:
                self.ref_used_by.setdefault(s, []).append(l["key"])
                if s.startswith("ev-") and s in self.ev:
                    self.ev_used_by.setdefault(s, []).append(l["key"])
                    self.doc_used_by.setdefault(self.ev[s]["document_id"], set()).add(l["key"])
        # downstream: which lines use a line as input
        self.line_used_by: dict[str, list[str]] = {}
        for l in self.versions["v3"]["lines"]:
            for i in l.get("inputs") or []:
                self.line_used_by.setdefault(i, []).append(l["key"])

    # ---------- references ----------
    def json_pointer(self, root: Any, pointer: str) -> Any:
        cur = root
        for part in [p for p in pointer.split("/") if p != ""]:
            part = part.replace("~1", "/").replace("~0", "~")
            cur = cur[int(part)] if isinstance(cur, list) else cur[part]
        return cur

    def resolve(self, ref: str) -> dict:
        """Turn any reference string from the packet into a displayable record."""
        try:
            if ref.startswith("ev-") and ref in self.ev:
                e = self.ev[ref]
                d = self.docs[e["document_id"]]
                return {"ref": ref, "kind": "value", "title": f"{e['label']}", "subtitle": f"{d['id']} · {d['title']} · p{e['page']}",
                        "value": e["value"], "doc": d["id"], "page": e["page"], "confidence": e["confidence"], "text_as_read": e["text_as_read"]}
            if re.fullmatch(r"D\d\d", ref) and ref in self.docs:
                d = self.docs[ref]
                return {"ref": ref, "kind": "document", "title": d["title"], "subtitle": d["document_type"], "doc": ref, "page": 1}
            m = re.fullmatch(r"doc:(D\d\d)(?:#page(\d+))?", ref)
            if m:
                d = self.docs[m.group(1)]
                return {"ref": ref, "kind": "document", "title": d["title"], "subtitle": f"page {m.group(2) or 1}", "doc": d["id"], "page": int(m.group(2) or 1)}
            if ref in self.qa:
                q = self.qa[ref]
                return {"ref": ref, "kind": "questionnaire", "title": q["question"], "subtitle": f"{q['answered_by']} · {q['answered_at'][:10]}", "value": q["answer"]}
            if ref in self.msgs:
                q = self.msgs[ref]
                return {"ref": ref, "kind": "message", "title": f"Message from {q['from']}", "subtitle": q["sent_at"][:10], "value": q["text"]}
            if ref in self.calls:
                c = self.calls[ref]
                return {"ref": ref, "kind": "call", "title": "Client call notes", "subtitle": c["date"][:10], "value": " • ".join(c["notes"])[:1200]}
            if ref.startswith("py:"):
                v = self.json_pointer(self.raw["prior_years"], ref[3:])
                return {"ref": ref, "kind": "prior_year", "title": "Prior-year record", "subtitle": ref[3:], "value": v if not isinstance(v, (dict, list)) else json.dumps(v)[:300]}
            if ref.startswith("agency:"):
                v = self.json_pointer(self.raw["tax_agency_records"], ref[7:])
                return {"ref": ref, "kind": "agency", "title": "Tax agency record", "subtitle": ref[7:], "value": v if not isinstance(v, (dict, list)) else json.dumps(v)[:300]}
            if ref.startswith("ref:param."):
                name = ref[10:]
                return {"ref": ref, "kind": "parameter", "title": f"Engine parameter {name}", "subtitle": "engine_reference", "value": json.dumps(self.raw["engine_reference"]["parameters"].get(name))}
            if ref.startswith("ref:fx."):
                _, _, cur, rate = ref.split(".", 3)
                return {"ref": ref, "kind": "parameter", "title": f"FX {cur} {rate}", "subtitle": "SEK per USD", "value": self.raw["fx_rates"][f"{cur}_per_USD"][rate]}
            if ref.startswith("asset:"):
                aid = ref[6:]
                a = next((a for a in self.versions["v3"]["assets"] if a["asset_id"] == aid), None)
                return {"ref": ref, "kind": "asset", "title": a["description"] if a else aid, "subtitle": "Depreciation record", "value": a["cost"] if a else None}
            if ref.startswith("household:"):
                p = self.people.get(ref[10:])
                return {"ref": ref, "kind": "household", "title": p["name"] if p else ref, "subtitle": p["role"] if p else "household"}
            if ref.startswith("timeline:"):
                t = self.timeline.get(ref[9:])
                return {"ref": ref, "kind": "timeline", "title": t["event"].replace("_", " ") if t else ref, "subtitle": t["at"][:10] if t else "", "value": t.get("detail") if t else None}
            if ref in self.lines["v3"]:
                l = self.lines["v3"][ref]
                return {"ref": ref, "kind": "line", "title": l["label"], "subtitle": ref, "value": l["value"]}
        except (KeyError, IndexError, ValueError, TypeError):
            pass
        return {"ref": ref, "kind": "unknown", "title": ref, "subtitle": "unresolved reference"}

    # ---------- documents ----------
    def highlight_spans(self, doc_id: str) -> list[dict]:
        """Locate each extracted value inside the printed page text, so the simulated
        document can highlight the exact field. Real PDFs would use `position` instead."""
        out = []
        for e in self.ev_by_doc.get(doc_id, []):
            page = next((p for p in self.docs[doc_id]["pages"] if p["page"] == e["page"]), None)
            if not page:
                continue
            text = page["printed_content"]
            i, t = -1, ""
            for t in self._candidates(e):
                i = self._find_near(text, t, e["label"])
                if i >= 0:
                    break
            out.append({"ev": e["id"], "page": e["page"], "start": i, "end": i + len(t) if i >= 0 else -1,
                        "found": i >= 0, "field": e["field"], "label": e["label"], "value": e["value"],
                        "confidence": e["confidence"], "used_by": self.ev_used_by.get(e["id"], [])})
        return out

    @staticmethod
    def _candidates(e: dict) -> list[str]:
        """Ways the same value can be printed: as read, ISO vs US dates, with/without cents."""
        c = [str(e["text_as_read"])]
        v = e["value"]
        if e["value_type"] == "date" and isinstance(v, str) and re.fullmatch(r"\d{4}-\d\d-\d\d", v):
            y, m, dd = v.split("-")
            c += [v, f"{m}/{dd}/{y}", f"{m}/{y}"]
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            c += [f"{v:,.2f}", f"{v:,.0f}", f"{abs(v):,.2f}", f"({abs(v):,.2f})", str(v)]
        if isinstance(v, str):
            c.append(v)
        return [x for x in dict.fromkeys(c) if x]

    @staticmethod
    def _find_near(text: str, needle: str, label: str) -> int:
        """If the value occurs several times, pick the occurrence closest after a word of its label."""
        hits = [m.start() for m in re.finditer(re.escape(needle), text)]
        hits = [h for h in hits if not (h > 0 and text[h - 1].isdigit()) and not (h + len(needle) < len(text) and text[h + len(needle)].isdigit())]
        if len(hits) <= 1:
            return hits[0] if hits else -1
        words = [w for w in re.findall(r"[A-Za-z]{4,}", label.lower())]
        best, score = hits[0], 10 ** 9
        low = text.lower()
        for h in hits:
            for w in words:
                j = low.rfind(w, 0, h)
                if j >= 0 and h - j < score:
                    best, score = h, h - j
        return best

    def doc_summary(self, d: dict) -> dict:
        used = sorted(self.doc_used_by.get(d["id"], set()))
        v3 = self.versions["v3"]
        status = "used" if used else ("superseded" if d["id"] in v3.get("documents_superseded", []) else "not_on_return")
        return {"id": d["id"], "title": d["title"], "type": d["document_type"], "issuer": d.get("issuer"),
                "belongs_to": d["belongs_to"], "received_at": d["received_at"], "pages": d["page_count"],
                "extraction": d["extraction"], "values": len(self.ev_by_doc.get(d["id"], [])), "lines": used,
                "status": status, "area": DOC_AREA.get(d["id"], "intake_and_engagement")}


_PACKET: Packet | None = None


def get_packet() -> Packet:
    global _PACKET
    if _PACKET is None:
        _PACKET = Packet()
    return _PACKET
