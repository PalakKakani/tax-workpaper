import { html, useState, useEffect, useStore, store as S, q, api, act, trace, money, Money, Ref, Refs, Pill, Seg, when, day, whoName, who, can, areaLabel,
  statusPill, Effect, useFetch, signed, describeEvent, toast, role, refresh } from "./core.js";
import { Head, signCell } from "./pages1.js";

// ------------------------------------------------------------ books to tax
export function Books() {
  const [d] = useFetch("/api/books");
  if (!d) return null;
  return html`<div class="stack">
    <${Head} title="Business books to taxable income" sub="Lindqvist Studio's QuickBooks profit, bridged line by line to Schedule C, then to taxable income. Every reconciling item cites its source." />
    <div class="sheet"><table><tbody>
      ${d.rows.map((r, i) => html`<tr class=${i === 0 ? "" : ""}><td>${r.label}<${Refs} refs=${r.refs} />${r.finding ? html`<div class="small"><a onClick=${() => trace(r.finding.id)}>${statusPill({ ...r.finding, kind: "error" })} ${r.finding.title}</a></div>` : null}</td><td class="num" style="width:160px"><${Money} v=${r.amount} /></td></tr>`)}
      <tr class="total"><td>Schedule C net profit, rebuilt from the books</td><td class="num"><${Money} v=${d.computed} /></td></tr>
      <tr><td>Schedule C line 31 on the return now <span class="faint small">(engine v3: ${money(d.v3_schedule_c)})</span></td><td class="num"><${Money} v=${d.schedule_c} /></td></tr>
      <tr><td><b>${Math.abs(d.diff) < 1 ? "Ties out" : "Difference"}</b></td><td class=${"num " + (Math.abs(d.diff) < 1 ? "tick" : "neg")}>${Math.abs(d.diff) < 1 ? "✓ 0" : signed(d.diff)}</td></tr>
    </tbody></table></div>
    <div class="callout">Accepting the double-counted 1099-K and the personal-use findings moves those rows to zero; the bridge still ties because both sides read the same working numbers.</div>
    <div class="sheet"><div class="section-title"><h3>On to taxable income</h3><span class="small faint">engine v3 values</span></div><table><tbody>
      ${d.taxable_income_chain.map((l) => html`<tr class="click" onClick=${() => trace(l.key)}><td class="mono">${l.key}</td><td>${l.label}</td><td class="num"><${Money} v=${l.value} /></td></tr>`)}</tbody></table></div>
  </div>`;
}

// ------------------------------------------------------------ state split
export function States() {
  const [d] = useFetch("/api/statesplit");
  if (!d) return null;
  const pct = d.ca_resident_days && d.year_days ? Math.round((d.ca_resident_days / d.year_days) * 1000) / 10 : null;
  return html`<div class="stack">
    <${Head} title="Splitting income between states" sub="California taxes everything while they lived there (to July 14) and only California-source income after. Texas has no income tax." />
    <div class="sheet pad"><div class="row" style="gap:0;align-items:stretch">${d.residency.map((r) => { const days = (new Date(r.to) - new Date(r.from)) / 864e5 + 1;
      return html`<div style=${`flex:${days};padding:10px;background:${r.state === "CA" ? "var(--blue-soft)" : "var(--rule-2)"};border-right:2px solid #fff`}><b>${r.state} ${r.status}</b><div class="small">${day(r.from)} – ${day(r.to)} · ${days} days</div></div>`; })}</div>
      ${pct ? html`<p class="small muted" style="margin-top:8px">${d.ca_resident_days} California resident days of ${d.year_days} (${pct}%). The engine prorates interest, dividends, gains and Schedule C by days unless an item is fully California-source.</p>` : null}</div>
    <div class="sheet"><table><thead><tr><th>Schedule CA (540NR)</th><th class="num">Federal (A)</th><th class="num">CA law (D)</th><th class="num">California source (E)</th><th class="num">CA share</th></tr></thead><tbody>
      ${d.rows.map((r) => html`<tr><td>${r.line}. ${r.name}${r.cols.E && r.cols.E.note ? html`<div class="small muted">${r.cols.E.note}</div>` : r.cols.C && r.cols.C.note ? html`<div class="small muted">${r.cols.C.note}</div>` : r.cols.B && r.cols.B.note ? html`<div class="small muted">${r.cols.B.note}</div>` : null}</td>
        ${["A", "D", "E"].map((c) => html`<td class="num">${r.cols[c] ? html`<a onClick=${() => trace(r.cols[c].key)}>${money(r.cols[c].value)}</a>` : "–"}</td>`)}
        <td class="num faint">${r.ca_share !== null ? Math.round(r.ca_share * 100) + "%" : ""}</td></tr>`)}</tbody></table></div>
    <div class="grid2"><div class="sheet pad"><h3>Wages: sourced by where the work was done</h3><p class="small" style="margin-top:6px">Corvane (all in California) plus Halvorsen pay through the July 15 move, from the paystub. Halvorsen's payroll kept California as the work state until September by mistake, so box 16 overstates California wages.</p><${Refs} refs=${["doc:D08#page1", "doc:D09#page1", "doc:D73#page1", "qa-45", "SchCA540NR.1.E", "chk-ca-wages-after-move"]} /></div>
      <div class="sheet pad"><h3>Ridgeline: the fund's own apportionment</h3><p class="small mono" style="margin-top:6px">${d.ridgeline}</p><${Refs} refs=${["doc:D38#page1"]} /></div></div>
  </div>`;
}

// ------------------------------------------------------------ records a CPA expects
export function Records() {
  const [d] = useFetch("/api/records");
  const [tab, setTab] = useState("summary");
  if (!d) return null;
  const L = (rows) => html`<div class="sheet"><table><thead><tr><th>Line</th><th>Description</th><th class="num">2025 now</th><th class="num">2024</th></tr></thead><tbody>${rows.map((l) => html`<tr class="click" onClick=${() => trace(l.key)}><td class="mono">${l.key}</td><td>${l.label}</td><td class="num"><b>${money(l.value)}</b></td><td class="num faint">${l.py === null || l.py === undefined ? "" : money(l.py)}</td></tr>`)}</tbody></table></div>`;
  const tabs = [["summary", "Return summary"], ["tax", "Tax computation"], ["dep", "Depreciation"], ["rent", "Rentals & sale"], ["k1", "K-1s"], ["basis", "Basis by year"], ["ret", "Retirement & foreign"], ["ded", "Deductions & credits"], ["pay", "Payments"], ["carry", "Carryovers"]];
  return html`<div class="stack">
    <${Head} title="Records" sub="The schedules a CPA expects to find, each number clickable back to its source." />
    <div class="row">${tabs.map(([k, l]) => html`<button class=${"btn small" + (tab === k ? " primary" : "")} onClick=${() => setTab(k)}>${l}</button>`)}</div>
    ${tab === "summary" ? L(d.summary) : tab === "tax" ? L(d.tax_computation) : tab === "rent" ? L(d.rentals) : tab === "ret" ? L(d.retirement_foreign) : tab === "ded" ? L(d.deductions_credits) : tab === "pay" ? L(d.payments) : null}
    ${tab === "dep" ? html`<div class="sheet scroll"><table><thead><tr><th>Asset</th><th>In service</th><th>Method / life</th><th class="num">Cost</th><th class="num">Federal 2025</th><th class="num">California 2025</th><th class="num">AMT diff.</th><th class="num">Fed. accumulated</th><th>Disposal / recapture</th></tr></thead><tbody>
      ${d.depreciation.map((a) => html`<tr><td><b>${a.asset_id}</b><div class="small">${a.description}</div></td><td class="small">${a.placed_in_service}</td><td class="small">${a.method}${a.life_years ? " · " + a.life_years + " yr" : ""}${a.federal.bonus ? " · bonus" : ""}</td>
        <td class="num">${money(a.cost)}</td><td class="num">${money(a.federal.depreciation_2025)}</td><td class="num">${money(a.california.depreciation_2025)}</td><td class="num">${money((a.amt || {}).difference_from_regular)}</td><td class="num">${money(a.federal.accumulated_end)}</td>
        <td class="small">${a.disposed ? html`Sold ${typeof a.disposed === "string" ? a.disposed : a.disposed.date || ""}${a.recapture ? html`<br/>4797 gain ${money(a.recapture.gain_4797)}${a.recapture.unrecaptured_1250 ? html`<br/>Unrecaptured §1250 ${money(a.recapture.unrecaptured_1250)}` : ""}` : ""}` : ""}</td></tr>`)}</tbody></table></div>
      <div class="callout">The studio equipment took 100% bonus federally; California doesn't allow bonus. See the section 179 election finding: same federal tax, $1,050 less California tax.</div>` : null}
    ${tab === "k1" ? d.k1.map((k) => html`<div class="sheet"><div class="section-title"><h3>${k.entity}</h3><${Ref} r=${"doc:" + k.doc} /></div><table><thead><tr><th>K-1 item</th><th class="num">Amount</th><th>Lands on</th><th class="num">Return now</th></tr></thead><tbody>
      ${k.rows.map((r) => html`<tr><td><a onClick=${() => trace(r.ev)}>${r.label}</a></td><td class="num">${typeof r.value === "number" && r.value > 1 ? money(r.value) : String(r.value)}</td><td>${r.line && r.line !== "-" ? html`<${Ref} r=${r.line} />` : html`<span class="faint small">memo only</span>`}</td><td class="num">${r.line_value !== null && r.line_value !== undefined ? money(r.line_value) : ""}</td></tr>`)}</tbody></table></div>`) : null}
    ${tab === "basis" ? html`<div class="sheet"><div class="section-title"><h3>Woodworks S corporation stock basis (Form 7203)</h3><span class="small faint">the 2023 gap is closed by D40</span></div><table><thead><tr><th>Year</th><th class="num">Start</th><th class="num">Income</th><th class="num">Distributions</th><th class="num">End</th><th>Source</th></tr></thead><tbody>
      ${d.scorp_rollforward.map((r) => html`<tr><td>${r.year}</td><td class="num">${money(r.start)}</td><td class="num">${money(r.income)}</td><td class="num">${money(r.distributions)}</td><td class="num"><b>${money(r.end)}</b>${r.excess ? html`<div class="small neg">${money(r.excess)} over basis → capital gain</div>` : ""}</td><td class="small">${r.source}</td></tr>`)}</tbody></table></div>
      <div class="sheet pad"><h3>Other basis records</h3>${Object.entries(d.basis).filter(([k]) => k !== "scorp_lindqvist_family_woodworks").map(([k, v]) => html`<div style="margin-top:8px"><b class="small">${k.replaceAll("_", " ")}</b>${v.map((r) => html`<div class="small mono">${JSON.stringify(r)}</div>`)}</div>`)}</div>` : null}
    ${tab === "carry" ? html`<div class="grid2"><div class="sheet pad"><h3>Into 2025 (from 2024)</h3>${Object.entries(d.carryovers.in).filter(([, v]) => typeof v !== "object").map(([k, v]) => html`<div class="row" style="justify-content:space-between"><span>${k.replaceAll("_", " ")}</span><b>${money(v)}</b></div>`)}</div>
      <div class="sheet pad"><h3>Out of 2025 (engine v3)</h3>${Object.entries(d.carryovers.out.federal).map(([k, v]) => html`<div class="row" style="justify-content:space-between"><span>${k.replaceAll("_", " ")}</span><b>${money(v)}</b></div>`)}
        <h3 style="margin-top:10px">California basis differences</h3>${Object.entries(d.carryovers.out.california.depreciation_basis_differences || {}).map(([k, v]) => html`<div class="row" style="justify-content:space-between"><span>${k}</span><b>${money(v)}</b></div>`)}</div></div>` : null}
  </div>`;
}

// ------------------------------------------------------------ prior year
export function Variance() {
  const [d] = useFetch("/api/variance");
  const [all, setAll] = useState(false);
  if (!d) return null;
  const rows = d.rows.filter((r) => all || r.flag);
  return html`<div class="stack">
    <${Head} title="Against last year" sub=${`Swings over ${d.standard.flag_if_change_over_percent}% and $${d.standard.and_over_amount.toLocaleString()} (the firm standard) are flagged. Last year was prepared by another firm, so their choices are listed next to ours.`}>
      <${Seg} value=${all ? "all" : "flag"} onChange=${(v) => setAll(v === "all")} options=${[["flag", "Flagged swings"], ["all", "All lines"]]} /><//>
    <div class="sheet"><div class="section-title"><h3>What the prior preparer did, and what we changed</h3><${Ref} r="doc:D07#page1" /></div><table><tbody>
      ${d.prior_preparer_vs_us.map((r) => html`<tr><td style="width:150px"><b>${r.topic}</b></td><td class="small muted" style="width:32%">${r.prior}</td><td class="small">${r.us}<${Refs} refs=${r.refs} /></td></tr>`)}</tbody></table></div>
    <div class="sheet scroll"><table><thead><tr><th>Line</th><th>Description</th><th class="num">2024</th><th class="num">2025 now</th><th class="num">Change</th><th class="num">%</th></tr></thead><tbody>
      ${rows.map((r) => html`<tr class="click" onClick=${() => S.meta.lineIndex[r.key] && trace(r.key)}><td class="mono">${r.key}</td><td>${r.label}${r.note ? html` <span class="small faint">${r.note}</span>` : ""}</td><td class="num">${money(r.py)}</td><td class="num">${money(r.cy)}</td>
        <td class="num ${r.flag ? "neg" : ""}">${r.change === null ? "" : signed(r.change)}</td><td class="num faint">${r.pct === null || r.pct === undefined ? "" : Math.round(r.pct) + "%"}</td></tr>`)}</tbody></table></div>
  </div>`;
}

// ------------------------------------------------------------ areas and sign-off
export function Areas() {
  const s = useStore();
  const st = s.state;
  const lvl = { preparer: "preparer", reviewer: "reviewer", partner: "partner" }[role()];
  return html`<div class="stack">
    <${Head} title="Areas and sign-off" sub="A sign-off is a promise about exactly what was in the area when you signed. If anything in it changes later, the sign-off reopens on its own. You can't review an area you prepared." />
    <div class="grid3">${Object.values(st.areas).map((a) => { const over = a.budget && a.hours > a.budget;
      return html`<div class="sheet pad area-card"><div class="row" style="justify-content:space-between"><h3>${a.label}</h3><span class="small faint">${a.lines} lines</span></div>
        <div class="small muted">Preparer ${whoName(a.assignment.preparer)} · reviewer ${whoName(a.assignment.reviewer)}${a.assignment.due ? " · due " + a.assignment.due : ""}</div>
        <div class="signs"><span class="small">Preparer</span> ${signCell(a.signoffs.preparer)}</div><div class="signs"><span class="small">Reviewer</span> ${signCell(a.signoffs.reviewer)}</div>
        <div class="small">${a.open_findings.length ? html`<a href="#/issues" class="neg">${a.open_findings.length} open findings</a>` : "No open findings"} · ${a.open_review_notes.length ? html`<a href="#/people">${a.open_review_notes.length} review notes</a>` : "no review notes"}</div>
        <div class="small" style="margin-top:6px">${a.hours} of ${a.budget ?? "–"} budgeted hours</div><div class=${"meter" + (over ? " over" : "")}><div style=${`width:${Math.min(100, a.budget ? (a.hours / a.budget) * 100 : 0)}%`}></div></div>
        <div class="row" style="margin-top:10px">${lvl && can("signoff.sign") && lvl !== "partner" ? html`<button class="btn small primary" onClick=${() => act("signoff.sign", { area: a.id, level: lvl })}>Sign as ${lvl}</button>` : null}
          ${can("time.log") ? html`<button class="btn small" onClick=${() => { const h = parseFloat(prompt("Hours on " + a.label + "?")); if (h) act("time.log", { area: a.id, hours: h }); }}>Log time</button>` : null}
          ${can("review_note.open") ? html`<button class="btn small" onClick=${() => { const t = prompt("Review note (blocks filing until cleared):"); if (t) act("review_note.open", { area: a.id, text: t, blocking: true }); }}>Add review note</button>` : null}
          ${can("assignment.set") ? html`<button class="btn small" onClick=${() => { const d = prompt("Due date (YYYY-MM-DD)?"); if (d) act("assignment.set", { area: a.id, role: "preparer", staff: a.assignment.preparer, due: d }); }}>Set deadline</button>` : null}</div>
      </div>`; })}</div>
    <div class="sheet pad"><h3>Whole return: partner sign-off</h3><div class="signs" style="margin-top:6px">${signCell(st.return_signoff.signoffs.partner)}</div>
      ${role() === "partner" ? html`<button class="btn primary" onClick=${() => act("signoff.sign", { area: "return", level: "partner" })}>Sign the return as partner</button>` : html`<p class="small muted">Only a partner signs the whole return, after every area has fresh preparer and reviewer sign-offs.</p>`}</div>
  </div>`;
}

// ------------------------------------------------------------ people: questions, review notes, judgments
export function People() {
  const s = useStore();
  const st = s.state;
  const [reply, setReply] = useState({});
  return html`<div class="stack">
    <${Head} title="Questions, review notes and judgments" sub="Questions to the client or a colleague are attached to the item they're about, and the answer becomes evidence there. Open review notes block filing." />
    <div class="sheet"><div class="section-title"><h3>Review notes</h3></div>
      ${st.review_notes.length ? st.review_notes.map((r) => html`<div class="pad" style="border-bottom:1px solid var(--rule-2)"><div class="row"><${Pill} k=${r.status === "cleared" ? "ok" : "blue"}>${r.status}<//>${r.blocking ? html`<${Pill} k="high">blocks filing<//>` : ""}<span class="small faint">${areaLabel(r.area)} · ${whoName(r.by)} · ${when(r.at)}</span>${r.target ? html`<${Ref} r=${r.target} />` : ""}</div>
        <p style="margin-top:6px;color:var(--blue)">${r.text}</p>${r.thread.map((t) => html`<div class="small" style="margin-left:14px">↳ <b>${whoName(t.by)}</b>: ${t.text} <span class="faint">${when(t.at)}</span></div>`)}
        ${r.status !== "cleared" ? html`<div class="row" style="margin-top:8px">${can("review_note.respond") ? html`<input type="text" placeholder="Respond" style="max-width:420px" onInput=${(e) => setReply({ ...reply, [r.id]: e.target.value })} /><button class="btn small" onClick=${() => act("review_note.respond", { note: r.id, text: reply[r.id] })}>Respond</button>` : null}
          ${can("review_note.clear") ? html`<button class="btn small good" onClick=${() => act("review_note.clear", { note: r.id })}>Clear</button>` : null}</div>` : html`<div class="small ok-text">Cleared by ${whoName(r.cleared.by)} ${when(r.cleared.at)}</div>`}</div>`) : html`<div class="empty">No review notes.</div>`}</div>
    <div class="sheet"><div class="section-title"><h3>Questions</h3></div>
      ${st.questions.length ? st.questions.map((x) => html`<div class="pad" style="border-bottom:1px solid var(--rule-2)"><div class="small faint">${whoName(x.by)} → ${whoName(x.to)} · ${when(x.at)} ${x.target ? html`<${Ref} r=${x.target} />` : ""}</div><p style="margin-top:4px">${x.text}</p>
        ${x.answer ? html`<div class="callout green"><b>${whoName(x.answer.by)}:</b> ${x.answer.text}</div>` : x.to === S.viewer ? html`<div class="row"><input type="text" placeholder="Your answer" style="max-width:480px" onInput=${(e) => setReply({ ...reply, [x.id]: e.target.value })} /><button class="btn small primary" onClick=${() => act("question.answer", { question: x.id, text: reply[x.id] })}>Send answer</button></div>` : html`<span class="small faint">Waiting for ${whoName(x.to)}</span>`}</div>`) : html`<div class="empty">No questions yet. Ask one from any number, document or finding.</div>`}</div>
    <div class="sheet"><div class="section-title"><h3>Judgment calls, elections, due diligence and penalty decisions</h3><span class="small faint">each records the authority relied on</span></div>
      ${st.judgments.length ? html`<table><tbody>${st.judgments.map((j) => html`<tr><td style="width:130px"><${Pill} k="amber">${j.kind}<//></td><td>${j.text}<div class="small muted">Authority: ${j.authority} · ${whoName(j.by)} ${day(j.at)}</div></td><td>${j.target ? html`<${Ref} r=${j.target} />` : ""}</td></tr>`)}</tbody></table>` : html`<div class="empty">None recorded yet. Record them from a finding.</div>`}</div>
    <div class="sheet"><div class="section-title"><h3>From the client</h3><span class="small faint">questionnaire, messages, call notes</span></div><table><tbody>
      ${S.meta.messages.map((m) => html`<tr><td class="small" style="width:110px">${day(m.sent_at)}</td><td><b>${m.from}</b>: ${m.text}</td><td><${Ref} r=${m.id} /></td></tr>`)}
      ${S.meta.calls.map((c) => html`<tr><td class="small">${day(c.date)}</td><td><b>Call</b>: ${c.notes.join(" ")}</td><td><${Ref} r=${c.id} /></td></tr>`)}</tbody></table></div>
  </div>`;
}

// ------------------------------------------------------------ filing and after
export function Filing() {
  const s = useStore();
  const st = s.state, m = s.meta, f = st.filing;
  const [notice] = useFetch("/api/notice/N-2025-L566");
  const [rf] = useFetch("/api/rollforward");
  const replayed = new Set(st.replayed.map((r) => r.id));
  const ext = m.extension;
  const steps = [
    ["Extension filed with 36,000 (from engine v2)", true],
    ["Every area signed by preparer and reviewer", !st.filing.blockers.some((b) => b.includes("areas missing"))],
    ["Partner approved adjustments over $1,000", !st.filing.blockers.some((b) => b.includes("partner approval"))],
    ["Partner signed the return", !st.filing.blockers.includes("partner sign-off")],
    ["Client approved and signed Form 8879", !!f.client_approved && !st.filing.blockers.some((b) => b.includes("client"))],
    ["Frozen at filing", f.frozen],
  ];
  return html`<div class="stack">
    <${Head} title="Filing and after" sub="Filing freezes the return exactly as transmitted. Any later change is an amendment on top, with the filed version kept." />
    <div class="grid2">
      <div class="sheet pad"><h3>Filing gate</h3><ul class="gate" style="list-style:none;padding:0;margin:8px 0">${steps.map(([t, ok]) => html`<li class=${ok ? "done" : "block"}>${ok ? "✓" : "○"} ${t}</li>`)}</ul>
        ${f.blockers.length ? html`<div class="small muted">Blocking: ${f.blockers.join("; ")}</div>` : null}
        <div class="row" style="margin-top:10px">
          ${can("filing.freeze") && !f.frozen ? html`<button class="btn primary" disabled=${f.blockers.length > 0} onClick=${() => act("filing.freeze", { reason: "Transmitted" })}>Freeze and file</button>` : null}
          ${can("filing.amend") && f.frozen && !f.amending ? html`<button class="btn" onClick=${() => { const r = prompt("Why amend?"); if (r) act("filing.amend", { reason: r }); }}>Start amendment</button>` : null}
          ${f.frozen ? html`<button class="btn" onClick=${() => window.open("#/clientcopy", "_self")}>Client's copy</button>` : null}</div>
        ${f.frozen ? html`<p class="small" style="margin-top:8px">Frozen ${when(f.frozen_at)} · snapshot <span class="mono">${f.snapshot}</span>${f.amending ? html` · <${Pill} k="amber">amendment ${f.amendments} in progress<//>` : ""}</p>` : null}
        ${f.client_approved ? html`<p class="small">Client approved ${when(f.client_approved.at)} (${whoName(f.client_approved.by)}).</p>` : null}</div>
      <div class="sheet pad"><h3>Extension and payments</h3><p class="small" style="margin-top:6px">Form 4868 on 2026-04-14 with ${money(ext.federal.paid_with_form_4868)} (estimated from engine v2: tax ${money(ext.federal.estimated_total_tax)}); FTB 3519 with ${money(ext.california.paid_with_ftb_3519)} (refund expected). An extension to file isn't an extension to pay: anything still owed after April 15 accrues interest at ${Math.round(m.post_filing_rates.irs_underpayment_interest_rate_annual * 1000) / 10}% and a ${Math.round(m.post_filing_rates.irs_failure_to_pay_penalty_per_month * 1000) / 10}%/month penalty.</p>
        <p class="small">Working federal ${st.working.federal.balance_due > 0 ? "balance due " + money(st.working.federal.balance_due) : "refund " + money(-st.working.federal.balance_due)}: ${st.working.federal.balance_due > 0 ? "late-payment interest applies." : "the extension payment covered the tax, so no late-payment interest."}</p></div>
    </div>
    <div class="sheet pad"><h3>The season, replayable</h3><p class="small muted">Scripted events from the packet. A partner replays them to see how the workpaper handles each.</p>
      <div class="timeline" style="margin-top:10px">${m.timeline.filter((t) => t.at > "2026-06-23").map((t) => html`<div class=${"ev " + (replayed.has(t.id) ? (t.event.includes("rejected") ? "bad" : "done") : "")}>
        <b>${t.event.replaceAll("_", " ")}</b> <span class="small faint">${day(t.at)}</span>${t.detail ? html`<div class="small muted">${t.detail}</div>` : ""}
        ${t.event === "efile_rejected" ? html`<div class="small">${m.agency.efile[0].errors[0].message} ${st.findings.find((x) => x.id === "chk-dependent-ssn-mismatch").status !== "open" ? html`<span class="ok-text">Caught before transmission by the dependent-SSN check.</span>` : html`<a onClick=${() => trace("chk-dependent-ssn-mismatch")}>Our check flags this now.</a>`}</div>` : ""}
        ${can("timeline.replay") && !replayed.has(t.id) ? html` <button class="btn small" onClick=${() => act("timeline.replay", { timeline: t.id })}>Replay</button>` : ""}</div>`)}</div></div>
    ${notice ? html`<div class="sheet"><div class="section-title"><h3>IRS ${notice.notice.type} for ${notice.notice.tax_year} · response due ${notice.notice.response_due}</h3><button class="btn small no-print" onClick=${() => (location.hash = "#/notice")}>Open response packet</button></div>
      <div class="pad small">${notice.items.map((it) => html`<div style="margin-bottom:8px"><b>${it.item}</b><div class="muted">${it.answer}</div></div>`)}</div></div>` : null}
    ${rf ? html`<div class="sheet pad"><h3>Carry forward and plan 2026</h3>
      <div class="grid2" style="margin-top:8px"><div><div class="small muted">Federal safe harbor: 110% of 2025 tax = ${money(rf.federal_safe_harbor.total)}</div>${rf.federal_safe_harbor.installments.map((i) => html`<div class="row small" style="justify-content:space-between"><span>${i.due}</span><b>${money(i.amount)}</b></div>`)}</div>
        <div><div class="small muted">California safe harbor: ${money(rf.california_safe_harbor.total)} (30/40/30)</div>${rf.california_safe_harbor.installments.map((i) => html`<div class="row small" style="justify-content:space-between"><span>${i.due}</span><b>${money(i.amount)}</b></div>`)}</div></div>
      <table style="margin-top:10px"><tbody>${rf.carry_forward.map((c) => html`<tr><td>${c.what}</td><td class="small">${c.value}</td><td><${Refs} refs=${c.refs} /></td></tr>`)}</tbody></table>
      <ul class="small" style="margin:8px 0 0">${rf.planning.known_2026_changes_for_this_household.map((x) => html`<li>${x}</li>`)}</ul></div>` : null}
  </div>`;
}

export function Notice() {
  const [d] = useFetch("/api/notice/N-2025-L566");
  if (!d) return null;
  return html`<div class="stack">
    <${Head} title=${`Response to IRS ${d.notice.type}, tax year ${d.notice.tax_year}`} sub=${`Dated ${d.notice.dated}; response due ${d.notice.response_due}. Self-contained: the filed numbers, how each was built, and the evidence. Print it or save as PDF.`}><button class="btn" onClick=${() => window.print()}>Print / save PDF</button><//>
    <div class="sheet pad small">Return frozen ${d.filing.frozen ? when(d.filing.frozen_at) : "(not yet filed)"} · snapshot <span class="mono">${d.filing.snapshot || "–"}</span> · partner sign-off ${d.signoffs.partner ? whoName(d.signoffs.partner.by) + " " + day(d.signoffs.partner.at) : "–"}</div>
    ${d.items.map((it, i) => html`<div class="sheet pad"><h2>Item ${i + 1}. ${it.item}</h2><p style="margin-top:8px">${it.answer}</p>
      <table><thead><tr><th>Line</th><th>Description</th><th class="num">As filed</th><th class="num">Engine before review</th></tr></thead><tbody>${it.line_values.map((l) => html`<tr><td class="mono">${l.key}</td><td>${l.label}</td><td class="num"><b>${money(l.filed)}</b></td><td class="num faint">${money(l.v3)}</td></tr>`)}</tbody></table>
      ${it.recon ? html`<p class="small" style="margin-top:8px"><b>Reconciliation:</b> ${it.recon.left.label} = ${money(it.recon.left.value)}; ${it.recon.right.label} = ${money(it.recon.right.value)}.</p>` : null}
      <div class="small" style="margin-top:8px"><b>Review decisions:</b> ${it.findings.map((f) => html`${f.title} (${f.status}). `)}</div>
      <div class="small" style="margin-top:6px"><b>Evidence:</b></div>${it.evidence.map((e) => html`<div class="small">· ${e.title} <span class="faint">${e.subtitle}</span>${e.value !== undefined ? html` <span class="mono">${String(e.value).slice(0, 140)}</span>` : ""}</div>`)}</div>`)}
  </div>`;
}

export function ClientCopy() {
  const s = useStore();
  const f = s.state.filing;
  const vals = f.frozen_values || {};
  const keys = ["F1040.1z", "F1040.2b", "F1040.3b", "F1040.4b", "F1040.7", "F1040.8", "F1040.11", "F1040.12", "F1040.13", "F1040.15", "F1040.24", "F1040.33"];
  const sum = f.frozen_summary || s.state.working;
  return html`<div class="stack"><${Head} title="Your 2025 return: client copy" sub=${f.frozen ? `As filed ${day(f.frozen_at)}. Keep this with your records for at least seven years.` : "Not filed yet: this is the version waiting for your approval."}><button class="btn" onClick=${() => window.print()}>Print / save PDF</button><//>
    <div class="sheet ledger"><div><h3>Federal</h3><div class="bottom-line">${sum.federal.balance_due > 0 ? "You owe " : "Your refund "}${money(Math.abs(sum.federal.balance_due))}</div><div class="kv" style="margin-top:8px"><span class="k">Total tax</span><span class="v">${money(sum.federal.total_tax)}</span><span></span><span class="k">Payments</span><span class="v">${money(sum.federal.payments)}</span><span></span></div></div>
      <div><h3>California</h3><div class="bottom-line">${sum.california.balance_due > 0 ? "You owe " : "Your refund "}${money(Math.abs(sum.california.balance_due))}</div><div class="kv" style="margin-top:8px"><span class="k">Total tax</span><span class="v">${money(sum.california.total_tax)}</span><span></span><span class="k">Payments</span><span class="v">${money(sum.california.payments)}</span><span></span></div></div></div>
    <div class="sheet"><table><tbody>${keys.map((k) => html`<tr><td>${S.meta.lineIndex[k].label}</td><td class="num">${money(k in vals ? vals[k] : k in s.state.current_values ? s.state.current_values[k] : S.meta.lineIndex[k].value)}</td></tr>`)}</tbody></table></div>
    <p class="small muted">Lines shown as computed by the engine; tax, payments and refund include every correction made in review.</p></div>`;
}

// ------------------------------------------------------------ firm
export function Firm() {
  const s = useStore();
  const st = s.state;
  const [audit] = useFetch("/api/audit");
  const [rules, setRules] = useState(null);
  const staff = s.meta.actors.filter((a) => a.role !== "client");
  const hours = staff.map((p) => ({ p, h: st.time_log.filter((t) => t.by === p.id).reduce((a, t) => a + +t.hours, 0) }));
  const budget = Object.values(s.meta.budget).reduce((a, b) => a + b, 0);
  const used = st.time_log.reduce((a, t) => a + +t.hours, 0);
  return html`<div class="stack">
    <${Head} title="Firm" sub="Standards, people and access, time against budget, and the tamper-evident record of everything that happened." />
    <div class="grid2">
      <div class="sheet pad"><h3>Firm standards</h3>
        ${rules === null ? html`<ul class="small" style="padding-left:18px">${st.standards.rules.map((r) => html`<li>${r}</li>`)}</ul>${can("standards.update") ? html`<button class="btn small" onClick=${() => setRules(st.standards.rules.join("\n"))}>Edit standards</button>` : html`<p class="small faint">The firm administrator edits these.</p>`}`
          : html`<textarea style="min-height:180px" value=${rules} onInput=${(e) => setRules(e.target.value)}></textarea><div class="row" style="margin-top:6px"><button class="btn primary small" onClick=${() => act("standards.update", { rules: rules.split("\n").filter(Boolean) }).then(() => setRules(null))}>Save standards</button><button class="btn small" onClick=${() => setRules(null)}>Cancel</button></div>`}
        <p class="small muted">Variance review: flag changes over ${st.standards.variance_review.flag_if_change_over_percent}% and $${st.standards.variance_review.and_over_amount.toLocaleString()}.</p></div>
      <div class="sheet pad"><h3>Time against budget</h3><p class="small" style="margin-top:4px">${used.toFixed(2)} of ${budget} hours</p><div class=${"meter" + (used > budget ? " over" : "")}><div style=${`width:${Math.min(100, (used / budget) * 100)}%`}></div></div>
        ${hours.filter((x) => x.h).map((x) => html`<div class="row small" style="justify-content:space-between;margin-top:4px"><span>${x.p.name}</span><b>${x.h.toFixed(2)} h</b></div>`)}</div>
    </div>
    <div class="sheet"><div class="section-title"><h3>People and access</h3></div><table><thead><tr><th>Name</th><th>Role</th><th>Sensitive data</th><th>Note</th></tr></thead><tbody>
      ${staff.map((p) => html`<tr><td>${p.name}${p.credential ? ", " + p.credential : ""}</td><td>${p.role.replaceAll("_", " ")}</td><td>${p.clearance ? html`<${Pill} k="ok">full<//>` : html`<${Pill} k="amber">masked only<//>`}</td><td class="small muted">${p.note || ""}</td></tr>`)}</tbody></table></div>
    <div class="sheet"><div class="section-title"><h3>Sensitive data view log</h3><span class="small faint">every unmasked view is recorded</span></div>
      ${st.sensitive_views.length ? html`<table><tbody>${st.sensitive_views.map((v) => html`<tr><td>${whoName(v.by)}</td><td class="mono">${v.ref}</td><td class="small">${when(v.at)}</td></tr>`)}</tbody></table>` : html`<div class="empty">No unmasked views yet.</div>`}</div>
    ${audit ? html`<div class="sheet"><div class="section-title"><h3>Event log</h3><span class=${"small " + (audit.chain.ok ? "ok-text" : "neg")}>${audit.chain.ok ? `✓ hash chain intact (${audit.chain.events} events)` : "Chain broken at " + audit.chain.broken_at}</span></div>
      <div class="scroll"><table><tbody>${[...audit.events].reverse().map((e) => html`<tr><td class="mono small">${e.seq}</td><td class="small">${when(e.at)}</td><td>${describeEvent(e)}</td><td class="mono small faint">${e.hash.slice(0, 10)}</td></tr>`)}</tbody></table></div></div>` : null}
  </div>`;
}

// ------------------------------------------------------------ activity and compare
export function Activity() {
  const s = useStore();
  const [audit] = useFetch("/api/audit");
  const [a, setA] = useState(null);
  const [cmp, setCmp] = useState(null);
  useEffect(() => { if (a !== null) q(`/api/compare?a=${a}`).then(setCmp); }, [a, s.state.seq]);
  return html`<div class="stack">
    <${Head} title="Activity and versions" sub="What changed since you last looked, the engine's three runs, and any two moments of the workpaper side by side." />
    <div class="sheet"><div class="section-title"><h3>Since you last looked</h3>${s.state.since_last_seen.length ? html`<button class="btn small" onClick=${() => act("seen", {}, { toast: "Marked as seen." })}>Mark as seen</button>` : null}</div>
      ${s.state.since_last_seen.length ? html`<table><tbody>${[...s.state.since_last_seen].reverse().map((e) => html`<tr><td>${describeEvent(e)}</td><td class="small faint">${when(e.at)}</td></tr>`)}</tbody></table>` : html`<div class="empty">You're up to date.</div>`}</div>
    <div class="sheet"><div class="section-title"><h3>Engine runs</h3></div><table><tbody>${s.meta.versions.map((v) => html`<tr><td><b>${v.version}</b> ${day(v.computed_at)}</td><td class="small">${v.trigger}</td><td class="num">${v.changes} line changes</td><td class="num">tax ${money(v.summary.federal.total_tax)} / CA ${money(v.summary.california.total_tax)}</td></tr>`)}</tbody></table></div>
    <div class="sheet pad"><h3>Compare the workpaper now with an earlier moment</h3>
      <div class="row" style="margin-top:6px"><label class="small">After event #</label><select class="f" style="width:auto" onChange=${(e) => setA(+e.target.value)}><option value="">Choose…</option>${audit ? audit.events.map((e) => html`<option value=${e.seq}>${e.seq} · ${day(e.at)} · ${describeEvent(e).slice(0, 60)}</option>`) : null}</select></div>
      ${cmp ? html`<div class="grid2" style="margin-top:10px"><div><b>Federal tax</b> ${money(cmp.working.a.federal.total_tax)} → ${money(cmp.working.b.federal.total_tax)}<br/><b>California tax</b> ${money(cmp.working.a.california.total_tax)} → ${money(cmp.working.b.california.total_tax)}</div><div class="small">${cmp.events.length} events in between</div></div>
        <table style="margin-top:8px"><tbody>${cmp.lines.map((l) => html`<tr class="click" onClick=${() => trace(l.key)}><td class="mono">${l.key}</td><td>${l.label}</td><td class="num">${money(l.a)} → <b>${money(l.b)}</b></td></tr>`)}
        ${cmp.findings.map((f) => html`<tr><td></td><td>${f.title}</td><td class="num small">${f.a} → <b>${f.b}</b></td></tr>`)}</tbody></table>` : null}</div>
  </div>`;
}

// ------------------------------------------------------------ what-if
export function WhatIf() {
  const s = useStore();
  const [line, setLine] = useState("");
  const [to, setTo] = useState("");
  const [cat, setCat] = useState("ordinary_income");
  const l = s.meta.lineIndex[line];
  const cur = l ? (line in s.state.current_values ? s.state.current_values[line] : l.value) : null;
  const r = s.meta.rates[cat];
  const d = l && to !== "" ? +to - cur : 0;
  return html`<div class="stack">
    <${Head} title="What-ifs" sub="Try a change without touching the return. The engine's own alternatives are exact; a custom change is priced with its per-dollar rates." />
    <div class="sheet"><table><thead><tr><th>Engine alternative</th><th class="num">Federal tax</th><th class="num">California tax</th><th>Lines it changes</th></tr></thead><tbody>
      ${s.meta.what_if.map((w) => html`<tr><td>${w.description}</td><td class=${"num " + (w.federal > 0 ? "neg" : "")}>${signed(w.federal)}</td><td class=${"num " + (w.california > 0 ? "neg" : "")}>${signed(w.california)}</td><td class="small">${w.changed_lines.slice(0, 6).map((c) => html`<${Ref} r=${c.key} /> `)}${w.changed_lines.length > 6 ? `+${w.changed_lines.length - 6}` : ""}</td></tr>`)}</tbody></table></div>
    <div class="sheet pad"><h3>Custom</h3><div class="grid3" style="margin-top:8px">
      <label class="f">Line<input type="text" list="lines" value=${line} onInput=${(e) => setLine(e.target.value)} placeholder="e.g. SchC.1" /></label>
      <datalist id="lines">${s.meta.lines.map((x) => html`<option value=${x.key}>${x.label}</option>`)}</datalist>
      <label class="f">New value ${l ? `(now ${money(cur)})` : ""}<input type="number" value=${to} onInput=${(e) => setTo(e.target.value)} /></label>
      <label class="f">Category<select class="f" value=${cat} onChange=${(e) => setCat(e.target.value)}>${Object.keys(s.meta.rates).map((c) => html`<option value=${c}>${c.replaceAll("_", " ")}</option>`)}</select></label></div>
      ${l && to !== "" ? html`<p><b>${signed(d * r.federal_per_dollar)}</b> federal, <b>${signed(d * r.california_per_dollar)}</b> California. <span class="small muted">Change of ${signed(d)} × ${r.federal_per_dollar} / ${r.california_per_dollar}. Large changes can cross thresholds the rates don't capture.</span></p>` : html`<p class="small muted">Pick a line and a value.</p>`}</div>
  </div>`;
}

// ------------------------------------------------------------ client portal
export function ClientHome() {
  const s = useStore();
  const st = s.state;
  const mine = st.questions.filter((x) => x.to === S.viewer);
  const [ans, setAns] = useState({});
  const ready = st.filing.ready_for_client;
  return html`<div class="stack">
    <${Head} title=${`Hi ${who(S.viewer).name.split(" ")[0]}`} sub="Your 2025 return with Miraflores. Answer our questions here; when the return is ready you'll approve it and sign Form 8879 here too." />
    <div class="sheet pad"><h3>Questions for you</h3>${mine.length ? mine.map((x) => html`<div style="margin-top:10px"><p>${x.text}</p>${x.answer ? html`<div class="callout green">You answered: ${x.answer.text}</div>` : html`<textarea onInput=${(e) => setAns({ ...ans, [x.id]: e.target.value })}></textarea><div class="row" style="margin-top:6px"><button class="btn primary" onClick=${() => act("question.answer", { question: x.id, text: ans[x.id] })}>Send answer</button>
      <label class="btn">Upload a document<input type="file" hidden onChange=${async (e) => { const { upload } = await import("./core.js"); const up = await upload(e.target.files[0]); act("evidence.attach", { target: x.target || x.id, file: up, note: "Client upload" }); }} /></label></div>`}</div>`) : html`<p class="small muted">No questions right now.</p>`}</div>
    <div class="sheet pad"><h3>Approve your return</h3>
      ${st.filing.client_approved && !st.filing.blockers.some((b) => b.includes("client")) ? html`<p class="ok-text">✓ You approved and signed on ${day(st.filing.client_approved.at)}.</p>`
        : ready ? html`<p>Federal: ${st.working.federal.balance_due > 0 ? "you owe " + money(st.working.federal.balance_due) : "refund " + money(-st.working.federal.balance_due)}. California: ${st.working.california.balance_due > 0 ? "you owe " + money(st.working.california.balance_due) : "refund " + money(-st.working.california.balance_due)}.</p>
          <button class="btn good" onClick=${() => act("client.approve", { form: "8879" })}>Approve and sign Form 8879</button>${st.filing.blockers.some((b) => b.includes("different version")) ? html`<p class="small neg">The return changed after you approved it. Please review and approve again.</p>` : ""}`
        : html`<p class="small muted">We're still reviewing. You'll get a notice here when it's ready.</p>`}</div>
    ${st.filing.frozen ? html`<div class="sheet pad"><a href="#/clientcopy">Download your copy of the filed return</a></div>` : null}
  </div>`;
}
