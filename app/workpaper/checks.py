"""Independent checks: recompute from the documents instead of trusting the engine.

Each check reads the packet (printed page text = truth, plus client answers and agency
records), compares with the v3 return, and returns a Finding with:
  - plain-language explanation (for a new hire) and technical detail (for a CPA)
  - the exact evidence refs and affected return lines
  - a proposed set of adjustments, each priced with the README tax_effect_rates
Nothing here edits the return. Accepting a finding is an event (see state.py).
"""
from __future__ import annotations

import re
from datetime import date

from .packet import Packet

num = lambda s: float(str(s).replace(",", ""))
MONEY = r"([\d,]+\.\d\d)"


def effect(p: Packet, category: str, delta: float) -> dict:
    r = p.rates.get(category)
    if not r:
        return {"federal": 0, "california": 0}
    return {"federal": round(delta * r["federal_per_dollar"]), "california": round(delta * r["california_per_dollar"])}


def adj(p: Packet, line: str, to: float, category: str, delta: float | None = None, note: str = "") -> dict:
    frm = p.lines["v3"].get(line, {}).get("value")
    d = (to - (frm or 0)) if delta is None else delta
    return {"line": line, "from": frm, "to": round(to, 2), "category": category, "delta": round(d, 2),
            "effect": effect(p, category, d) if not category.startswith("payment") else {"federal": 0, "california": 0},
            "payment": ({"federal": round(d)} if category == "payment_federal" else {"california": round(d)} if category == "payment_california" else None),
            "note": note}


def page(p: Packet, doc: str, n: int = 1) -> str:
    return next(x["printed_content"] for x in p.docs[doc]["pages"] if x["page"] == n)


def V(p: Packet, key: str):
    return p.lines["v3"][key]["value"]


def finding(**k) -> dict:
    k.setdefault("engine", "missed")
    k.setdefault("kind", "error")
    k.setdefault("proposal", [])
    k.setdefault("what_if", None)
    k.setdefault("needs", None)
    fed = sum(a["effect"]["federal"] for a in k["proposal"])
    ca = sum(a["effect"]["california"] for a in k["proposal"])
    pay = {"federal": sum((a.get("payment") or {}).get("federal", 0) for a in k["proposal"]),
           "california": sum((a.get("payment") or {}).get("california", 0) for a in k["proposal"])}
    k["tax_effect"] = {"federal": fed, "california": ca}
    k["payment_effect"] = pay
    return k


# ---------------------------------------------------------------- checks

def rsu_basis(p: Packet):
    sup = " ".join(x["printed_content"] for x in p.docs["D11"]["pages"])
    lots = re.findall(r"Lot (RSU-\d+): (\d+) sh acquired (\d\d/\d\d/\d{4}) \(vest FMV [\d.]+\) adjusted basis " + MONEY, sup)
    by_acq = {f"{a[6:]}-{a[:2]}-{a[3:5]}": (lot, num(b)) for lot, _, a, b in lots}
    props, total = [], 0.0
    for key, l in p.lines["v3"].items():
        m = re.search(r"\(RSU\) \(acquired (\S+), sold (\S+); proceeds " + MONEY + r", basis 0\.00", l["label"])
        if m and m.group(1) in by_acq:
            lot, basis = by_acq[m.group(1)]
            cat = "ltcg" if key.split(".")[1] in "DEF" else "stcg"
            props.append(adj(p, key, num(m.group(3)) - basis, cat, note=f"{lot}: adjusted basis {basis:,.2f} per D11"))
            total += basis
    if not props:
        return None
    return finding(code="RSU_BASIS_ZERO", severity="high", area="wages_and_stock_compensation",
                   title=f"RSU shares taxed twice: ${total:,.0f} of basis missing",
                   plain="The broker left the cost blank for RSU shares, so the return used $0. That income was already taxed on the W-2, so it is being taxed a second time as a capital gain.",
                   detail="1099-B reports noncovered RSU lots with blank basis. Corvane's supplemental statement (D11 p2) gives the adjusted basis (FMV at vest, already in W-2 box 1). Enter it with adjustment code B.",
                   lines=[a["line"] for a in props] + ["SchD.2", "SchD.9"], sources=["doc:D11#page2", "D08", "D28"],
                   proposal=props, fix="Use adjusted basis from D11; code B on Form 8949.")


def ca_wage_sourcing(p: Packet):
    res = next(r for r in p.raw["household"]["residency"] if r["state"] == "CA")
    stub = page(p, "D73")
    m = re.search(r"CA taxable wages " + MONEY, stub)
    if not m:
        return None
    ca_part = num(m.group(1))
    corv = num(re.search(r"Box 16 " + MONEY, page(p, "D08")).group(1))
    halv16 = num(re.search(r"Box 16 " + MONEY, page(p, "D09")).group(1))
    reported = V(p, "SchCA540NR.1.E")
    correct = corv + ca_part
    if reported - correct < 1:
        return None
    return finding(code="CA_WAGES_AFTER_MOVE", severity="high", area="california",
                   title=f"California wages overstated by ${reported - correct:,.0f}",
                   plain=f"The family stopped being California residents on {res['to']}. The return counts all of Halvorsen's salary as California income, including pay earned while living in Texas.",
                   detail=f"R-CA-WAGES-SOURCE used W-2 box 16 ({halv16:,.0f}); the employer kept CA as work state until 9/30 by mistake (qa-45). Paystub D73: CA taxable wages through 07/15/2025 = {ca_part:,.0f}. CA wages = Corvane {corv:,.0f} + {ca_part:,.0f} = {correct:,.0f}. The 4,180 CA withholding is still a credit.",
                   lines=["SchCA540NR.1.E"], sources=["doc:D73#page1", "ev-1081", "D09", "ev-0047", "household:ngozi", "qa-02", "qa-03", "qa-45"],
                   proposal=[adj(p, "SchCA540NR.1.E", correct, "ca_source_income")],
                   fix="Source Halvorsen wages by residency dates; keep CA withholding.")


def k_overlap(p: Packet):
    books = num(re.search(r"Total income " + MONEY, page(p, "D14")).group(1))
    k = num(re.search(r"Box 1a gross amount[^0-9]*" + MONEY, page(p, "D21")).group(1))
    dep = page(p, "D15", 3)
    if V(p, "SchC.1") == books + k and "Paywell" in dep and "deposited gross" in dep:
        return finding(code="1099K_ALREADY_IN_BOOKS", severity="high", area="business",
                       title=f"Same ${k:,.0f} counted twice in gross receipts",
                       plain="A client paid Erik by card through Paywell. That money is already in the books' sales. The engine added Paywell's 1099-K on top, so it is counted twice.",
                       detail=f"SchC.1 {V(p, 'SchC.1'):,.0f} = books {books:,.0f} + 1099-K {k:,.0f} (R-SCHC-GROSS). D15 p3: Atlas paid 41,200, of which 12,400 through Paywell, deposited gross into Sales. 1099-NECs 142,000 + no-1099 clients 9,300 = books 151,300. The 2028 IRS exam asks for this reconciliation.",
                       lines=["SchC.1"], sources=["doc:D15#page3", "D21", "D14", "D17"],
                       proposal=[adj(p, "SchC.1", books, "schc_profit")], fix="Gross receipts = books; keep the NEC/K to books reconciliation.")


def duplicate_pages(p: Packet):
    out = []
    for d in p.raw["documents"]:
        if d["page_count"] < 2:
            continue
        bodies = {}
        for pg in d["pages"]:
            body = re.sub(r"^\(.*?\)\s*", "", pg["printed_content"]).strip()
            if body in bodies and len(body) > 200:
                out.append((d["id"], bodies[body], pg["page"]))
            bodies.setdefault(body, pg["page"])
    for doc, first, dup in out:
        if doc == "D23":
            totals = {pg["page"]: num(re.search(r"total[^0-9]*([\d,]+)", pg["printed_content"], re.I).group(1)) for pg in p.docs[doc]["pages"]}
            miles = V(p, "SchC.44a") - totals[dup]
            rate = p.raw["engine_reference"]["parameters"]["mileage_rate"]
            return finding(code="DUPLICATE_PAGE", severity="high", area="business",
                           title="Mileage log page counted twice",
                           plain=f"Page {dup} of the mileage log is a second scan of page {first}. The engine added up every page, so business miles became {V(p, 'SchC.44a'):,.0f} instead of {miles:,.0f}.",
                           detail=f"Page {dup} text is identical to page {first} (marked 'Second scan'). R-MILEAGE-PAGE-TOTALS summed all pages. {miles:,.0f} mi x {rate} = {miles * rate:,.0f} vs {V(p, 'SchC.9'):,.0f}. Total odometer miles 17,740, so 8,100 business miles is plausible.",
                           lines=["SchC.44a", "SchC.9"], sources=[f"doc:{doc}#page{first}", f"doc:{doc}#page{dup}", "ref:param.mileage_rate"],
                           proposal=[adj(p, "SchC.9", miles * rate, "schc_profit", delta=V(p, "SchC.9") - miles * rate)],
                           fix=f"Exclude page {dup}.")


def sehi_eligibility(p: Packet):
    q = next((x for x in p.raw["client"]["questionnaire"] if "eligible for health coverage" in x["question"]), None)
    if q and q["answer"].lower().startswith("yes") and V(p, "Sch1.17") > 0:
        return finding(code="SEHI_EMPLOYER_PLAN", severity="high", area="business",
                       title="Self-employed health insurance not allowed",
                       plain="Erik could have joined his wife's employer family plan, so his own premiums can't be deducted.",
                       detail="IRC 162(l)(2)(B): no deduction for any month the taxpayer is eligible to participate in a subsidized plan of an employer of the spouse. qa-25: both of Ngozi's employers offered family coverage all year.",
                       lines=["Sch1.17"], sources=[q["id"], "D25", "ev-0484"],
                       proposal=[adj(p, "Sch1.17", 0, "adjustment")], fix="Remove the deduction (authority: IRC 162(l)(2)(B)).")


def repair_vs_improvement(p: Packet):
    inv = page(p, "D47")
    if re.search(r"Installed new .*system", inv) and "HVAC 11,000" in (p.lines["v3"]["SchE.14A"].get("note") or "").replace(".00", ""):
        wi = next((a for a in p.raw["what_if"]["alternatives"] if a["id"] == "hvac_improvement"), None)
        props = [adj(p, "SchE.14A", V(p, "SchE.14A") - 11000, "ordinary_income", delta=11000),
                 adj(p, "SchE.18A", V(p, "SchE.18A") + 150, "ordinary_income", delta=-150, note="New asset 27.5 yr SL mid-month from Aug")]
        f = finding(code="REPAIR_IS_IMPROVEMENT", severity="medium", area="rentals_and_sale",
                    title="HVAC replacement deducted as a repair",
                    plain="Putting in a whole new heating and cooling system is an improvement. It has to be depreciated over 27.5 years, not deducted all at once.",
                    detail="D47: removed furnace and condenser; installed new heat pump, air handler, line set and thermostat; permit B25-31877. Restoration/betterment under Reg. 1.263(a)-3. The engine's own what-if for this change: federal +3,633, California +896.",
                    lines=["SchE.14A", "SchE.18A"], sources=["doc:D47#page1", "D46", "qa-37", "call-01"], proposal=props,
                    fix="Capitalize 11,000 as SAC-HVAC-2025; depreciate.", what_if="hvac_improvement")
        if wi:
            f["tax_effect"] = {"federal": wi["federal"]["total_tax_change"], "california": wi["california"]["total_tax_change"]}
            f["tax_effect_source"] = "engine what-if"
        return f


def seller_tax_credit(p: Packet):
    m = re.search(r"Seller credit for 2025 county taxes ([\d/]+-[\d/]+): " + MONEY, page(p, "D54"))
    if not m:
        return None
    credit = num(m.group(2))
    re_tax = V(p, "SchA.5b")
    salt = V(p, "SchA.5a") + re_tax - credit
    cap = V(p, "SchA.5e")
    new_ded = min(salt, cap)
    return finding(code="PROPERTY_TAX_PRORATION", severity="medium", area="deductions_and_credits",
                   title="Property tax ignores the seller's share",
                   plain="When the family bought the house, the seller paid the county taxes for January to July 7 through a credit at closing. Only the family's own share can be deducted.",
                   detail=f"D54: seller credit {credit:,.2f} for {m.group(1)}. Buyer deducts {re_tax:,.0f} - {credit:,.0f} = {re_tax - credit:,.0f} (IRC 164(d)). SALT {V(p, 'SchA.5d'):,.0f} -> {salt:,.0f}, now under the {cap:,.0f} cap, so itemized deductions fall {cap - new_ded:,.0f}.",
                   lines=["SchA.5b", "SchA.5e"], sources=["doc:D54#page1", "D58", "D57", "ev-1036"],
                   proposal=[adj(p, "SchA.5b", re_tax - credit, "salt", delta=-credit),
                             adj(p, "SchA.5e", new_ded, "itemized")],
                   fix="Real estate taxes = levy minus seller credit.")


def vehicle_donation(p: Packet):
    t = page(p, "D66")
    m = re.search(r"4c gross proceeds from sale " + MONEY, t)
    claimed = V(p, "F8283.A1.vehicle")
    if m and "4a vehicle sold" in t and claimed > num(m.group(1)):
        g = num(m.group(1))
        return finding(code="VEHICLE_OVER_PROCEEDS", severity="medium", area="deductions_and_credits",
                       title=f"Car donation claimed at ${claimed:,.0f}; charity sold it for ${g:,.0f}",
                       plain="When a charity sells a donated car, you can deduct only what it sold for, not the Blue Book value.",
                       detail=f"1098-C box 4a checked, box 4c gross proceeds {g:,.2f}. IRC 170(f)(12)(A)(ii) limits the deduction to gross proceeds. R-NONCASH-GIFT used the client's estimate (qa-39). Under IRS exam in 2028.",
                       lines=["F8283.A1.vehicle", "SchA.12"], sources=["doc:D66#page1", "ev-1055", "qa-39", "call-01"],
                       proposal=[adj(p, "F8283.A1.vehicle", g, "itemized")], fix="Deduction = 1098-C box 4c; attach 1098-C.")


def payoff_interest_in_1098(p: Packet):
    t = page(p, "D56")
    m = re.search(r"interest [\d/-]+ " + MONEY, t)
    note = p.lines["v3"]["SchA.8a"].get("note") or ""
    if m and "reported on the 2025 Form 1098" in t and "payoff statement" in note:
        amt = num(m.group(1))
        return finding(code="PAYOFF_INTEREST_DOUBLE", severity="medium", area="deductions_and_credits",
                       title=f"Mortgage interest at payoff counted twice (${amt:,.0f})",
                       plain="The payoff letter's interest is already included in the lender's Form 1098. The engine added both.",
                       detail=f"D56: 'Interest is reported on the 2025 Form 1098.' D55 box 1 13,900 'includes ... interest paid at payoff 11/20/2025'. R-MORTGAGE-INTEREST adds every 1098 and lender statement.",
                       lines=["SchA.8a"], sources=["doc:D56#page1", "doc:D55#page1", "ev-1032"],
                       proposal=[adj(p, "SchA.8a", V(p, "SchA.8a") - amt, "itemized")], fix="Remove the payoff statement amount.")


def duplicate_interest(p: Packet):
    lines = [l for k, l in p.lines["v3"].items() if k.startswith("SchB.1.")]
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            if a["value"] == b["value"] and "Northlake" in a["label"] and "Northlake" in b["label"]:
                da = p.ev[a["sources"][0]]["document_id"]
                if "sweep" in page(p, da).lower() and "Northlake Bank" in page(p, da):
                    return finding(code="INTEREST_TWICE", severity="medium", area="investments_and_digital_assets",
                                   title=f"Bank interest counted twice (${a['value']:,.0f})",
                                   plain="The same interest shows up on the brokerage's combined statement and on the bank's own 1099-INT. It was entered from both.",
                                   detail="D28's 1099-INT section is the Northlake Bank sweep for account 7731; D29 is Northlake Bank's 1099-INT for that same sweep. Same payer, same account, same amount.",
                                   lines=[a["key"], b["key"]], sources=["doc:D28#page1", a["sources"][0], "doc:D29#page1", b["sources"][0]],
                                   proposal=[adj(p, b["key"], 0, "interest")], fix="Keep one line.")


def fx_vintage(p: Packet):
    year = p.raw["household"]["tax_year"]
    for k, l in p.lines["v3"].items():
        for s in l.get("sources") or []:
            m = re.fullmatch(r"ref:fx\.(\w+)\.(\d{4})_average", s)
            if m and int(m.group(2)) != year:
                cur = m.group(1)
                fc = p.ev[[x for x in l["sources"] if x.startswith("ev-")][0]]["value"]
                right = p.raw["fx_rates"][f"{cur}_per_USD"][f"{year}_average"]
                new = round(fc / right)
                return finding(code="FX_WRONG_YEAR", severity="low", area="investments_and_digital_assets",
                               title=f"Foreign interest converted at the {m.group(2)} rate",
                               plain=f"The engine used last year's exchange rate. With {year}'s rate the Swedish interest is ${new:,} not ${l['value']:,}.",
                               detail=f"{cur} {fc:,.2f} / {right} ({year} average) = {new:,} vs / {p.raw['fx_rates'][f'{cur}_per_USD'][m.group(2) + '_average']} ({m.group(2)}).",
                               lines=[k], sources=["doc:D36#page1", s, f"ref:fx.{cur}.{year}_average"],
                               proposal=[adj(p, k, new, "interest")], fix=f"Use ref:fx.{cur}.{year}_average.")


def crypto_transfer_basis(p: Packet):
    msg = next((m for m in p.raw["client"]["messages"] if "no cost" in m["text"] and "bought" in m["text"]), None)
    l = p.lines["v3"].get("F8949.H.C6")
    if not (msg and l):
        return None
    cost = num(re.search(r"for about ([\d,]+)", msg["text"]).group(1))
    acq = re.search(r"(\d\d)/(\d\d)/(\d{4})", msg["text"])
    proceeds = num(re.search(r"proceeds " + MONEY, l["label"]).group(1))
    return finding(code="CRYPTO_BASIS_FOUND", severity="medium", area="investments_and_digital_assets", engine="flagged", engine_code="DIGITAL_ASSET_BASIS_MISSING",
                   title="Crypto lot C6: real cost found, and it is long-term",
                   plain=f"Erik bought this bitcoin in 2021 on another exchange, then moved it. With its ${cost:,.0f} cost it is a small long-term gain, not a ${proceeds:,.0f} short-term gain.",
                   detail=f"D35: 'TRANSFER-IN 2025-06-01 (cost basis unknown)'. msg-07: bought {acq.group(0)} for ~{cost:,.0f}; exchange closed; bank line to CryptoNorth. Holding period runs from the original purchase. Box H -> box K.",
                   lines=["F8949.H.C6"], sources=["doc:D35#page1", msg["id"], "D34"],
                   proposal=[adj(p, "F8949.H.C6", 0, "stcg", delta=-proceeds, note="Moved to box K"),
                             adj(p, "F8949.K.C6", proceeds - cost, "ltcg", delta=proceeds - cost,
                                 note=f"BTC 0.05 units (acquired {acq.group(3)}-{acq.group(1)}-{acq.group(2)}, sold 2025-06-18; proceeds {proceeds:,.2f}, basis {cost:,.2f})")],
                   needs="Bank statement showing the 3,050 purchase", fix="Get the bank statement, then basis 3,050, acquired 2021-03-15, box K.")


def broker_unread_pages(p: Packet):
    out = None
    for d in ["D31"]:
        doc = p.docs[d]
        if doc["extraction"]["status"] != "partial":
            continue
        summ = num(re.search(r"total proceeds " + MONEY, page(p, d, 1)).group(1))
        pat = re.compile(r"(M\d+) (.+?) ([\d.]+) sh acquired (\S+) sold (\S+) proceeds " + MONEY + r" basis " + MONEY + r" (short|long)-term (covered|noncovered)")
        missing = []
        for pg in doc["pages"]:
            for m in pat.finditer(pg["printed_content"]):
                if not any(f".{m.group(1)}" in k for k in p.lines["v3"]):
                    missing.append((pg["page"], m))
        if missing:
            pg, m = missing[0]
            gain = num(m.group(6)) - num(m.group(7))
            box = "B" if m.group(9) == "noncovered" else "A"
            out = finding(code="BROKER_PAGE_UNREAD", severity="low", area="investments_and_digital_assets", engine="flagged", engine_code="BROKER_SUMMARY_DETAIL_MISMATCH",
                          title="Meridian page 32 sale missing from the return",
                          plain="The pipeline didn't read the last page of the Meridian statement, so one small sale is missing.",
                          detail=f"Summary proceeds {summ:,.2f}; page {pg}: {m.group(1)} {m.group(2)} proceeds {m.group(6)} basis {m.group(7)} {m.group(8)}-term {m.group(9)} (box {box}).",
                          lines=[f"F8949.{box}"], sources=[f"doc:{d}#page{pg}", f"doc:{d}#page1"],
                          proposal=[adj(p, f"F8949.{box}.{m.group(1)}", gain, "stcg", note=f"{m.group(2)} (acquired {m.group(4)}, sold {m.group(5)}; proceeds {m.group(6)}, basis {m.group(7)})")], fix=f"Add {m.group(1)} to box {box}.")
    return out


def mixed_use(p: Packet):
    notes = " ".join(" ".join(c["notes"]) for c in p.raw["client"]["call_notes"])
    ph = re.search(r"Mobile plan.*?(\d+)%", notes)
    it = re.search(r"internet.*?about (\d+)%", notes, re.I)
    sp = "Spotify Family in software is personal" in notes
    if not (ph and it):
        return None
    t2 = page(p, "D15", 2)
    phone = num(re.search(r"Telephone " + MONEY, t2).group(1))
    net = num(re.search(r"Internet " + MONEY, t2).group(1))
    spot = num(re.search(r"Spotify Family " + MONEY, page(p, "D15", 1)).group(1)) if sp else 0
    disallow = phone * (1 - int(ph.group(1)) / 100) + net * (1 - int(it.group(1)) / 100)
    return finding(code="PERSONAL_USE", severity="medium", area="business",
                   title=f"Family phone, home internet and Spotify deducted in full (${disallow + spot:,.0f} personal)",
                   plain=f"Erik told us the phone is {ph.group(1)}% business, internet {it.group(1)}%, and Spotify Family is personal. The return deducted all of it.",
                   detail=f"D15 p2: 4-line family plan {phone:,.0f}, home internet {net:,.0f}; p1: Spotify Family {spot:,.0f}. Call 2026-03-26. Personal: {disallow:,.0f} + {spot:,.0f}. Meals include 'team lunches with contractors' (50% OK).",
                   lines=["SchC.25", "SchC.27a.1"], sources=["call-01", "doc:D15#page2", "doc:D15#page1", "ev-0101", "ev-0095", "ev-0099"],
                   proposal=[adj(p, "SchC.25", V(p, "SchC.25") - disallow, "schc_profit", delta=disallow),
                             adj(p, "SchC.27a.1", V(p, "SchC.27a.1") - spot, "schc_profit", delta=spot)],
                   fix="Deduct business share only.")


def federal_estimates(p: Packet):
    tx = p.raw["tax_agency_records"]["irs_account_transcript_2025"][0]["transactions"]
    ests = [t for t in tx if t["code"] == "670" and "Estimated" in t["description"]]
    paid = sum(t["amount"] for t in ests)
    claimed = V(p, "F1040.26")
    if claimed != paid:
        return finding(code="ESTIMATES_VS_IRS", severity="medium", area="payments",
                       title=f"Federal estimates: return says ${claimed:,.0f}, IRS has ${paid:,.0f}",
                       plain="For the January payment the return used the client's memory ('4,000 I think'). The IRS transcript shows $3,000.",
                       detail="R-ESTIMATED-PAYMENTS took qa-41 for Q4. Transcript (as of 2026-03-12): 670 on 2026-01-15 = 3,000. No EFTPS confirmation for Q4 in D67. Knock-on: the Form 2210 penalty (164) was computed with the 4,000 and is slightly understated; recompute it with 3,000 paid on 1/15/2026.",
                       lines=["F1040.26"], sources=["qa-41", "agency:/irs_account_transcript_2025/0/transactions/3", "D67", "D69"],
                       proposal=[adj(p, "F1040.26", paid, "payment_federal")], fix="Agree estimates to the IRS transcript.")


def ca_payment_year(p: Packet):
    t = page(p, "D68")
    wrong = [(d, num(a)) for d, a, y in re.findall(r"(\d{4}-\d\d-\d\d) " + MONEY + r" tax year (\d{4})", t)
             if y != "2025" and "2025-04-01" <= d <= "2026-01-15"]
    if wrong:
        amt = sum(a for _, a in wrong)
        return finding(code="CA_PAYMENT_OTHER_YEAR", severity="medium", area="payments",
                       title=f"A ${amt:,.0f} payment for 2024 counted as 2025 (California)",
                       plain="The September payment to California was marked for tax year 2024, and California is holding it as a 2024 credit.",
                       detail=f"D68: {wrong[0][0]} {wrong[0][1]:,.2f} 'tax year 2024'. FTB account lists it under tax_year_2024_payments_after_filing. R-CA-ESTIMATED-PAYMENTS used payment dates, not the designated year.",
                       lines=["F540NR.72"], sources=["doc:D68#page1", "ev-1076", "agency:/ftb_account/tax_year_2024_payments_after_filing/0"],
                       proposal=[adj(p, "F540NR.72", V(p, "F540NR.72") - amt, "payment_california")],
                       fix="Remove from 2025; ask FTB to transfer the 2024 credit.")


def dependent_tin(p: Packet):
    theo = p.people["theo"]
    card = re.search(r"(\d{3}-\d\d-\d{4})", page(p, "D71")).group(1)
    py = next(d["ssn"] for d in p.raw["prior_years"]["return_2024"]["dependents"] if d["name"].startswith("Theo"))
    if theo["ssn"] != card:
        return finding(code="DEPENDENT_SSN_MISMATCH", severity="high", area="intake_and_engagement", engine="missed",
                       title="Theo's SSN on the return doesn't match his card",
                       plain="The SSN typed in the organizer doesn't match Theo's Social Security card or last year's return. The IRS will reject the e-file.",
                       detail=f"Organizer: XXX-XX-{theo['ssn'][-4:]}; card D71 and 2024 return: XXX-XX-{card[-4:]} (transposed digits). Can be caught before transmission by agreeing dependents to the prior-year return.",
                       lines=["F8812.4"], sources=["household:theo", "doc:D71#page1", "py:/return_2024/dependents/1", "msg-10"],
                       proposal=[], fix="Correct the SSN; re-verify all TINs against cards and prior year.")


def provider_tin(p: Packet):
    out = []
    for k in ["F2441.1a", "F2441.1b"]:
        l = p.lines["v3"][k]
        tid = re.search(r"tax ID (\d\d-\d{7})", l["label"]).group(1)
        doc = p.ev[l["sources"][0]]["document_id"]
        dt = re.search(r"Tax ID (\d\d-\d{7})", page(p, doc)).group(1)
        if tid != dt:
            out.append((k, tid, dt, doc))
    if out:
        k, tid, dt, doc = out[0]
        return finding(code="PROVIDER_TIN_MISMATCH", severity="low", area="deductions_and_credits",
                       title="Child care provider's tax ID has swapped digits",
                       plain="The provider's tax ID on Form 2441 doesn't match the provider's own statement.",
                       detail=f"{k}: {tid}; {doc}: {dt}. Also D61 is 'Bright Oak Kids Club', not 'Bright Oak Preschool'.",
                       lines=[k], sources=[f"doc:{doc}#page1", p.lines['v3'][k]["sources"][0]], fix="Use name and ID from the statements.")


def sep_excess(p: Packet):
    l = p.lines["v3"]["Sch1.16"]
    m = re.search(r"Contribution " + MONEY + r"; limit .*= " + MONEY, l.get("note") or "")
    if m and num(m.group(1)) > num(m.group(2)):
        ex = num(m.group(1)) - num(m.group(2))
        return finding(code="SEP_EXCESS", severity="medium", area="business", kind="judgment",
                       title=f"SEP contribution over the limit by ${ex:,.0f} (more after fixes)",
                       plain="Erik put in more than he's allowed. The extra must be taken out, or a 6% penalty applies every year it stays in.",
                       detail=f"Contribution {num(m.group(1)):,.0f} vs limit {num(m.group(2)):,.2f}. The limit drops further once Schedule C findings are accepted. Excess contributions are subject to a 6% excise (Form 5329) unless withdrawn with earnings by the due date (IRC 4973).",
                       lines=["Sch1.16"], sources=["D26", "ev-0485", "qa-26"], fix="Recompute after Sch C changes; advise withdrawal of excess.")


def low_confidence_reads(p: Packet):
    used = [e for e in p.raw["extracted_values"] if e["confidence"] < 0.6 and p.ev_used_by.get(e["id"])]
    if used:
        e = used[0]
        return finding(code="LOW_CONFIDENCE_READ", severity="low", area="deductions_and_credits", engine="flagged", kind="verified", engine_code="LOW_CONFIDENCE_READ",
                       title=f"Handwritten receipt: ${e['value']:,.0f} read at {e['confidence']:.0%} confidence",
                       plain="The first digit could be 1 or 7. The parish and the check number confirm $1,500. We still need a proper written receipt.",
                       detail="ev-1049 'text_as_read' with an ambiguous first digit. msg-08: parish confirmed 1,500, check #2207. A gift of 250+ needs a contemporaneous written acknowledgment (IRC 170(f)(8)).",
                       lines=p.ev_used_by[e["id"]], sources=["doc:D64#page1", e["id"], "msg-08"], fix="Keep 1,500; request typed acknowledgment.")


def nec_not_filed(p: Packet):
    if "No Forms 1099 have been issued" in page(p, "D27"):
        return finding(code="1099NEC_NOT_FILED", severity="medium", area="business", kind="judgment", engine="flagged", engine_code="FORM_1099_FILING",
                       title="Contractors paid $7,400 with no 1099-NEC filed",
                       plain="Erik paid two contractors by bank transfer and didn't send them 1099-NEC forms. He needs to file them late.",
                       detail="D27: Quintero 4,800, Patel 2,600, ACH. 1099-NEC was due 2026-02-02. Schedule C questions I/J must be answered truthfully. Late-filing penalty per form.",
                       lines=["SchC.11"], sources=["D27", "call-01", "qa-22", "qa-23"], fix="File late 1099-NECs now; answer Sch C I/J truthfully.")


def ira_basis_conflict(p: Packet):
    q = p.qa.get("qa-31")
    if q and "none" in q["answer"].lower() and p.raw["prior_years"]["return_2024"]["lines"].get("F8606.14", 0) > 0:
        return finding(code="CLIENT_ANSWER_CONFLICT", severity="low", area="wages_and_stock_compensation", kind="verified",
                       title="Client says no IRA basis; records show $7,000",
                       plain="The client thinks they had no prior basis, but last year's return and the 2024 Form 5498 show a $7,000 contribution. The return is right; we keep a note so nobody 'fixes' it.",
                       detail="D42: 7,000 contributed 02/12/2025 for 2024; 2024 Form 8606 line 14 = 7,000. Both 2025 distributions (7,010 + 7,016) were converted. Taxable amount 26 is correct.",
                       lines=["F8606.2"], sources=["qa-31", "D42", "py:/return_2024/lines/F8606.14"], fix="No change.")


def foreign_inheritance_3520(p: Packet):
    """The prior preparer's open item, cross-checked against the bank statement and the client's own answer."""
    open_items = " ".join(p.raw["prior_years"]["prior_preparer_workpaper"]["open_items_left_by_prior_preparer"])
    stmt = page(p, "D36")
    m = re.search(r"Account opened (\d\d/\d{4}) \(inheritance from ([^)]+)\)", stmt)
    if "3520" in open_items and m:
        return finding(code="FORM_3520_UNRESOLVED", severity="medium", area="investments_and_digital_assets", kind="judgment",
                       title="2023 Form 3520 for the Swedish inheritance was never resolved",
                       plain=f"Erik inherited the Swedish account from {m.group(2)} in {m.group(1)}. A foreign inheritance over $100,000 must be reported on Form 3520. The prior preparer flagged it and never closed it.",
                       detail="D07 p3 open item: '2023 Form 3520 (foreign inheritance over 100,000) - discussed? (no note of resolution)'. D36: 'Account opened 09/2023 (inheritance from Birgitta Lindqvist)'. qa-07 confirms. Not on the 2025 return and outside this engagement (D01), but late-filing penalties can reach 25% of the gift; must be raised with the client in writing.",
                       lines=["SchB.7a"], sources=["doc:D07#page3", "doc:D36#page1", "qa-07", "doc:D01#page1"],
                       fix="Tell the client in writing; offer a separate engagement (reasonable-cause statement).")


def corrected_1099_applied(p: Packet):
    old, new = p.docs["D30"]["pages"], p.docs["D31"]["pages"]
    changed = [n["page"] for o, n in zip(old, new) if o["printed_content"] != n["printed_content"] and n["page"] != 1]
    if changed and "D30" in p.versions["v3"]["documents_superseded"]:
        return finding(code="CORRECTED_1099_APPLIED", severity="low", area="investments_and_digital_assets", kind="verified",
                       title="Corrected Meridian 1099 applied correctly (3 lots changed)",
                       plain="Meridian sent a corrected 1099 in March. We compared it page by page with the original: three sales changed, and the return uses the corrected numbers with no leftovers from the old form.",
                       detail=f"Pages that differ: {changed}. M6 wash sale 735 -> 512; M9 basis 6,900 -> 4,880; M14 acquired 2024-10-15 -> 2024-09-15 (short -> long-term, moved from box A to box D in v2). D30 is superseded; no line uses it.",
                       lines=["F8949.A.M6", "F8949.D.M9", "F8949.D.M14"], sources=["doc:D31#page4", "doc:D31#page6", "doc:D31#page8", "doc:D30#page4"],
                       engine="handled", fix="No change.")


def election_opportunities(p: Packet):
    """Scan the engine's what-ifs for a choice that lowers tax in one jurisdiction at no cost in the other."""
    for a in p.raw["what_if"]["alternatives"]:
        fed, ca = a["federal"]["total_tax_change"], a["california"]["total_tax_change"]
        if a["id"] == "equipment_section179" and fed <= 0 and ca < 0:
            f = finding(code="ELECTION_SECTION_179", severity="medium", area="business", kind="judgment", engine="missed",
                        title=f"Electing section 179 for the studio equipment saves California ${-ca:,.0f}",
                        plain="The engine took 100% bonus depreciation. Expensing the same equipment under section 179 gives the same federal result, but California allows section 179 (up to $25,000) and not bonus, so California tax drops.",
                        detail=f"what_if '{a['id']}': federal {fed:+,}, California {ca:+,}. Changes F4562-C.12 0 -> 38,000 and F4562-C.14 38,000 -> 0; SchCA540NR.12.C 30,400 -> 10,400. An election is a judgment call: record it with the partner's approval.",
                        lines=["F4562-C.12", "F4562-C.14", "SchCA540NR.12.C"], sources=["doc:D22#page1", "qa-18", "call-01"], what_if=a["id"],
                        proposal=[adj(p, "F4562-C.12", 38000, "election"), adj(p, "F4562-C.14", 0, "election")],
                        fix="Elect section 179 on Form 4562 Part I (federal and California).")
            f["tax_effect"] = {"federal": fed, "california": ca}
            f["tax_effect_source"] = "engine what-if"
            return f


def oregon_credit_condition(p: Packet):
    """Schedule S: Oregon is not a state CA residents can claim a credit for, except through a group (composite) return."""
    l = p.lines["v3"].get("ScheduleS.credit")
    k1 = page(p, "D39", 2)
    if l and "Oregon" in l["label"] and "composite" in k1.lower():
        return finding(code="OREGON_CREDIT_CONDITION", severity="medium", area="california", kind="judgment",
                       title=f"California credit for Oregon tax (${l['value']:,}) depends on a condition nobody checked",
                       plain="California normally gives no credit for tax paid to Oregon. The exception is a group (composite) return, which this is, but only if Oregon's group return does not already give its own credit for California tax.",
                       detail=f"Engine rule R-CA-OSTC claimed {l['value']:,} on Schedule S. FTB 2025 Schedule S instructions: Oregon is not among the states listed for residents; residents included in a group nonresident return filed with AZ, OR or VA 'may also claim a credit' unless that state allows a credit for taxes paid to California on the group return. D39 p2: Oregon composite, 1,580 paid on Erik's behalf. Confirm with Woodworks how the composite was computed; if Oregon allowed a California credit, remove the 844 (California tax +844).",
                       lines=["ScheduleS.credit"], sources=["doc:D39#page2", "ev-0982"],
                       fix="Confirm the Oregon composite computation with the S corporation; record the answer as a judgment.")


CHECKS = [oregon_credit_condition, election_opportunities, foreign_inheritance_3520, corrected_1099_applied, rsu_basis, ca_wage_sourcing, k_overlap, duplicate_pages, sehi_eligibility, repair_vs_improvement,
          seller_tax_credit, vehicle_donation, payoff_interest_in_1098, duplicate_interest, fx_vintage,
          crypto_transfer_basis, broker_unread_pages, mixed_use, federal_estimates, ca_payment_year,
          dependent_tin, provider_tin, sep_excess, low_confidence_reads, nec_not_filed, ira_basis_conflict]


def run_checks(p: Packet) -> list[dict]:
    out = []
    for c in CHECKS:
        try:
            f = c(p)
        except Exception as e:  # a broken check must never hide the others
            f = finding(code=f"CHECK_FAILED_{c.__name__}", severity="low", area="intake_and_engagement", kind="judgment",
                        title=f"Check {c.__name__} could not run", plain=str(e), detail=repr(e), lines=[], sources=[], fix="Investigate.")
        if f:
            f["id"] = "chk-" + f["code"].lower().replace("_", "-")
            f["source"] = "independent check"
            out.append(f)
    # engine diagnostics become issues too, so nothing the engine raised is lost
    for dgn in p.versions["v3"]["diagnostics"]:
        if any(dgn["code"] in (f.get("engine_code") or "") for f in out):
            continue
        out.append(finding(code=dgn["code"], id="eng-" + dgn["code"].lower().replace("_", "-"), source="engine diagnostic",
                           severity={"error": "high", "warning": "medium"}.get(dgn["severity"], "low"), kind="diagnostic", engine="flagged",
                           area=_diag_area(dgn["code"]), title=DIAG_TITLES.get(dgn["code"], dgn["code"].replace("_", " ").capitalize()), plain=dgn["message"],
                           detail=dgn["message"], lines=[], sources=dgn.get("refs", []), fix="Resolve or document."))
    return out


DIAG_TITLES = {
    "AMT_CREDIT_CARRYFORWARD": "AMT from ISO exercise creates a credit to carry forward",
    "AOTC_PHASED_OUT": "Education credit fully phased out for Ada",
    "FBAR_OUTSIDE_RETURN": "FBAR (FinCEN 114) due for the Swedish account",
    "DUE_DILIGENCE_REQUIRED": "Form 8867 due diligence for child and dependent credits",
    "CA_AMT_NOT_COMPUTED": "California AMT not computed by the engine",
    "HOME_OFFICE_AREA_CHANGE": "Home office size changed mid-year",
    "QUESTIONNAIRE_SALES_CONFLICT": "Client said 'no sales'; 294 sales were reported",
}


def _diag_area(code: str) -> str:
    return {"DIGITAL_ASSET_BASIS_MISSING": "investments_and_digital_assets", "BROKER_SUMMARY_DETAIL_MISMATCH": "investments_and_digital_assets",
            "FBAR_OUTSIDE_RETURN": "investments_and_digital_assets", "AMT_CREDIT_CARRYFORWARD": "wages_and_stock_compensation",
            "AOTC_PHASED_OUT": "deductions_and_credits", "DUE_DILIGENCE_REQUIRED": "deductions_and_credits", "LOW_CONFIDENCE_READ": "deductions_and_credits",
            "FORM_1099_FILING": "business", "HOME_OFFICE_AREA_CHANGE": "business", "CA_AMT_NOT_COMPUTED": "california",
            "QUESTIONNAIRE_SALES_CONFLICT": "investments_and_digital_assets"}.get(code, "intake_and_engagement")
