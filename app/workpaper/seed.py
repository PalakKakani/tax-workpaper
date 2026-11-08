"""A short, realistic history so the demo opens mid-engagement (late June 2026, after v3).

It shows on first load: accepted findings, a client question, a verification, a
review note blocking filing, and a reviewer sign-off that reopened because the
preparer changed the area after it was signed.
"""
from .packet import Packet
from .state import build_state


def seed_demo(p: Packet, store) -> None:
    def ev(actor, type_, payload, at, batch=None, target=None):
        if type_ == "signoff.sign":
            st = build_state(p, store.all())
            payload["hash"] = st["areas"][payload["area"]]["hash"]
        store.append(actor, type_, payload, target=target or payload.get("finding") or payload.get("line") or payload.get("area") or payload.get("target"), batch=batch, at=at)

    ev("st-01", "time.log", {"area": "intake_and_engagement", "hours": 1.0, "note": "Engagement, organizer, IP PIN"}, "2026-06-23T14:05:00Z")
    ev("st-01", "bulk.verify", {"targets": ["F1040.1a", "F1040.25a", "Sch3.11", "F8889.9"], "type": "agreed_to_source_document",
                                "note": "Agreed to W-2s D08/D09; D10 is the same Halvorsen W-2 (photo), counted once."}, "2026-06-23T14:40:00Z", batch="b-seed-1")
    ev("st-01", "verification.record", {"target": "F8606.2", "type": "agreed_to_prior_year", "note": "2024 Form 8606 line 14 = 7,000. Client's 'no basis' answer is wrong."}, "2026-06-23T14:52:00Z")
    ev("st-01", "signoff.sign", {"area": "wages_and_stock_compensation", "level": "preparer"}, "2026-06-23T15:10:00Z")
    ev("st-01", "time.log", {"area": "wages_and_stock_compensation", "hours": 2.5}, "2026-06-23T15:11:00Z")
    ev("st-02", "signoff.sign", {"area": "wages_and_stock_compensation", "level": "reviewer"}, "2026-06-24T16:30:00Z")
    ev("st-01", "finding.accept", {"finding": "chk-duplicate-page", "reason": "Page 3 is a rescan of page 2 (same coffee stain)."}, "2026-06-25T13:20:00Z")
    ev("st-01", "finding.accept", {"finding": "chk-1099k-already-in-books", "reason": "D15 p3: Paywell deposits recorded gross in Sales."}, "2026-06-25T13:34:00Z")
    ev("st-01", "finding.accept", {"finding": "chk-interest-twice", "reason": "Same sweep account 7731."}, "2026-06-25T13:41:00Z")
    ev("st-01", "finding.accept", {"finding": "chk-rsu-basis-zero", "reason": "Basis per Corvane supplemental statement D11."}, "2026-06-25T14:02:00Z")
    ev("st-01", "question.ask", {"to": "cu-02", "target": "chk-crypto-basis-found", "text": "Can you upload the 2021 bank statement that shows the $3,050 payment to CryptoNorth? We need it to use that cost for the bitcoin sold in June."}, "2026-06-30T19:10:00Z")
    ev("st-01", "time.log", {"area": "business", "hours": 2.0}, "2026-06-25T15:00:00Z")
    ev("st-01", "time.log", {"area": "investments_and_digital_assets", "hours": 3.0}, "2026-06-25T16:30:00Z")
    ev("st-04", "time.log", {"area": "investments_and_digital_assets", "hours": 1.5, "note": "Tied 260 Brightpath lots to 8949"}, "2026-06-26T15:00:00Z")
    ev("st-04", "note.add", {"target": "D74", "text": "All 260 Brightpath lots agree to Form 8949 (proceeds, basis, wash sales, term)."}, "2026-06-26T15:05:00Z")
    ev("st-02", "review_note.open", {"area": "business", "target": "chk-sehi-employer-plan", "blocking": True,
                                     "text": "Before we remove the 14,400: confirm Erik was eligible all 12 months (Corvane Jan-May and Halvorsen from June). If there's a gap month, that month is deductible."}, "2026-06-26T17:45:00Z")
    ev("st-02", "time.log", {"area": "business", "hours": 0.5}, "2026-06-26T17:50:00Z")


def seed_filed(p: Packet, store) -> None:
    """Play the rest of the season through, from late June 2026 to the 2028 exam letter.

    Every step goes through the same permission checks as the UI, so this doubles as
    an end-to-end test of the filing gate: if any rule would block a step, seeding fails.
    """
    from .commands import execute

    def do(actor, type_, payload, at, batch=None):
        return execute(p, store, actor, type_, payload, batch=batch, at=at)

    st = build_state(p, store.all())
    rn = next(r["id"] for r in st["review_notes"] if r["status"] != "cleared")
    q = next(q["id"] for q in st["questions"] if not q["answer"])

    do("st-01", "review_note.respond", {"note": rn, "text": "Confirmed with Ngozi: Corvane family coverage through 5/31, Halvorsen from 6/2 (day one). No gap month, so no month qualifies."}, "2026-06-27T14:10:00Z")
    do("st-02", "review_note.clear", {"note": rn}, "2026-06-27T16:00:00Z")
    b1 = "b-0627-business"
    for f, why in [("chk-sehi-employer-plan", "IRC 162(l)(2)(B); eligible all 12 months (see review note)."),
                   ("chk-personal-use", "Business share per Erik on call-01: phone 70%, internet 50%, Spotify personal.")]:
        do("st-01", "finding.accept", {"finding": f, "reason": why}, "2026-06-27T16:20:00Z", batch=b1)
    b2 = "b-0629-deductions"
    for f, why in [("chk-property-tax-proration", "IRC 164(d): seller credit on D54 covers 1/1-7/7."),
                   ("chk-vehicle-over-proceeds", "IRC 170(f)(12): 1098-C box 4c."),
                   ("chk-payoff-interest-double", "D56 says the interest is on the 1098."),
                   ("chk-fx-wrong-year", "Use the 2025 average rate (ref:fx.SEK.2025_average)."),
                   ("chk-estimates-vs-irs", "IRS transcript is the record; no EFTPS confirmation for 4,000."),
                   ("chk-ca-payment-other-year", "FTB holds it as a 2024 credit; client to request transfer.")]:
        do("st-01", "finding.accept", {"finding": f, "reason": why}, "2026-06-29T15:00:00Z", batch=b2)
    do("st-02", "finding.accept", {"finding": "chk-ca-wages-after-move", "reason": "Source Halvorsen wages by residency (paystub D73)."}, "2026-06-29T17:00:00Z")
    do("st-02", "finding.accept", {"finding": "chk-repair-is-improvement", "reason": "Reg. 1.263(a)-3(k): whole-system replacement is a restoration."}, "2026-06-29T17:05:00Z")
    do("cu-02", "question.answer", {"question": q, "text": "Uploaded the bank statement page: 03/15/2021 3,050.00 to CryptoNorth."}, "2026-07-01T02:00:00Z")
    do("cu-02", "evidence.attach", {"target": "chk-crypto-basis-found", "kind": "client upload", "name": "2021-03 bank statement (CryptoNorth line).pdf", "note": "Client upload in reply to the open question."}, "2026-07-01T02:01:00Z")
    do("st-01", "finding.accept", {"finding": "chk-crypto-basis-found", "reason": "Basis 3,050 per bank statement; holding period from 2021-03-15."}, "2026-07-01T14:00:00Z")
    do("st-01", "finding.accept", {"finding": "chk-broker-page-unread", "reason": "Read page 32 of D31 manually."}, "2026-07-01T14:05:00Z")
    do("st-01", "finding.resolve", {"finding": "chk-dependent-ssn-mismatch", "reason": "Organizer typo. Corrected to match the 2024 return (D06); client asked for the card.", "authority": "D06 p1"}, "2026-07-01T14:20:00Z")
    do("st-01", "question.ask", {"to": "cu-01", "target": "chk-dependent-ssn-mismatch", "text": "Please upload a photo of Theo's Social Security card so we can confirm his number before we e-file."}, "2026-07-01T14:21:00Z")
    do("st-01", "finding.resolve", {"finding": "chk-provider-tin-mismatch", "reason": "Name and tax ID taken from D61 and D62."}, "2026-07-01T14:30:00Z")
    for f, kind, text, auth in [
        ("chk-sep-excess", "advice", "Advised Erik in writing to withdraw the excess plus earnings before 10/15/2026; 5329 if not.", "IRC 4973; IRC 408(d)(4)"),
        ("chk-1099nec-not-filed", "penalty decision", "Client to file late 1099-NECs now; Schedule C line J answered 'No' truthfully. Penalty per form accepted by client.", "IRC 6721"),
        ("chk-form-3520-unresolved", "outside filing", "Raised with client in writing; separate engagement offered for a late 2023 Form 3520 with reasonable-cause statement.", "IRC 6039F; IRC 6677"),
        ("chk-election-section-179", "election", "Elect section 179 for the 2025 studio equipment: same federal tax, California saves 1,050.", "IRC 179; R&TC 17255"),
    ]:
        do("st-03" if kind == "election" else "st-01", "judgment.record", {"target": f, "kind": kind, "text": text, "authority": auth}, "2026-07-02T15:00:00Z")
    do("st-03", "finding.accept", {"finding": "chk-election-section-179", "reason": "Partner election (see judgment)."}, "2026-07-02T15:05:00Z")
    for f in ("chk-sep-excess", "chk-1099nec-not-filed", "chk-form-3520-unresolved"):
        do("st-01", "finding.resolve", {"finding": f, "reason": "Judgment recorded."}, "2026-07-02T15:10:00Z")
    for f, kind, text, auth in [
        ("chk-oregon-credit-condition", "judgment", "Woodworks' preparer confirms the Oregon composite allows no credit for California tax, so the Schedule S credit stands.", "FTB 2025 Schedule S instructions (group nonresident returns)"),
        ("eng-due-diligence-required", "due diligence", "Form 8867 completed: Theo lived with us 12 months (school records), age 8; Ada full-time student age 19 (D59, D60).", "IRC 6695(g); Reg. 1.6695-2"),
        ("eng-fbar-outside-return", "outside filing", "Client confirms FBAR filed for 2024; 2025 due 10/15/2026. Reminder sent.", "31 CFR 1010.350"),
        ("eng-ca-amt-not-computed", "judgment", "ISO exercised 7/30/2025 after the move; Schedule P prepared outside the engine.", "R&TC 17502"),
        ("eng-home-office-area-change", "judgment", "Area change is the move (D24): 220 sq ft then 260 sq ft; monthly average 240.", "Rev. Proc. 2013-13"),
        ("eng-questionnaire-sales-conflict", "judgment", "Client misunderstood 'sold' (direct indexing and crypto trades). All 1099-Bs and the 1099-DA are on the return.", "D74, D31, D28, D34"),
        ("eng-aotc-phased-out", "judgment", "MAGI above the phase-out; Ada cannot claim it either as a dependent.", "IRC 25A(d)"),
        ("eng-amt-credit-carryforward", "judgment", "Minimum tax credit 3,871 carried to 2026 (Form 8801).", "IRC 53"),
    ]:
        do("st-01", "judgment.record", {"target": f, "kind": kind, "text": text, "authority": auth}, "2026-07-02T16:00:00Z")
        do("st-01", "finding.resolve", {"finding": f, "reason": "Judgment recorded."}, "2026-07-02T16:01:00Z")
    for area, h in [("deductions_and_credits", 1.5), ("rentals_and_sale", 2.5), ("california", 1.5), ("payments", 0.75), ("pass_throughs_and_basis", 1.5), ("intake_and_engagement", 0.5)]:
        do("st-01", "time.log", {"area": area, "hours": h}, "2026-07-02T17:00:00Z")

    st = build_state(p, store.all())
    for aid in st["areas"]:
        do("st-01", "signoff.sign", {"area": aid, "level": "preparer"}, "2026-07-03T14:00:00Z")
    for aid in st["areas"]:
        do("st-02", "signoff.sign", {"area": aid, "level": "reviewer"}, "2026-07-06T15:00:00Z")
        do("st-02", "time.log", {"area": aid, "hours": 0.25}, "2026-07-06T15:01:00Z")
    st = build_state(p, store.all())
    do("st-03", "adjustment.approve", {"adjustments": st["filing"]["big_unapproved"]}, "2026-07-07T16:00:00Z")
    do("st-03", "signoff.sign", {"area": "return", "level": "partner"}, "2026-07-07T16:30:00Z")
    do("st-03", "time.log", {"area": "intake_and_engagement", "hours": 1.0, "note": "Partner review"}, "2026-07-07T16:31:00Z")
    do("cu-01", "client.approve", {"form": "8879", "text": "Reviewed the summary, looks good."}, "2026-07-10T20:05:00Z")
    q2 = next(x["id"] for x in build_state(p, store.all())["questions"] if x["to"] == "cu-01" and not x["answer"])
    do("cu-01", "question.answer", {"question": q2, "text": "Card attached. I must have typed his number wrong in the organizer."}, "2026-07-13T19:01:00Z")
    do("cu-01", "evidence.attach", {"target": "chk-dependent-ssn-mismatch", "kind": "client upload", "name": "Theo SS card.jpg", "note": "D71"}, "2026-07-13T19:02:00Z")
    do("st-03", "filing.freeze", {"reason": "Transmitted federal and California."}, "2026-07-14T16:00:00Z")
    for tl in ("tl-23", "tl-24", "tl-25", "tl-26"):
        do("st-03", "timeline.replay", {"timeline": tl}, "2026-08-21T15:00:00Z")
    do("st-06", "note.add", {"target": "return", "text": "Quality review (selected 2027-01-04): sign-offs, judgments and authority complete. No exceptions."}, "2027-01-04T15:00:00Z")
    do("st-03", "timeline.replay", {"timeline": "tl-27"}, "2027-01-04T15:01:00Z")
    do("st-03", "timeline.replay", {"timeline": "tl-28"}, "2027-01-15T15:00:00Z")
    do("st-03", "timeline.replay", {"timeline": "tl-29"}, "2028-01-26T15:00:00Z")
