"""Read models the reviewer works from. Everything here is derived, never stored.

Each view recomputes from the documents' printed text and the current working
values (v3 + accepted adjustments), so a reconciliation that breaks turns green
the moment the finding that explains it is accepted, and turns red again if
someone undoes it.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from .packet import AREAS, DOC_AREA, Packet, area_of_line

num = lambda s: float(str(s).replace(",", ""))
MONEY = r"([\d,]+\.\d\d)"


def cur(p: Packet, st: dict, key: str, default=0):
    if key in st["current_values"]:
        return st["current_values"][key]
    l = p.lines["v3"].get(key)
    return l["value"] if l else default


def page(p: Packet, doc: str, n: int = 1) -> str:
    return next(x["printed_content"] for x in p.docs[doc]["pages"] if x["page"] == n)


def find_money(text: str, label: str) -> float | None:
    m = re.search(re.escape(label) + r"[^0-9(]*" + MONEY, text)
    return num(m.group(1)) if m else None


def _explained_by(st: dict, code: str) -> dict | None:
    f = next((f for f in st["findings"] if f["id"] == code), None)
    return {"id": f["id"], "title": f["title"], "status": f["status"]} if f else None


def rec(id, title, area, left_label, left, right_label, right, left_refs, right_refs, note="", explained_by=None, tol=1.0):
    diff = round((left or 0) - (right or 0), 2)
    return {"id": id, "title": title, "area": area, "left": {"label": left_label, "value": left, "refs": left_refs},
            "right": {"label": right_label, "value": right, "refs": right_refs}, "diff": diff,
            "status": "agrees" if abs(diff) < tol else "break", "note": note, "explained_by": explained_by}


# --------------------------------------------------------------------- reconciliations
def reconciliations(p: Packet, st: dict) -> list[dict]:
    R = []
    w2 = {d: page(p, d) for d in ("D08", "D09")}
    box = lambda d, b: find_money(w2[d], f"Box {b} ")
    R.append(rec("w2-wages", "W-2 box 1 wages (each W-2 once) = Form 1040 line 1a", "wages_and_stock_compensation",
                 "W-2s D08 + D09", box("D08", 1) + box("D09", 1), "F1040.1a", cur(p, st, "F1040.1a"),
                 ["doc:D08#page1", "doc:D09#page1"], ["F1040.1a"], "D10 is a phone photo of the D09 W-2 and is excluded so it is not counted twice."))
    R.append(rec("w2-fed-wh", "W-2 box 2 federal withholding = Form 1040 line 25a", "payments",
                 "W-2s D08 + D09", box("D08", 2) + box("D09", 2), "F1040.25a", cur(p, st, "F1040.25a"),
                 ["doc:D08#page1", "doc:D09#page1"], ["F1040.25a"]))
    R.append(rec("w2-ca-wh", "W-2 box 17 California withholding = 540NR line 71", "california",
                 "W-2s D08 + D09", box("D08", 17) + box("D09", 17), "F540NR.71", cur(p, st, "F540NR.71"),
                 ["doc:D08#page1", "doc:D09#page1"], ["F540NR.71"]))
    stub = page(p, "D73")
    ca_part = find_money(stub, "CA taxable wages")
    R.append(rec("ca-wages", "California-source wages = Corvane box 16 + Halvorsen pay through the move (paystub)", "california",
                 "D08 box 16 + D73 CA wages to 07/15", box("D08", 16) + ca_part, "SchCA540NR.1.E", cur(p, st, "SchCA540NR.1.E"),
                 ["doc:D08#page1", "doc:D73#page1", "household:residency"], ["SchCA540NR.1.E"],
                 "Residency ended 2025-07-14. Halvorsen payroll kept CA as work state to 9/30 by mistake (qa-45).",
                 _explained_by(st, "chk-ca-wages-after-move")))

    # TieOut: third-party reporting to books to Schedule C
    nec = sum(find_money(page(p, d), "nonemployee compensation") for d in ("D16", "D17", "D18", "D19", "D20"))
    k = find_money(page(p, "D21"), "Box 1a gross amount of payment card/third party network transactions")
    d15 = page(p, "D15", 3)
    no1099 = find_money(d15, "Deposits from clients who issued no Form 1099:")
    overlap = find_money(d15, "of which")  # Atlas card payments: in the NEC and in the 1099-K
    p_and_l = page(p, "D14")
    books = find_money(p_and_l, "Total income")
    R.append(rec("tieout-books", "1099-NEC + 1099-K - overlap + unreported clients = books sales", "business",
                 f"NEC {nec:,.0f} + K {k:,.0f} - Atlas card overlap {overlap:,.0f} + no-1099 clients {no1099:,.0f}", nec + k - overlap + no1099,
                 "Books total income (D14)", books, ["doc:D16", "doc:D17", "doc:D18", "doc:D19", "doc:D20", "doc:D21", "doc:D15#page3"], ["doc:D14#page1"],
                 "This is the reconciliation the 2028 IRS exam letter asks for (third parties reported 154,400; books 151,300)."))
    R.append(rec("books-schc", "Books sales = Schedule C gross receipts", "business", "Books total income (D14)", books,
                 "SchC.1", cur(p, st, "SchC.1"), ["doc:D14#page1"], ["SchC.1"],
                 "Engine rule R-SCHC-GROSS added the 1099-K on top of books.", _explained_by(st, "chk-1099k-already-in-books")))

    # mileage: unique pages only
    totals, bodies = {}, set()
    for pg in p.docs["D23"]["pages"]:
        body = re.sub(r"^\(.*?\)\s*", "", pg["printed_content"]).strip()
        t = num(re.search(r"Page total ([\d,]+)", pg["printed_content"]).group(1))
        if body not in bodies:
            totals[pg["page"]] = t
        bodies.add(body)
    miles = sum(totals.values())
    R.append(rec("mileage", "Mileage log (unique pages) x rate = Schedule C car expense", "business",
                 f"{miles:,.0f} mi x {p.raw['engine_reference']['parameters']['mileage_rate']}", round(miles * p.raw["engine_reference"]["parameters"]["mileage_rate"]),
                 "SchC.9", cur(p, st, "SchC.9"), [f"doc:D23#page{n}" for n in totals], ["SchC.9"], "Page 3 is a second scan of page 2.",
                 _explained_by(st, "chk-duplicate-page")))

    # brokers
    for did, name in (("D74", "Brightpath"), ("D31", "Meridian (corrected)")):
        t1 = page(p, did, 1)
        lots = sales_lots(p, st, account=did)
        proceeds = sum(l["proceeds"] for l in lots)
        if did == "D74":
            summ = find_money(t1, "short-term covered proceeds") + find_money(t1, "long-term covered proceeds")
        else:
            summ = find_money(t1, "total proceeds")
        R.append(rec(f"broker-{did}", f"{name} 1099-B summary proceeds = lots on Form 8949", "investments_and_digital_assets",
                     f"{did} summary", summ, f"{len(lots)} lots on the return", round(proceeds, 2), [f"doc:{did}#page1"], [l["key"] for l in lots][:3],
                     "Page 32 (Additional transactions) was not read by the pipeline." if did == "D31" else "",
                     _explained_by(st, "chk-broker-page-unread") if did == "D31" else None))
    da = find_money(page(p, "D34"), "Total gross proceeds")
    cl = sales_lots(p, st, account="D34")
    R.append(rec("crypto-1099da", "Coinhaven 1099-DA proceeds = digital-asset lots", "investments_and_digital_assets", "D34 total", da,
                 f"{len(cl)} lots", round(sum(l['proceeds'] for l in cl), 2), ["doc:D34#page1"], ["F8949.H.total", "F8949.K.total"]))

    # interest by payer (a payer appearing twice is a break)
    payers = defaultdict(float)
    for kk, l in p.lines["v3"].items():
        if kk.startswith("SchB.1.") and cur(p, st, kk):
            payers["Northlake" if "Northlake" in l["label"] else l["label"]] += cur(p, st, kk)
    doc_int = find_money(page(p, "D29"), "Box 1 interest income")
    R.append(rec("interest-northlake", "Northlake sweep interest (one 1099-INT) = Schedule B", "investments_and_digital_assets",
                 "D29 box 1 (same account 7731 as the D28 composite)", doc_int, "Schedule B, Northlake lines", payers["Northlake"],
                 ["doc:D29#page1", "doc:D28#page1"], ["SchB.1.1", "SchB.1.2"], explained_by=_explained_by(st, "chk-interest-twice")))

    # rents
    R.append(rec("rents", "1099-MISC rents = Schedule E rents, Fremont Way", "rentals_and_sale", "D46 1099-MISC box 1",
                 find_money(page(p, "D46", 2), "box 1 rents"), "SchE.3A", cur(p, st, "SchE.3A"), ["doc:D46#page2"], ["SchE.3A"]))
    R.append(rec("1099s", "1099-S gross proceeds = Form 4797 sales price", "rentals_and_sale", "D52 box 2",
                 find_money(page(p, "D52"), "Box 2 gross proceeds"), "F4797.21", cur(p, st, "F4797.21"), ["doc:D52#page1"], ["F4797.21"]))

    # mortgage interest: 1098s are complete; statements are not added
    i1098 = find_money(page(p, "D55"), "Box 1 mortgage interest received") + find_money(page(p, "D57"), "Box 1 mortgage interest received")
    pts = find_money(page(p, "D55"), "Box 6 points paid on purchase")
    R.append(rec("mortgage", "Forms 1098 (interest + purchase points) = Schedule A line 8a", "deductions_and_credits",
                 "D55 + D57 box 1 + D55 box 6", i1098 + pts, "SchA.8a", cur(p, st, "SchA.8a"), ["doc:D55#page1", "doc:D57#page1"], ["SchA.8a"],
                 "The payoff statement D56 says its interest is already on the 1098.", _explained_by(st, "chk-payoff-interest-double")))

    # estimates vs agency records
    tx = p.raw["tax_agency_records"]["irs_account_transcript_2025"][-1]["transactions"]
    irs_est = sum(t["amount"] for t in tx if t["code"] == "670" and "Estimated" in t["description"])
    R.append(rec("fed-estimates", "IRS transcript estimated payments = Form 1040 line 26", "payments", "IRS transcript (code 670)", irs_est,
                 "F1040.26", cur(p, st, "F1040.26"), ["agency:/irs_account_transcript_2025/1/transactions"], ["F1040.26"],
                 "Q4 came from the client's memory ('4,000 I think').", _explained_by(st, "chk-estimates-vs-irs")))
    ftb = sum(x["amount"] for x in p.raw["tax_agency_records"]["ftb_account"]["tax_year_2025_payments"])
    R.append(rec("ca-estimates", "FTB account 2025 payments = 540NR line 72", "payments", "FTB account, tax year 2025", ftb,
                 "F540NR.72", cur(p, st, "F540NR.72"), ["agency:/ftb_account/tax_year_2025_payments"], ["F540NR.72"],
                 "The 9/15/2025 payment was designated tax year 2024.", _explained_by(st, "chk-ca-payment-other-year")))
    ext = next(t["amount"] for t in tx if "extension" in t["description"].lower() and t["code"] == "670")
    R.append(rec("extension", "Extension payment on transcript = Schedule 3 line 10", "payments", "IRS transcript 2026-04-14", ext,
                 "Sch3.10", cur(p, st, "Sch3.10"), ["agency:/irs_account_transcript_2025/1/transactions/4"], ["Sch3.10"]))

    # independent recomputations
    ss_wh = find_money(w2["D08"], "Box 4 ") + find_money(w2["D09"], "Box 4 ")
    cap = p.raw["engine_reference"]["parameters"]["ss_wage_base"] * 0.062
    R.append(rec("excess-ss", "Recomputed excess social security (two employers) = Schedule 3 line 11", "payments",
                 f"{ss_wh:,.2f} withheld - {cap:,.2f} max", round(ss_wh - cap), "Sch3.11", cur(p, st, "Sch3.11"),
                 ["doc:D08#page1", "doc:D09#page1", "ref:param.ss_wage_base"], ["Sch3.11"]))
    b = 21300
    for yr, (inc, dist) in {2023: (14100, 20000), 2024: (16900, 30000)}.items():
        b = max(0, b + inc - dist)
    R.append(rec("scorp-basis", "Recomputed S corp stock basis at 1/1/2025 = Form 7203 line 1", "pass_throughs_and_basis",
                 "21,300 (2022) +14,100 -20,000 (2023, D40) +16,900 -30,000 (2024)", b, "F7203.1", cur(p, st, "F7203.1"),
                 ["doc:D40#page1", "py:/basis_records/scorp_lindqvist_family_woodworks", "py:/return_2024/K1_1120S"], ["F7203.1"],
                 "The 2023 K-1 (D40) closes the gap the prior preparer left open."))
    conv = find_money(page(p, "D41"), "Box 1 gross distribution")
    taxable = round(conv - conv * min(1, 14000 / conv), 0)  # pro-rata: basis / (year-end value 0 + converted)
    R.append(rec("8606", "Recomputed backdoor Roth taxable amount = Form 8606 line 18", "wages_and_stock_compensation",
                 f"{conv:,.0f} converted - 14,000 basis (pro-rata, year-end IRA value 0)", taxable, "F8606.18", cur(p, st, "F8606.18"),
                 ["doc:D41#page1", "doc:D42#page1", "doc:D43#page1"], ["F8606.18"]))
    return R


# --------------------------------------------------------------------- sales detail
LOT_DOC = {"X": "D74", "M": "D31", "N": "D28", "C": "D34", "S": "D39"}
_lot_page_cache: dict = {}


def _lot_page(p: Packet, doc: str, lot: str) -> int:
    k = (doc, lot)
    if k not in _lot_page_cache:
        _lot_page_cache[k] = next((pg["page"] for pg in p.docs[doc]["pages"] if re.search(rf"\b{lot}\b", pg["printed_content"])), 1)
    return _lot_page_cache[k]


def sales_lots(p: Packet, st: dict, account: str | None = None) -> list[dict]:
    out = []
    keys = list(p.lines["v3"].keys()) + [a["line"] for a in st["adjustments"] if a["active"] and a["line"] not in p.lines["v3"]]
    for key in dict.fromkeys(keys):
        parts = key.split(".")
        if len(parts) != 3 or parts[0] != "F8949" or parts[2] == "total":
            continue
        lot = parts[2]
        doc = LOT_DOC.get(lot[0], "D39") if lot != "SCORP" else "D39"
        if account and doc != account and not (account == "D34" and doc == "D34"):
            continue
        l = p.lines["v3"].get(key)
        label = l["label"] if l else next((a.get("note") or key for a in st["adjustments"] if a["line"] == key), key)
        m = re.search(r"acquired (\S+), sold (\S+?)[;)]? ?(?:; )?proceeds ([\d,]+\.\d\d), basis ([\d,]+\.\d\d)(?:, adjustment(?: [A-Z])? ([\d,]+\.\d\d))?", label)
        gain = cur(p, st, key, None)
        if gain is None:
            continue
        flags = []
        if m and num(m.group(4)) == 0 and lot[0] in "NC":
            flags.append("broker basis 0")
        if m and m.group(5) and lot[0] == "X":
            flags.append("wash sale")
        if key in st["current_values"]:
            flags.append("adjusted")
        if lot[0] == "C" and m and m.group(1) == "2025-06-01":
            flags.append("basis unknown")
        if not l:
            flags.append("added by us")
        removed = gain == 0 and l and l["value"] != 0 and key in st["current_values"]
        if removed:
            flags.append("removed")
        out.append({"key": key, "box": parts[1], "lot": lot, "doc": doc, "page": _lot_page(p, doc, lot) if lot != "SCORP" else 1,
                    "desc": label.split(" (acquired")[0] if l else label, "acquired": m.group(1) if m else None, "sold": m.group(2) if m else None,
                    "proceeds": num(m.group(3)) if m and not removed else 0.0, "basis": num(m.group(4)) if m and not removed else 0.0, "adjustment": num(m.group(5)) if m and m.group(5) else 0.0,
                    "gain": gain, "term": "long" if parts[1] in "DEFKL" else "short", "flags": flags})
    return out


def sales_summary(p: Packet, st: dict) -> dict:
    lots = sales_lots(p, st)
    groups = defaultdict(lambda: {"n": 0, "proceeds": 0.0, "basis": 0.0, "adj": 0.0, "gain": 0.0, "flagged": 0})
    names = {"D74": "Brightpath (direct indexing)", "D31": "Meridian (joint, corrected)", "D28": "Northlake (Ngozi)", "D34": "Coinhaven (crypto)", "D39": "Woodworks S corp"}
    for l in lots:
        g = groups[(l["doc"], l["box"])]
        g["n"] += 1
        g["proceeds"] += l["proceeds"]
        g["basis"] += l["basis"]
        g["adj"] += l["adjustment"]
        g["gain"] += l["gain"]
        g["flagged"] += 1 if set(l["flags"]) - {"wash sale"} else 0
    return {"lots": lots, "groups": [{"account": names.get(d, d), "doc": d, "box": b, **{k: round(v, 2) for k, v in g.items()}} for (d, b), g in sorted(groups.items())]}


# --------------------------------------------------------------------- books to tax
def books_to_tax(p: Packet, st: dict) -> dict:
    t = page(p, "D14")
    f = lambda lbl: find_money(t, lbl)
    books_net = f("Net income")
    steps = [
        ("Net income per books (QuickBooks, cash basis)", books_net, ["doc:D14#page1"], None),
        ("Add back: Erik's health insurance (moves to Schedule 1 line 17)", f("Insurance - health (Erik)"), ["doc:D14#page1", "Sch1.17"], None),
        ("Add back: book depreciation (straight-line 5 years)", f("Depreciation"), ["doc:D14#page2"], None),
        ("Less: tax depreciation (100% special allowance)", -cur(p, st, "SchC.13"), ["SchC.13", "doc:D22#page1"], None),
        ("Add back: actual fuel (replaced by standard mileage)", f("Car and truck - fuel"), ["doc:D14#page1"], None),
        ("Less: standard mileage", -cur(p, st, "SchC.9"), ["SchC.9", "doc:D23"], "chk-duplicate-page"),
        ("Add back: 50% of meals (nondeductible)", f("Meals") - cur(p, st, "SchC.24b"), ["doc:D14#page1", "SchC.24b"], None),
        ("Less: home office (simplified)", -cur(p, st, "SchC.30"), ["SchC.30", "doc:D24#page1"], None),
        ("Add back: personal share of phone, internet, Spotify (books deducted 100%)", (f("Telephone") + f("Internet") - cur(p, st, "SchC.25")) + (f("Software and subscriptions") - cur(p, st, "SchC.27a.1")), ["call-01", "SchC.25", "SchC.27a.1"], "chk-personal-use"),
        ("Gross receipts above books (engine added the 1099-K)", cur(p, st, "SchC.1") - f("Total income"), ["SchC.1", "doc:D21#page1"], "chk-1099k-already-in-books"),
    ]
    rows, total = [], 0.0
    for label, amt, refs, finding in steps:
        amt = round(amt or 0, 2)
        total += amt
        rows.append({"label": label, "amount": amt, "refs": refs, "finding": _explained_by(st, finding) if finding else None})
    schc_working = cur(p, st, "SchC.31")  # v3 plus accepted adjustments, rolled up (state._derive)
    return {"rows": rows, "computed": round(total, 2), "schedule_c": schc_working, "v3_schedule_c": p.lines["v3"]["SchC.31"]["value"],
            "diff": round(total - schc_working, 2), "taxable_income_chain": [
                {"key": k, "label": p.lines["v3"][k]["label"], "value": cur(p, st, k)} for k in
                ("SchC.31", "Sch1.3", "F1040.8", "F1040.9", "F1040.11", "F1040.15")]}


# --------------------------------------------------------------------- state split
def state_split(p: Packet, st: dict) -> dict:
    rows = defaultdict(dict)
    for k, l in p.lines["v3"].items():
        m = re.fullmatch(r"SchCA540NR\.(\d+)\.([A-E])", k)
        if m:
            rows[int(m.group(1))][m.group(2)] = {"key": k, "value": cur(p, st, k), "label": l["label"], "note": l.get("note"), "rule": l.get("rule")}
    out = []
    for n in sorted(rows):
        r = rows[n]
        name = next(iter(r.values()))["label"].split(" - ")[0]
        d = (r.get("D") or {}).get("value")
        e = (r.get("E") or {}).get("value")
        out.append({"line": n, "name": name, "cols": r, "ca_share": (e / d) if d else None})
    res = p.raw["household"]["residency"]
    days = p.raw["engine_reference"]["parameters"].get("ca_resident_days")
    return {"residency": res, "ca_resident_days": days, "year_days": p.raw["engine_reference"]["parameters"].get("year_days"), "rows": out,
            "ratio": {"F540NR.32": cur(p, st, "F540NR.32"), "F540NR.17": cur(p, st, "F540NR.17"), "F540NR.34": cur(p, st, "F540NR.34")},
            "ridgeline": page(p, "D38")}


# --------------------------------------------------------------------- variance vs prior year
def variance(p: Packet, st: dict) -> dict:
    std = st["standards"].get("variance_review", {"flag_if_change_over_percent": 10, "and_over_amount": 1000})
    py = p.raw["prior_years"]["return_2024"]["lines"]
    labels = p.raw["prior_years"]["return_2024"].get("line_labels", {})
    rows = []
    for k, pv in py.items():
        if not isinstance(pv, (int, float)):
            continue
        cv = cur(p, st, k, None)
        if cv is None or not isinstance(cv, (int, float)):
            rows.append({"key": k, "label": labels.get(k, k), "py": pv, "cy": None, "change": None, "pct": None, "flag": abs(pv) >= std["and_over_amount"], "note": "Not on the 2025 return"})
            continue
        ch = cv - pv
        pct = (ch / abs(pv) * 100) if pv else None
        flag = abs(ch) > std["and_over_amount"] and (pct is None or abs(pct) > std["flag_if_change_over_percent"])
        rows.append({"key": k, "label": labels.get(k) or p.lines["v3"].get(k, {}).get("label", k), "py": pv, "cy": cv, "change": ch, "pct": pct, "flag": flag})
    return {"standard": std, "rows": rows, "prior_preparer": p.raw["prior_years"]["prior_preparer_workpaper"],
            "prior_preparer_vs_us": PRIOR_VS_US}


PRIOR_VS_US = [
    {"topic": "S corp basis", "prior": "2023 K-1 missing; 'assumed basis sufficient' for 2024.", "us": "2023 K-1 found (D40). Basis rolled 2022-2025: 2,300 at 1/1/2025; 21,215 of 2025 distributions are capital gain.", "refs": ["doc:D40#page1", "F7203.1"]},
    {"topic": "IRA basis", "prior": "7,000 per client; 5498 not obtained.", "us": "2024 Form 5498 (D42) confirms 7,000. Client now says 'no prior basis' (qa-31): the records win.", "refs": ["doc:D42#page1", "qa-31", "F8606.2"]},
    {"topic": "Home office", "prior": "300 sq ft, 'client to confirm'.", "us": "Measured 220 sq ft (Sacramento) and 260 sq ft (Austin). 2024 was overstated by 80 sq ft (400 of deduction); immaterial, documented, no amendment.", "refs": ["doc:D24#page1", "SchC.30"]},
    {"topic": "Foreign inheritance", "prior": "'2023 Form 3520 - discussed? (no note of resolution)'.", "us": "Open. The Swedish account came from Erik's mother in 09/2023 (qa-07, D36). Outside this engagement; raised with the client as an outside filing.", "refs": ["doc:D36#page1", "qa-07"]},
    {"topic": "FBAR", "prior": "'Filed by client separately'.", "us": "Still required for 2025 (max about 147,000 USD). Outside scope; deadline tracked (10/15/2026).", "refs": ["doc:D36#page1"]},
    {"topic": "Preparer", "prior": "Delta River Tax Services.", "us": "Miraflores. Carryovers agreed to D06/D07 and used as given.", "refs": ["doc:D06#page6", "doc:D07#page6"]},
]


# --------------------------------------------------------------------- completeness
OUTSIDE_FILINGS = [
    {"id": "fbar", "what": "FinCEN 114 (FBAR) for Sparbanken Norrland", "who": "Client (outside engagement)", "due": "2026-10-15", "why": "Max balance SEK 1,452,300 (about 147,000 USD) is over 10,000.", "refs": ["doc:D36#page1", "eng-fbar-outside-return"]},
    {"id": "1099nec", "what": "Forms 1099-NEC to Mara Quintero (4,800) and Dev Patel (2,600)", "who": "Lindqvist Studio (outside engagement)", "due": "2026-02-02 (late)", "why": "Paid 600+ by ACH.", "refs": ["doc:D27#page1", "chk-1099nec-not-filed"]},
    {"id": "3520", "what": "Form 3520 for 2023 (foreign inheritance over 100,000)", "who": "Client; needs a separate engagement", "due": "Past due (2023 return)", "why": "Erik inherited the Swedish account from his mother in 09/2023; the prior preparer left it unresolved.", "refs": ["doc:D36#page1", "doc:D07#page3", "qa-07"]},
    {"id": "or", "what": "Oregon nonresident return for Woodworks income", "who": "Covered by the S corp's Oregon composite return", "due": "-", "why": "D39: Oregon tax 1,580 paid on Erik's behalf.", "refs": ["doc:D39#page2"]},
    {"id": "az", "what": "Arizona nonresident return for Ridgeline income", "who": "Covered by the fund's Arizona composite return", "due": "-", "why": "D38: no Arizona filing required by the partner.", "refs": ["doc:D38#page1"]},
    {"id": "ada", "what": "Ada's own 2025 Form 1040 (summer W-2 4,100)", "who": "Ada, consumer software", "due": "2026-04-15", "why": "Must check 'someone can claim you' (she did).", "refs": ["household:ada"]},
    {"id": "5329", "what": "Form 5329 if Erik leaves the SEP excess in", "who": "On this return if not withdrawn by the due date", "due": "2026-10-15", "why": "6% excise on the excess every year it stays.", "refs": ["chk-sep-excess"]},
    {"id": "8867", "what": "Form 8867 paid preparer due diligence", "who": "Preparer (filed with this return)", "due": "With the return", "why": "Child tax credit and credit for other dependents are claimed.", "refs": ["eng-due-diligence-required"]},
]


def completeness(p: Packet, st: dict, docs: list[dict]) -> dict:
    acc = {}
    for n in st["notes"]:
        if n.get("target", "").startswith("D") and len(n.get("target", "")) == 3:
            acc.setdefault(n["target"], []).append(n)
    by_status = defaultdict(int)
    for d in docs:
        by_status[d["status"]] += 1
    return {"documents": by_status, "documents_total": len(docs), "outside_filings": OUTSIDE_FILINGS,
            "areas": [{"id": a, "label": l, "signed": st["areas"][a]["signoffs"]} for a, l in AREAS],
            "considered": [{"area": a["label"], "open_findings": len(a["open_findings"]), "hours": a["hours"], "budget": a["budget"]} for a in st["areas"].values()]}


# --------------------------------------------------------------------- records a CPA expects
def records(p: Packet, st: dict) -> dict:
    v3 = p.versions["v3"]
    L = lambda *keys: [{"key": k, "label": p.lines["v3"][k]["label"], "value": cur(p, st, k), "py": p.raw["prior_years"]["return_2024"]["lines"].get(k)} for k in keys if k in p.lines["v3"]]
    assets = []
    for a in v3["assets"]:
        assets.append({**a, "recapture": ({"unrecaptured_1250": cur(p, st, "SchD.19") if a["asset_id"].startswith("AUS") else None,
                                           "gain_4797": cur(p, st, "F4797.25")} if a.get("disposed") else None)})
    k1 = []
    for did, ent, lines in (("D39", "Lindqvist Family Woodworks, Inc. (1120-S, 20%)", {"box1": "SchE.28A", "box4": "SchB.1.7", "box16d": "F7203.6", "qbi": "F8995.2.2", "or_tax": "ScheduleS.credit"}),
                            ("D37", "Ridgeline Real Estate Fund III LP (1065, limited partner)", {"box2": "SchE.28B", "box5": "SchB.1.8", "box9a": "SchD.12", "box21": "Sch3.1", "box19a": None})):
        rows = []
        for e in p.ev_by_doc.get(did, []):
            dest = lines.get(e["field"], "-")
            rows.append({"ev": e["id"], "field": e["field"], "label": e["label"], "value": e["value"], "line": dest, "line_value": cur(p, st, dest) if dest and dest != "-" else None})
        k1.append({"doc": did, "entity": ent, "rows": rows})
    return {
        "summary": L("F1040.1z", "F1040.2b", "F1040.3b", "F1040.7", "F1040.8", "F1040.9", "F1040.10", "F1040.11", "F1040.12", "F1040.13", "F1040.15", "F1040.16", "F1040.22", "F1040.23", "F1040.24", "F1040.33", "F1040.37"),
        "tax_computation": L("F1040.15", "F1040.16", "F6251.4", "F6251.7", "F6251.11", "F1040.18", "F1040.19", "F1040.20", "F1040.22", "Sch2.4", "Sch2.11", "Sch2.12", "F1040.24"),
        "depreciation": assets,
        "rentals": L("SchE.3A", "SchE.20A", "SchE.21A", "SchE.22A", "SchE.3B", "SchE.20B", "SchE.21B", "SchE.22B", "F8582.1a", "F8582.1b", "F8582.1c", "F8582.3a", "F8582.4", "F4797.21", "F4797.22", "F4797.23", "F4797.25", "SchD.19"),
        "k1": k1,
        "retirement_foreign": L("F8606.2", "F8606.8", "F8606.18", "Sch1.16", "F8889.9", "F8889.16", "SchB.1.6", "SchB.7a", "F8938.1.max", "F8938.1.ye", "F8938.req", "Sch3.1"),
        "deductions_credits": L("SchA.5a", "SchA.5b", "SchA.5d", "SchA.5e", "SchA.8a", "SchA.8c", "SchA.11", "SchA.12", "SchA.17", "F8995.39", "F8812.8", "F8812.11", "F8812.12", "F8863.30", "F8863.7", "F2441.2", "F2441.31"),
        "payments": L("F1040.25a", "F1040.26", "Sch3.10", "Sch3.11", "F1040.33", "F1040.37", "F2210.19", "F540NR.71", "F540NR.72", "F540NR.78", "F540NR.97"),
        "carryovers": {"in": p.raw["prior_years"]["carryovers_into_2025"], "out": v3["carryovers_out"]},
        "basis": p.raw["prior_years"]["basis_records"],
        "scorp_rollforward": [
            {"year": 2022, "start": None, "income": None, "distributions": None, "end": 21300, "source": "client worksheet (D07)"},
            {"year": 2023, "start": 21300, "income": 14100, "distributions": 20000, "end": 15400, "source": "D40 (found 2026-06-05)"},
            {"year": 2024, "start": 15400, "income": 16900, "distributions": 30000, "end": 2300, "source": "2024 K-1 (D06)"},
            {"year": 2025, "start": 2300, "income": 18485, "distributions": 42000, "end": 0, "source": "D39; 21,215 in excess of basis", "excess": 21215},
        ],
    }


# --------------------------------------------------------------------- notice response packet
def notice_packet(p: Packet, st: dict, notice_id: str) -> dict:
    n = next(x for x in p.raw["tax_agency_records"]["notices"] if x["id"] == notice_id)
    items = []
    if notice_id == "N-2025-L566":
        recs = {r["id"]: r for r in reconciliations(p, st)}
        items = [
            {"item": n["items_under_examination"][0], "lines": ["SchA.12", "F8283.A1.stock", "F8283.A1.vehicle"],
             "evidence": ["doc:D65#page1", "doc:D66#page1", "qa-39", "call-01"], "findings": ["chk-vehicle-over-proceeds"],
             "answer": "Stock: 200 sh to a donor-advised fund, FMV 14,500 (high/low average 72.50), held since 2019; acknowledgment D65. Vehicle: deduction limited to gross proceeds 2,900 per Form 1098-C box 4c (sold 09/09/2025), not the 6,000 the client estimated."},
            {"item": n["items_under_examination"][1], "lines": ["SchC.1"], "evidence": ["doc:D14#page1", "doc:D15#page3", "doc:D16", "doc:D17", "doc:D21"],
             "findings": ["chk-1099k-already-in-books"], "recon": recs.get("tieout-books"),
             "answer": "1099-NEC 142,000 + 1099-K 12,400 - 12,400 Atlas card payments reported on both + 9,300 from clients who issued no 1099 = 151,300 = books = Schedule C line 1."},
        ]
    for it in items:
        it["line_values"] = [{"key": k, "label": p.lines["v3"].get(k, {}).get("label", k), "filed": (st["filing"].get("frozen_values") or {}).get(k, cur(p, st, k)), "v3": p.lines["v3"].get(k, {}).get("value")} for k in it["lines"]]
        it["findings"] = [_explained_by(st, f) for f in it["findings"]]
        it["evidence"] = [p.resolve(r) for r in it["evidence"]]
    return {"notice": n, "items": items, "filing": {k: st["filing"].get(k) for k in ("frozen", "frozen_at", "snapshot")},
            "signoffs": st["return_signoff"]["signoffs"], "working": st["working"]}


# --------------------------------------------------------------------- roll forward / plan next year
def rollforward(p: Packet, st: dict) -> dict:
    plan = p.raw["planning_reference_2026"]
    fed_tax = st["working"]["federal"]["total_tax"]
    ca_tax = st["working"]["california"]["total_tax"]
    fed_sh = round(fed_tax * 1.10)
    ca_sh = round(ca_tax * 1.10)
    return {"carryovers_out": p.versions["v3"]["carryovers_out"], "planning": plan,
            "federal_safe_harbor": {"total": fed_sh, "installments": [{"due": d, "amount": round(fed_sh / 4)} for d in plan["federal_estimate_due_dates"]]},
            "california_safe_harbor": {"total": ca_sh, "installments": [{"due": d, "amount": round(ca_sh * pct)} for d, pct in zip(plan["california_estimate_due_dates"], plan["california_installment_percentages"])]},
            "carry_forward": [
                {"what": "S corp stock basis (Form 7203)", "value": "0 at 12/31/2025; any 2026 distribution before income is a gain", "refs": ["F7203.15"]},
                {"what": "Minimum tax credit (Form 8801)", "value": "3,871 from the ISO exercise", "refs": ["F6251.11"]},
                {"what": "ISO shares (AMT basis 52 / regular 12 per share)", "value": "1,000 sh still held (qa-06)", "refs": ["doc:D12#page1"]},
                {"what": "SEP excess", "value": "Withdraw before 10/15/2026 or 6% excise", "refs": ["chk-sep-excess"]},
                {"what": "Ridgeline capital account", "value": "63,660 (outside basis never computed: compute in 2026)", "refs": ["doc:D37#page1"]},
                {"what": "California basis differences (studio equipment, appliances)", "value": "Track until disposed", "refs": ["FTB3885A.STU-PRINTER"]},
                {"what": "Open questions and judgments", "value": f"{len([q for q in st['questions'] if not q['answer']])} open questions, {len(st['judgments'])} judgments carried with history", "refs": []},
            ]}
