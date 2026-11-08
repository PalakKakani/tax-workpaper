"""Projection: replay the event log on top of the packet to get the workpaper now.

State is never stored; it is always rebuilt from (packet + events). That gives us,
for free: undo (a reversing event), history of every number, 'what changed since
you last looked' (events after your last 'seen'), comparing any two moments
(replay up to seq N), freeze at filing (a snapshot hash) and amendments on top.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from .checks import run_checks
from .packet import AREAS, DOC_AREA, Packet, area_of_line

ROLE_CAN = {
    "preparer": {"finding.accept", "finding.resolve", "finding.dismiss", "finding.reopen", "adjustment.manual", "adjustment.revert", "batch.undo",
                 "note.add", "evidence.attach", "verification.record", "question.ask", "review_note.respond", "signoff.sign",
                 "time.log", "judgment.record", "seen", "sensitive.view", "bulk.verify"},
    "reviewer": {"finding.accept", "finding.resolve", "finding.dismiss", "finding.reopen", "adjustment.manual", "adjustment.revert", "batch.undo",
                 "note.add", "evidence.attach", "verification.record", "question.ask", "review_note.open", "review_note.respond",
                 "review_note.clear", "signoff.sign", "time.log", "judgment.record", "seen", "sensitive.view", "bulk.verify"},
    "partner": {"finding.accept", "finding.resolve", "finding.dismiss", "finding.reopen", "adjustment.manual", "adjustment.revert", "adjustment.approve",
                "batch.undo", "note.add", "evidence.attach", "verification.record", "question.ask", "review_note.open",
                "review_note.respond", "review_note.clear", "signoff.sign", "time.log", "judgment.record", "seen",
                "sensitive.view", "filing.freeze", "filing.amend", "timeline.replay", "bulk.verify"},
    "firm_administrator": {"standards.update", "assignment.set", "note.add", "seen", "sensitive.view", "timeline.replay"},
    "quality_reviewer": {"review_note.open", "review_note.clear", "note.add", "seen", "sensitive.view"},
    "client": {"question.answer", "client.approve", "evidence.attach", "seen"},
}
SIGN_LEVELS = {"preparer": "preparer", "reviewer": "reviewer", "partner": "partner"}


def actors(p: Packet) -> dict:
    a = {s["id"]: {"id": s["id"], "name": s["name"], "role": s["role"], "credential": s.get("credential"),
                   "clearance": s.get("sensitive_data_clearance", False), "note": s.get("note"), "active_from": s.get("active_from")}
         for s in p.raw["firm"]["staff"]}
    for c in p.raw["firm"]["client_users"]:
        a[c["id"]] = {"id": c["id"], "name": c["name"], "role": "client", "clearance": False, "credential": None}
    return a


class PermissionError_(Exception):
    pass


def check_permission(p: Packet, state: dict, actor: str, type_: str, payload: dict) -> None:
    who = actors(p).get(actor)
    if not who:
        raise PermissionError_("Unknown user")
    if type_ not in ROLE_CAN.get(who["role"], set()):
        raise PermissionError_(f"A {who['role'].replace('_', ' ')} can't do '{type_}'.")
    if type_ == "sensitive.view" and not who["clearance"]:
        raise PermissionError_(f"{who['name']} has no sensitive-data clearance. Masked values only.")
    frozen = state["filing"]["frozen"] and not state["filing"]["amending"]
    if frozen and type_ in {"finding.accept", "finding.resolve", "finding.dismiss", "finding.reopen", "adjustment.manual", "adjustment.revert", "batch.undo", "bulk.verify", "signoff.sign"}:
        raise PermissionError_("The return is frozen at filing. Start an amendment to change it.")
    if type_ == "signoff.sign":
        level = payload.get("level")
        if SIGN_LEVELS.get(who["role"]) != level:
            raise PermissionError_(f"A {who['role']} can only sign at the {who['role']} level.")
        if payload["area"] == "return":
            if level != "partner":
                raise PermissionError_("Only a partner signs the whole return.")
            unsigned = [a["label"] for a in state["areas"].values() if not all(l in a["signoffs"] and not a["signoffs"][l]["stale"] for l in ("preparer", "reviewer"))]
            if unsigned:
                raise PermissionError_("Every area needs fresh preparer and reviewer sign-offs first: " + ", ".join(unsigned[:3]))
            if state["filing"]["big_unapproved"]:
                raise PermissionError_("Approve the adjustments over $1,000 first.")
            return
        area = state["areas"][payload["area"]]
        prep = area["signoffs"].get("preparer")
        if level != "preparer" and prep and prep["by"] == actor:
            raise PermissionError_("You prepared this area, so you can't review it (firm rule).")
        if level != "preparer" and area["open_review_notes"]:
            raise PermissionError_("Clear the open review notes in this area first.")
    if type_ == "filing.freeze" and state["filing"]["blockers"]:
        raise PermissionError_("Not ready to file: " + "; ".join(state["filing"]["blockers"][:3]))
    if type_ == "client.approve" and not state["filing"]["ready_for_client"]:
        raise PermissionError_("The firm hasn't sent the return for approval yet.")


def _h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


# Simple additive totals we roll up so schedules stay internally consistent after an
# adjustment. These are display totals only: tax is priced from the adjusted lines
# themselves (README: we can't rerun the engine), so derived lines are never priced.
_EXP = ["SchC.8", "SchC.9", "SchC.11", "SchC.13", "SchC.15", "SchC.17", "SchC.18", "SchC.22", "SchC.24a", "SchC.24b", "SchC.25", "SchC.27a.1", "SchC.27a.2"]
DERIVED = [
    ("SchA.5d", [("SchA.5a", 1), ("SchA.5b", 1)]), ("SchA.7", [("SchA.5e", 1)]),
    ("SchA.8e", [("SchA.8a", 1), ("SchA.8c", 1)]), ("SchA.10", [("SchA.8e", 1)]),
    ("SchA.12", [("F8283.A1.stock", 1), ("F8283.A1.vehicle", 1)]), ("SchA.14", [("SchA.11", 1), ("SchA.12", 1)]),
    ("SchA.17", [("SchA.7", 1), ("SchA.10", 1), ("SchA.14", 1)]), ("F1040.12", [("SchA.17", 1)]),
    ("SchB.2", [(f"SchB.1.{i}", 1) for i in range(1, 9)]), ("SchB.4", [("SchB.2", 1)]), ("F1040.2b", [("SchB.4", 1)]),
    ("SchC.5", [("SchC.1", 1)]), ("SchC.7", [("SchC.5", 1)]), ("SchC.28", [(k, 1) for k in _EXP]),
    ("SchC.29", [("SchC.7", 1), ("SchC.28", -1)]), ("SchC.31", [("SchC.29", 1), ("SchC.30", -1)]),
    ("Sch1.3", [("SchC.31", 1)]), ("SchSE.2", [("SchC.31", 1)]),
    ("F4562-C.22", [("F4562-C.12", 1), ("F4562-C.14", 1), ("F4562-C.19a", 1)]),
    ("F1040.33", [("F1040.25d", 1), ("F1040.26", 1), ("F1040.31", 1)]),
    ("F540NR.78", [("F540NR.71", 1), ("F540NR.72", 1), ("F540NR.73", 1)]),
]


def _derive(p: Packet, current: dict) -> dict:
    v3 = p.lines["v3"]
    out = {}
    val = lambda k: out.get(k, current.get(k, v3[k]["value"] if k in v3 else 0))
    for key, parts in DERIVED:
        if key in current or key not in v3:
            continue
        delta = sum(sign * (val(k) - (v3[k]["value"] if k in v3 else 0)) for k, sign in parts if k in v3 or k in current or k in out)
        if abs(delta) > 0.004:
            out[key] = round(v3[key]["value"] + delta, 2)
    return out


def build_state(p: Packet, events: list[dict], upto: int | None = None, viewer: str | None = None) -> dict:
    who = actors(p)
    if not hasattr(p, "_checks"):
        p._checks = run_checks(p)  # the packet never changes, so neither do the checks' raw results
    findings = {f["id"]: {**deepcopy(f), "status": "verified" if f["kind"] == "verified" else "open", "history": []} for f in p._checks}
    adjustments: dict[str, dict] = {}
    notes, evidence, verifications, questions, review_notes, judgments, sens_views, time_log = [], [], [], [], [], [], [], []
    signoffs: dict[str, dict] = {a: {} for a, _ in AREAS}
    signoffs["return"] = {}
    standards = deepcopy(p.raw["firm"]["starter_standards"])
    assignments = {a: dict(p.raw["firm"]["assignment_at_start"]) for a, _ in AREAS}
    seen: dict[str, int] = {}
    replayed: list[dict] = []
    filing = {"frozen": False, "frozen_at": None, "snapshot": None, "amending": False, "amendments": 0,
              "client_approved": None, "efile": []}
    applied = [e for e in events if upto is None or e["seq"] <= upto]

    def add_adjustments(e, items, finding_id=None):
        ids = []
        for i, a in enumerate(items):
            aid = f"adj-{e['seq']}-{i}"
            prev = next((x for x in adjustments.values() if x["line"] == a["line"] and x["active"]), None)
            adjustments[aid] = {**a, "id": aid, "by": e["actor"], "at": e["at"], "reason": e["payload"].get("reason") or a.get("note"),
                                "finding": finding_id, "batch": e["batch"] or e["id"], "active": True, "seq": e["seq"],
                                "supersedes": prev["id"] if prev else None, "approved_by": None,
                                "phase": "amendment" if filing["amending"] else "original"}
            if prev:
                prev["active"] = False
            ids.append(aid)
        return ids

    for e in applied:
        t, pl = e["type"], e["payload"]
        if t == "finding.accept":
            f = findings.get(pl["finding"])
            if f:
                f["status"] = "accepted"
                f["adjustments"] = add_adjustments(e, f["proposal"], f["id"])
                f["history"].append({"seq": e["seq"], "by": e["actor"], "at": e["at"], "what": "accepted", "reason": pl.get("reason")})
        elif t == "finding.resolve":
            f = findings.get(pl["finding"])
            if f:
                f["status"] = "resolved"
                f["history"].append({"seq": e["seq"], "by": e["actor"], "at": e["at"], "what": "resolved", "reason": pl.get("reason"), "authority": pl.get("authority")})
        elif t == "finding.dismiss":
            f = findings.get(pl["finding"])
            if f:
                f["status"] = "dismissed"
                f["history"].append({"seq": e["seq"], "by": e["actor"], "at": e["at"], "what": "dismissed", "reason": pl.get("reason"), "authority": pl.get("authority")})
        elif t == "finding.reopen":
            f = findings.get(pl["finding"])
            if f:
                for aid in f.get("adjustments", []):
                    adjustments[aid]["active"] = False
                f["status"] = "open"
                f["history"].append({"seq": e["seq"], "by": e["actor"], "at": e["at"], "what": "reopened", "reason": pl.get("reason")})
        elif t == "adjustment.manual":
            from .checks import adj
            a = adj(p, pl["line"], float(pl["to"]), pl.get("category", "ordinary_income"))
            add_adjustments(e, [a])
        elif t == "adjustment.revert":
            a = adjustments.get(pl["adjustment"])
            if a:
                a["active"] = False
                a["reverted"] = {"by": e["actor"], "at": e["at"], "reason": pl.get("reason")}
        elif t == "adjustment.approve":
            for aid in pl.get("adjustments", []):
                if aid in adjustments:
                    adjustments[aid]["approved_by"] = e["actor"]
        elif t == "batch.undo":
            for a in adjustments.values():
                if a["batch"] == pl["batch"] and a["active"]:
                    a["active"] = False
                    a["reverted"] = {"by": e["actor"], "at": e["at"], "reason": "undo"}
            for f in findings.values():
                if any(adjustments.get(x, {}).get("batch") == pl["batch"] for x in f.get("adjustments", [])):
                    f["status"] = "open"
                    f["history"].append({"seq": e["seq"], "by": e["actor"], "at": e["at"], "what": "undone"})
            for v in verifications:
                if v.get("batch") == pl["batch"]:
                    v["undone"] = True
        elif t == "note.add":
            notes.append({"seq": e["seq"], "by": e["actor"], "at": e["at"], **pl})
        elif t == "evidence.attach":
            evidence.append({"seq": e["seq"], "id": f"att-{e['seq']}", "by": e["actor"], "at": e["at"], **pl})
        elif t == "verification.record":
            verifications.append({"seq": e["seq"], "by": e["actor"], "at": e["at"], "batch": e["batch"], **pl})
        elif t == "bulk.verify":
            for tgt in pl["targets"]:
                verifications.append({"seq": e["seq"], "by": e["actor"], "at": e["at"], "batch": e["batch"] or e["id"], "target": tgt, "type": pl["type"], "note": pl.get("note")})
        elif t == "question.ask":
            questions.append({"id": f"q-{e['seq']}", "seq": e["seq"], "by": e["actor"], "at": e["at"], "answer": None, **pl})
        elif t == "question.answer":
            q = next((q for q in questions if q["id"] == pl["question"]), None)
            if q:
                q["answer"] = {"text": pl["text"], "by": e["actor"], "at": e["at"]}
        elif t == "review_note.open":
            review_notes.append({"id": f"rn-{e['seq']}", "seq": e["seq"], "by": e["actor"], "at": e["at"], "status": "open", "thread": [], **pl})
        elif t == "review_note.respond":
            r = next((r for r in review_notes if r["id"] == pl["note"]), None)
            if r:
                r["thread"].append({"by": e["actor"], "at": e["at"], "text": pl["text"]})
                r["status"] = "responded"
        elif t == "review_note.clear":
            r = next((r for r in review_notes if r["id"] == pl["note"]), None)
            if r:
                r["status"] = "cleared"
                r["cleared"] = {"by": e["actor"], "at": e["at"]}
        elif t == "signoff.sign":
            signoffs[pl["area"]][pl["level"]] = {"by": e["actor"], "at": e["at"], "hash": pl["hash"], "seq": e["seq"]}
        elif t == "judgment.record":
            judgments.append({"seq": e["seq"], "by": e["actor"], "at": e["at"], **pl})
        elif t == "sensitive.view":
            sens_views.append({"seq": e["seq"], "by": e["actor"], "at": e["at"], **pl})
        elif t == "time.log":
            time_log.append({"seq": e["seq"], "by": e["actor"], "at": e["at"], **pl})
        elif t == "standards.update":
            standards["rules"] = pl["rules"]
        elif t == "assignment.set":
            assignments[pl["area"]][pl["role"]] = pl["staff"]
            if pl.get("due"):
                assignments[pl["area"]]["due"] = pl["due"]
        elif t == "seen":
            seen[e["actor"]] = pl["seq"]
        elif t == "filing.freeze":
            filing.update(frozen=True, frozen_at=e["at"], snapshot=pl["snapshot"], amending=False, frozen_summary=pl.get("summary"),
                          frozen_values=pl.get("values"), frozen_seq=e["seq"])
            filing.setdefault("history", []).append({"what": "frozen", "at": e["at"], "by": e["actor"], "snapshot": pl["snapshot"]})
        elif t == "filing.amend":
            filing["amending"] = True
            filing["amendments"] += 1
            filing.setdefault("history", []).append({"what": "amendment started", "at": e["at"], "by": e["actor"], "reason": pl.get("reason")})
        elif t == "client.approve":
            filing["client_approved"] = {"by": e["actor"], "at": e["at"], "snapshot": pl.get("snapshot")}
        elif t == "timeline.replay":
            tl = p.timeline[pl["timeline"]]
            replayed.append({"seq": e["seq"], **tl})
            if tl["event"] in ("efile_rejected", "efile_accepted_federal", "efile_accepted_california"):
                filing["efile"].append({"event": tl["event"], "at": tl["at"]})

    active = [a for a in adjustments.values() if a["active"]]
    current = {a["line"]: a["to"] for a in active}
    derived = _derive(p, current)
    current.update(derived)

    # --- totals: v3 + priced adjustments (the README says: multiply, don't recompute)
    s = deepcopy(p.versions["v3"]["summary"])
    fed_tax = sum(a["effect"]["federal"] for a in active if not a.get("finding") or findings[a["finding"]].get("tax_effect_source") != "engine what-if")
    ca_tax = sum(a["effect"]["california"] for a in active if not a.get("finding") or findings[a["finding"]].get("tax_effect_source") != "engine what-if")
    for f in findings.values():  # findings priced by an engine what-if use the engine numbers
        if f["status"] == "accepted" and f.get("tax_effect_source") == "engine what-if":
            fed_tax += f["tax_effect"]["federal"]
            ca_tax += f["tax_effect"]["california"]
    fed_pay = sum((a.get("payment") or {}).get("federal", 0) for a in active)
    ca_pay = sum((a.get("payment") or {}).get("california", 0) for a in active)
    working = {"federal": {**s["federal"], "total_tax": s["federal"]["total_tax"] + fed_tax, "payments": s["federal"]["payments"] + fed_pay},
               "california": {**s["california"], "total_tax": s["california"]["total_tax"] + ca_tax, "payments": s["california"]["payments"] + ca_pay}}
    for j in ("federal", "california"):
        working[j]["balance_due"] = working[j]["total_tax"] - working[j]["payments"]
    working["delta"] = {"federal_tax": fed_tax, "california_tax": ca_tax, "federal_payments": fed_pay, "california_payments": ca_pay}

    # --- areas, sign-off hashes (a sign-off is a promise about exactly this content)
    areas = {}
    for aid, label in AREAS:
        lines = sorted(k for k in p.lines["v3"] if area_of_line(k) == aid)
        content = {"lines": {k: current.get(k, p.lines["v3"][k]["value"]) for k in lines},
                   "adjustments": sorted(a["id"] for a in active if area_of_line(a["line"]) == aid),
                   "findings": sorted((f["id"], f["status"]) for f in findings.values() if f["area"] == aid)}
        h = _h(content)
        sign = {lvl: {**v, "stale": v["hash"] != h} for lvl, v in signoffs[aid].items()}
        open_f = [f["id"] for f in findings.values() if f["area"] == aid and f["status"] == "open" and f["kind"] in ("error", "judgment", "diagnostic")]
        rn = [r["id"] for r in review_notes if r.get("area") == aid and r["status"] != "cleared"]
        hours = sum(float(t.get("hours", 0)) for t in time_log if t.get("area") == aid)
        areas[aid] = {"id": aid, "label": label, "hash": h, "lines": len(lines), "signoffs": sign, "open_findings": open_f,
                      "open_review_notes": rn, "assignment": assignments[aid], "budget": p.raw["firm"]["budget_hours"].get(aid),
                      "hours": hours, "docs": [d for d, a in DOC_AREA.items() if a == aid]}

    # --- filing gate = the firm's required steps, computed, never ticked by hand
    big = [a for a in active if (abs(a["effect"]["federal"]) > 1000 or abs(a["effect"]["california"]) > 1000) and not a["approved_by"]]
    blockers = []
    open_err = [f for f in findings.values() if f["status"] == "open" and f["kind"] in ("error",)]
    if open_err:
        blockers.append(f"{len(open_err)} open errors")
    if any(r["status"] != "cleared" and r.get("blocking", True) for r in review_notes):
        blockers.append("open review notes")
    unsigned = [a["label"] for a in areas.values() if not all(lv in a["signoffs"] and not a["signoffs"][lv]["stale"] for lv in ("preparer", "reviewer"))]
    if unsigned:
        blockers.append(f"{len(unsigned)} areas missing preparer/reviewer sign-off")
    if big:
        blockers.append(f"{len(big)} adjustments over $1,000 need partner approval")
    return_hash = _h({"areas": {k: v["hash"] for k, v in areas.items()}, "working": working})
    return_sign = {lvl: {**v, "stale": v["hash"] != return_hash} for lvl, v in signoffs["return"].items()}
    if not (return_sign.get("partner") and not return_sign["partner"]["stale"]):
        blockers.append("partner sign-off")
    open_q = [q for q in questions if not q["answer"]]
    ready_for_client = not [b for b in blockers if b != "partner sign-off"]
    if not filing["client_approved"]:
        blockers.append("client approval (Form 8879)")
    elif filing["client_approved"].get("snapshot") != _h(working):
        blockers.append("client approved a different version: re-approval needed")
    filing["blockers"] = blockers
    filing["ready_for_client"] = ready_for_client
    filing["open_questions"] = len(open_q)
    filing["big_unapproved"] = [a["id"] for a in big]
    filing["working_hash"] = _h(working)

    last_seen = seen.get(viewer, 0) if viewer else 0
    since = [e for e in applied if e["seq"] > last_seen and e["actor"] != viewer and e["type"] not in ("seen", "sensitive.view")]
    if who.get(viewer or "", {}).get("role") == "client":  # clients see what concerns them, not the firm's working notes
        since = [e for e in since if (e["type"] == "question.ask" and e["payload"].get("to") == viewer) or e["type"] == "filing.freeze"]

    # --- inbox: what this person has to do next (notifications are derived, never sent and forgotten)
    inbox = []
    me = who.get(viewer or "", {})
    role = me.get("role")
    for aid, a in areas.items():
        asg = a["assignment"]
        mine = asg.get(role) == viewer if role in ("preparer", "reviewer", "partner") else False
        for lvl, s in a["signoffs"].items():
            if s["by"] == viewer and s["stale"]:
                inbox.append({"kind": "signoff_stale", "area": aid, "text": f"Your {lvl} sign-off on {a['label']} reopened: the area changed after you signed."})
        if mine and role == "preparer" and a["open_review_notes"]:
            inbox.append({"kind": "review_note", "area": aid, "text": f"{len(a['open_review_notes'])} review note(s) on {a['label']} need your response."})
        if mine and role == "reviewer" and "preparer" in a["signoffs"] and not a["signoffs"]["preparer"]["stale"] and "reviewer" not in a["signoffs"]:
            inbox.append({"kind": "ready_for_review", "area": aid, "text": f"{a['label']} is signed by the preparer and ready for your review."})
        if mine and asg.get("due"):
            inbox.append({"kind": "deadline", "area": aid, "text": f"{a['label']} due {asg['due']}."})
    for q in questions:
        if q.get("to") == viewer and not q["answer"]:
            inbox.append({"kind": "question", "target": q["id"], "text": f"Question from {who.get(q['by'], {}).get('name', q['by'])}: {q['text'][:120]}"})
        if q["by"] == viewer and q["answer"] and q["answer"]["at"] > (next((e["at"] for e in applied if e["seq"] == last_seen), "")):
            inbox.append({"kind": "answer", "target": q["id"], "text": f"{who.get(q['answer']['by'], {}).get('name')} answered your question."})
    if role == "partner" and big:
        inbox.append({"kind": "approve", "text": f"{len(big)} adjustment(s) over $1,000 need your approval."})
    if role == "client" and ready_for_client and not filing["client_approved"]:
        inbox.append({"kind": "approve_return", "text": "Your return is ready. Review it and sign Form 8879 to authorize e-filing."})

    return {
        "findings": list(findings.values()), "adjustments": list(adjustments.values()), "current_values": current,
        "working": working, "areas": areas, "notes": notes, "evidence": evidence, "verifications": [v for v in verifications if not v.get("undone")],
        "questions": questions, "review_notes": review_notes, "judgments": judgments, "sensitive_views": sens_views,
        "time_log": time_log, "standards": standards, "filing": filing, "replayed": replayed,
        "return_signoff": {"hash": return_hash, "signoffs": return_sign},
        "derived": sorted(derived), "since_last_seen": since, "last_seen": last_seen, "seq": applied[-1]["seq"] if applied else 0, "inbox": inbox,
    }
