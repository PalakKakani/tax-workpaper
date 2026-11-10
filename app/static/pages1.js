import { html, useState, useEffect, useStore, store as S, q, act, trace, money, Money, Ref, Refs, Pill, Seg, when, day, whoName, can, areaLabel,
  statusPill, Effect, useFetch, signed, describeEvent, toast } from "./core.js";
import { engineTag } from "./trace.js";

const Head = ({ title, sub, children }) => html`<div class="page-head"><div><h1>${title}</h1>${sub ? html`<p>${sub}</p>` : null}</div><div class="row no-print">${children}</div></div>`;
export { Head };

// ------------------------------------------------------------ overview
export function Overview() {
  const s = useStore();
  const st = s.state, m = s.meta;
  const w = st.working;
  const v3 = m.versions[2].summary;
  const py = m.prior_year.summary;
  const openErr = st.findings.filter((f) => f.status === "open" && f.kind === "error");
  const fedDue = w.federal.balance_due, caDue = w.california.balance_due;
  const row = (k, v, base, prior) => html`<span class="k">${k}</span><span class="v">${money(v)}</span><span class=${"d " + (v !== base ? "" : "faint")}>${v !== base ? `engine ${money(base)}` : prior !== undefined ? `2024 ${money(prior)}` : ""}</span>`;
  return html`<div class="stack">
    <${Head} title="Okafor-Lindqvist · 2025 joint return" sub=${`Moved California → Texas on July 15. ${m.documents.length} documents, ${m.counts.values.toLocaleString()} extracted values, 3 engine runs. Numbers below are the engine's v3 plus every adjustment we've accepted, priced at the engine's per-dollar rates.`} />
    <div class="sheet ledger">
      <div><h3>Federal (Form 1040)</h3>
        <div class="bottom-line ${fedDue > 0 ? "neg" : ""}">${fedDue > 0 ? "Owes " : "Refund "}${money(Math.abs(fedDue))}</div>
        <div class="small muted" style="margin-bottom:10px">engine v3 said ${v3.federal.balance_due > 0 ? "owes" : "refund"} ${money(Math.abs(v3.federal.balance_due))}</div>
        <div class="kv">${row("AGI (engine v3)", w.federal.agi, w.federal.agi, py["F1040.11"])}${row("Taxable income (engine v3)", w.federal.taxable_income, w.federal.taxable_income, py["F1040.15"])}
          ${row("Total tax", w.federal.total_tax, v3.federal.total_tax, py["F1040.24"])}${row("Payments", w.federal.payments, v3.federal.payments, py["F1040.33"])}</div></div>
      <div><h3>California (540NR, part-year)</h3>
        <div class="bottom-line ${caDue > 0 ? "neg" : ""}">${caDue > 0 ? "Owes " : "Refund "}${money(Math.abs(caDue))}</div>
        <div class="small muted" style="margin-bottom:10px">engine v3 said ${v3.california.balance_due > 0 ? "owes" : "refund"} ${money(Math.abs(v3.california.balance_due))}</div>
        <div class="kv">${row("California AGI (engine v3)", w.california.ca_agi, w.california.ca_agi)}${row("Total tax", w.california.total_tax, v3.california.total_tax)}${row("Payments", w.california.payments, v3.california.payments)}</div></div>
    </div>
    <div class="grid3">
      <div class="sheet pad"><h3>Ready to file?</h3>
        ${st.filing.frozen ? html`<p class="ok-text">Filed and frozen ${day(st.filing.frozen_at)}${st.filing.amending ? " · amendment in progress" : ""}</p>` : null}
        <ul class="gate" style="padding-left:18px;margin:8px 0 0">${st.filing.blockers.length ? st.filing.blockers.map((b) => html`<li class="block">${b}</li>`) : html`<li class="done">Nothing blocks filing.</li>`}</ul>
        <a class="small" href="#/filing">Open filing</a></div>
      <div class="sheet pad"><h3>What we found</h3>
        <p style="margin-top:6px"><b class="neg">${openErr.length}</b> open errors · <b>${st.findings.filter((f) => f.status === "accepted").length}</b> adjusted · <b>${st.findings.filter((f) => f.status === "resolved").length}</b> resolved</p>
        <p class="small muted">Federal tax ${signed(w.delta.federal_tax)}, California ${signed(w.delta.california_tax)} versus the engine. Payments ${signed(w.delta.federal_payments)} / ${signed(w.delta.california_payments)}.</p>
        <a class="small" href="#/issues">Review findings</a></div>
      <div class="sheet pad"><h3>Changed since you last looked</h3>
        ${st.since_last_seen.length ? html`${st.since_last_seen.slice(-5).reverse().map((e) => html`<div class="small" style="margin-top:4px">${describeEvent(e)} <span class="faint">${day(e.at)}</span></div>`)}
          <button class="btn small" style="margin-top:8px" onClick=${() => act("seen", {}, { toast: "Marked as seen." })}>Mark all as seen</button>` : html`<p class="small muted">Nothing new.</p>`}
        <a class="small" href="#/activity">All activity</a></div>
    </div>
    <div class="sheet"><div class="section-title"><h3>Areas</h3><a class="small" href="#/areas">Sign-off board</a></div>
      <table><thead><tr><th>Area</th><th>Open</th><th>Preparer</th><th>Reviewer</th><th class="num">Hours / budget</th></tr></thead><tbody>
      ${Object.values(st.areas).map((a) => html`<tr class="click" onClick=${() => (location.hash = "#/areas")}><td>${a.label}</td>
        <td>${a.open_findings.length ? html`<${Pill} k="high">${a.open_findings.length} open<//>` : html`<${Pill} k="ok">clear<//>`} ${a.open_review_notes.length ? html`<${Pill} k="blue">${a.open_review_notes.length} review note<//>` : ""}</td>
        <td>${signCell(a.signoffs.preparer)}</td><td>${signCell(a.signoffs.reviewer)}</td><td class="num">${a.hours} / ${a.budget ?? "–"}</td></tr>`)}
      </tbody></table></div>
  </div>`;
}
export const signCell = (s) => (s ? (s.stale ? html`<${Pill} k="amber">reopened<//> <span class="small faint">${whoName(s.by)}</span>` : html`<span class="tick">✓</span> <span class="small">${whoName(s.by)} ${day(s.at)}</span>`) : html`<span class="faint small">not signed</span>`);

// ------------------------------------------------------------ issues
export function Issues() {
  const s = useStore();
  const [filter, setFilter] = useState("errors");
  const [area, setArea] = useState("");
  const [sel, setSel] = useState(new Set());
  const sevRank = { high: 0, medium: 1, low: 2 };
  const F = s.state.findings.filter((f) => !area || f.area === area);
  const groups = {
    errors: F.filter((f) => f.status === "open" && f.kind === "error"),
    decide: F.filter((f) => f.status === "open" && f.kind !== "error"),
    done: F.filter((f) => ["accepted", "resolved", "dismissed"].includes(f.status)),
    verified: F.filter((f) => f.status === "verified"),
  };
  const list = [...groups[filter]].sort((a, b) => sevRank[a.severity] - sevRank[b.severity]);
  const acceptable = [...sel].map((id) => s.state.findings.find((f) => f.id === id)).filter((f) => f && f.status === "open" && f.proposal.length);
  const bulkAccept = async () => {
    const batch = "b-" + Date.now().toString(36);
    for (const f of acceptable) await act("finding.accept", { finding: f.id, reason: "Bulk accept" }, { batch, toast: false });
    setSel(new Set());
    toast(`Accepted ${acceptable.length} adjustments.`, { batch });
  };
  const toggle = (id) => { const n = new Set(sel); n.has(id) ? n.delete(id) : n.add(id); setSel(n); };
  const sections = filter === "errors" || filter === "decide"
    ? [["high", "High impact"], ["medium", "Medium"], ["low", "Low"]].map(([k, l]) => [l, list.filter((f) => f.severity === k)]).filter(([, x]) => x.length)
    : [[null, list]];
  const hint = { errors: "Wrong numbers on the return. Each one blocks filing until it's fixed or resolved with a reason.",
    decide: "Not wrong numbers: calls a CPA has to make and record, like elections, outside filings and engine warnings.",
    done: "Every decision keeps who made it, why, and the original number.", verified: "Things that look wrong but the checks proved right, so nobody 'fixes' them." }[filter];
  return html`<div class="stack">
    <${Head} title="Findings" sub="Each check recomputes from the source documents instead of trusting the engine. Click any card to see the proof." />
    <div class="tabs" role="tablist">${[["errors", "Errors to fix", groups.errors.length], ["decide", "Needs a decision", groups.decide.length], ["done", "Decided", groups.done.length], ["verified", "Checked and right", groups.verified.length]].map(([k, l, n]) =>
      html`<button role="tab" aria-selected=${filter === k} class=${"tab" + (filter === k ? " on" : "")} onClick=${() => { setFilter(k); setSel(new Set()); }}>${l}<span class=${"tabn" + (k === "errors" && n ? " red" : "")}>${n}</span></button>`)}
      <select class="f areasel" onChange=${(e) => setArea(e.target.value)} aria-label="Area"><option value="">All areas</option>${s.meta.areas.map((a) => html`<option value=${a.id}>${a.label}</option>`)}</select></div>
    <p class="hint">${hint}</p>
    ${sel.size ? html`<div class="bulkbar"><b>${sel.size} selected</b>
      ${can("finding.accept") ? html`<button class="btn good" disabled=${!acceptable.length} onClick=${bulkAccept}>Accept ${acceptable.length} fix${acceptable.length === 1 ? "" : "es"}</button>` : null}
      <button class="btn" onClick=${() => setSel(new Set())}>Clear</button><span class="small muted">One batch, one undo.</span></div>` : null}
    ${list.length ? sections.map(([title, items]) => html`
      ${title ? html`<h3 class="grouph">${title} <span>${items.length}</span></h3>` : null}
      <div class="cards">${items.map((f) => html`<div class=${"fcard sev-" + f.severity + (sel.has(f.id) ? " sel" : "")} role="button" tabindex="0" onClick=${() => trace(f.id)} onKeyDown=${(e) => e.key === "Enter" && trace(f.id)}>
        ${f.status === "open" && f.proposal.length && can("finding.accept") ? html`<input type="checkbox" class="fcheck" aria-label="Select" checked=${sel.has(f.id)} onClick=${(e) => e.stopPropagation()} onChange=${() => toggle(f.id)} />` : html`<span class="fcheck"></span>`}
        <div class="fbody">
          <div class="ftitle">${f.title}</div>
          <div class="fplain">${f.plain}</div>
          <div class="fmeta">${areaLabel(f.area)}${engineTag(f) ? html` <span class="dot">·</span> ${engineTag(f)}` : null}${filter === "done" ? html` <span class="dot">·</span> ${statusPill(f)}` : null}</div>
        </div>
        <div class="feff">${fx(f)}</div>
      </div>`)}</div>`) : html`<div class="sheet empty">${filter === "errors" ? "No errors left to fix." : "Nothing here."}</div>`}
  </div>`;
}

function fx(f) {
  const te = f.tax_effect || {}, pe = f.payment_effect || {};
  const row = (label, v) => (v ? html`<div><span>${label}</span><b>${signed(v)}</b></div>` : null);
  const rows = [row("Federal tax", te.federal), row("California tax", te.california), row("Fed. payments", pe.federal), row("CA payments", pe.california)].filter(Boolean);
  return rows.length ? rows : html`<div class="none">${f.kind === "error" ? "Blocks filing" : "No tax change"}</div>`;
}

// ------------------------------------------------------------ the return, line by line
export function Return() {
  const s = useStore();
  const [form, setForm] = useState("F1040");
  const [txt, setTxt] = useState("");
  const [sel, setSel] = useState(new Set());
  const [vtype, setVtype] = useState("agreed_to_source_document");
  const forms = [...new Set(s.meta.lines.map((l) => l.form))];
  const verified = new Set(s.state.verifications.map((v) => v.target));
  const flagged = new Set(s.state.findings.filter((f) => f.status === "open").flatMap((f) => f.lines));
  let lines = s.meta.lines.filter((l) => (txt ? (l.key + " " + l.label).toLowerCase().includes(txt.toLowerCase()) : l.form === form));
  const big = lines.length > 250;
  if (big) lines = lines.slice(0, 250);
  const cur = (l) => (l.key in s.state.current_values ? s.state.current_values[l.key] : l.value);
  const bulk = () => { const batch = "b-" + Date.now().toString(36); act("bulk.verify", { targets: [...sel], type: vtype, note: prompt("What did you check?") || "" }, { batch, undo: { batch } }); setSel(new Set()); };
  return html`<div class="stack">
    <${Head} title="The return, line by line" sub="Click any number to see how it was built and the exact spot on the source document it came from.">
      <input type="text" placeholder="Filter lines (key or label)" value=${txt} onInput=${(e) => setTxt(e.target.value)} style="width:240px" />
    <//>
    <div class="row">${forms.map((f) => html`<button class=${"btn small" + (f === form && !txt ? " primary" : "")} onClick=${() => { setForm(f); setTxt(""); }}>${f}</button>`)}</div>
    ${sel.size && can("bulk.verify") ? html`<div class="sheet pad row"><b>${sel.size} selected</b><select class="f" style="width:auto" onChange=${(e) => setVtype(e.target.value)}>${s.state.standards.verification_types.map((t) => html`<option value=${t}>${t.replaceAll("_", " ")}</option>`)}</select><button class="btn primary" onClick=${bulk}>Verify all</button><button class="btn" onClick=${() => setSel(new Set())}>Clear</button></div>` : null}
    <div class="sheet scroll" style="max-height:none"><table><thead><tr><th></th><th>Line</th><th>Description</th><th class="num">Now</th><th class="num">Engine v3</th><th class="num">2024</th><th class="num">Sources</th></tr></thead><tbody>
      ${lines.map((l) => { const c = cur(l); return html`<tr class="click" onClick=${() => trace(l.key)}>
        <td onClick=${(e) => e.stopPropagation()}><input type="checkbox" aria-label="Select" checked=${sel.has(l.key)} onChange=${() => { const n = new Set(sel); n.has(l.key) ? n.delete(l.key) : n.add(l.key); setSel(n); }} /></td>
        <td class="mono">${l.key}</td><td>${l.label}${flagged.has(l.key) ? html` <${Pill} k="high">finding<//>` : ""}</td>
        <td class="num"><b>${money(c)}</b>${verified.has(l.key) ? html`<span class="tick">✓</span>` : ""}</td><td class="num ${c !== l.value ? "faint" : ""}">${c !== l.value ? html`<s>${money(l.value)}</s>` : money(l.value)}</td>
        <td class="num faint">${l.py === null || l.py === undefined ? "" : money(l.py)}</td><td class="num faint">${l.n_sources || ""}</td></tr>`; })}
    </tbody></table>${big ? html`<p class="pad small muted">Showing 250; filter to narrow.</p>` : null}</div>
  </div>`;
}

// ------------------------------------------------------------ documents
export function Documents() {
  const s = useStore();
  const [f, setF] = useState("all");
  const docs = s.meta.documents.filter((d) => f === "all" || d.status === f || (f === "late" && d.received_at > "2026-03-02"));
  const c = (st) => s.meta.documents.filter((d) => d.status === st).length;
  return html`<div class="stack">
    <${Head} title="Document index" sub="Every document and where it landed on the return, or why it didn't. Late and corrected documents are marked.">
      <${Seg} value=${f} onChange=${setF} options=${[["all", `All ${s.meta.documents.length}`], ["used", `Used ${c("used")}`], ["not_on_return", `Not on return ${c("not_on_return")}`], ["superseded", `Superseded ${c("superseded")}`], ["late", "Arrived late"]]} />
    <//>
    <div class="sheet"><table><thead><tr><th>Doc</th><th>Title</th><th>Belongs to</th><th>Received</th><th>Area</th><th>Status</th></tr></thead><tbody>
      ${docs.map((d) => html`<tr class="click" onClick=${() => trace("doc:" + d.id)}><td class="mono">${d.id}</td><td>${d.title}${d.extraction.status !== "extracted" ? html` <${Pill} k="amber">${d.extraction.status}<//>` : ""}</td>
        <td class="small">${d.belongs_to}</td><td class="small">${day(d.received_at)}${d.received_at > "2026-03-02" ? html` <${Pill} k="amber">late<//>` : ""}</td><td class="small">${areaLabel(d.area)}</td>
        <td>${d.status === "used" ? html`<${Pill} k="ok">${d.lines.length} lines<//>` : d.status === "superseded" ? html`<${Pill} k="amber">superseded<//>` : html`<${Pill}>not on return<//>`}${s.state.notes.some((n) => n.target === d.id) || s.state.verifications.some((v) => v.target === d.id) ? html`<span class="tick">✓</span>` : ""}</td></tr>`)}
    </tbody></table></div></div>`;
}

// ------------------------------------------------------------ reconciliations
export function Recon() {
  const [d] = useFetch("/api/recon");
  if (!d) return html`<p class="muted">Reconciling…</p>`;
  const breaks = d.filter((r) => r.status === "break");
  return html`<div class="stack">
    <${Head} title="Reconciliations" sub="Figures that should agree, computed independently from the documents and agency records and compared with the return as it stands now. A break turns green when the finding that explains it is accepted." />
    <div class=${"callout " + (breaks.length ? "red" : "green")}>${breaks.length ? `${breaks.length} of ${d.length} don't agree yet.` : `All ${d.length} agree.`}</div>
    <div class="sheet"><table><thead><tr><th>Should agree</th><th class="num">Independent figure</th><th class="num">Return now</th><th class="num">Difference</th><th>Status</th></tr></thead><tbody>
    ${d.map((r) => html`<tr><td><b>${r.title}</b><div class="small muted">${r.left.label}</div>${r.note ? html`<div class="small">${r.note}</div>` : null}<${Refs} refs=${[...r.left.refs, ...r.right.refs]} /></td>
      <td class="num"><${Money} v=${r.left.value} /></td><td class="num"><${Money} v=${r.right.value} /><div class="small faint">${r.right.label}</div></td>
      <td class="num ${r.status === "break" ? "neg" : "faint"}">${r.diff ? signed(r.diff) : "0"}</td>
      <td>${html`<${Pill} k=${r.status}>${r.status === "agrees" ? "agrees" : "break"}<//>`}${r.explained_by ? html`<div class="small" style="margin-top:4px"><a onClick=${() => trace(r.explained_by.id)}>${r.explained_by.status === "accepted" ? "fixed by" : "explained by"}: ${r.explained_by.title}</a></div>` : null}</td></tr>`)}
    </tbody></table></div></div>`;
}

// ------------------------------------------------------------ sales detail
export function Sales() {
  const [d] = useFetch("/api/sales");
  const [acct, setAcct] = useState("");
  const [only, setOnly] = useState(true);
  const [n, setN] = useState(100);
  if (!d) return html`<p class="muted">Loading ${"sales"}…</p>`;
  let lots = d.lots.filter((l) => (!acct || l.doc === acct) && (!only || l.flags.some((f) => f !== "wash sale")));
  const total = lots.length;
  lots = lots.slice(0, n);
  const accts = [...new Map(d.groups.map((g) => [g.doc, g.account])).entries()];
  return html`<div class="stack">
    <${Head} title="Sales detail" sub=${`${d.lots.length} sales across four accounts and an S corporation. Review the account totals first; only the lots that need a look are listed below by default.`} />
    <div class="sheet"><table><thead><tr><th>Account</th><th>Form 8949 box</th><th class="num">Sales</th><th class="num">Proceeds</th><th class="num">Basis</th><th class="num">Adjustments</th><th class="num">Gain (loss)</th><th class="num">Need a look</th></tr></thead><tbody>
      ${d.groups.map((g) => html`<tr class="click" onClick=${() => { setAcct(g.doc); setOnly(false); }}><td>${g.account} <span class="faint mono">${g.doc}</span></td><td>${g.box}</td><td class="num">${g.n}</td><td class="num"><${Money} v=${g.proceeds} cents /></td><td class="num"><${Money} v=${g.basis} cents /></td><td class="num"><${Money} v=${g.adj} cents /></td><td class="num"><b><${Money} v=${g.gain} cents /></b></td><td class="num">${g.flagged ? html`<${Pill} k="high">${g.flagged}<//>` : ""}</td></tr>`)}
    </tbody></table></div>
    <div class="row"><select class="f" style="width:auto" value=${acct} onChange=${(e) => setAcct(e.target.value)}><option value="">All accounts</option>${accts.map(([k, v]) => html`<option value=${k}>${v}</option>`)}</select>
      <label class="small"><input type="checkbox" checked=${only} onChange=${() => setOnly(!only)} /> Only lots that need a look (zero or unknown basis, adjusted, added)</label>
      <span class="small muted">${total} lots</span><a class="small" href="#/recon">Summary vs detail tie-outs</a></div>
    <div class="sheet scroll"><table><thead><tr><th>Lot</th><th>Security</th><th>Acquired</th><th>Sold</th><th class="num">Proceeds</th><th class="num">Basis</th><th class="num">Adj.</th><th class="num">Gain</th><th>Flags</th></tr></thead><tbody>
      ${lots.map((l) => html`<tr class="click" onClick=${() => trace(l.key)}><td class="mono">${l.box}.${l.lot}</td><td>${l.desc}</td><td class="small">${l.acquired || ""}</td><td class="small">${l.sold || ""}</td>
        <td class="num"><${Money} v=${l.proceeds} cents /></td><td class="num"><${Money} v=${l.basis} cents /></td><td class="num"><${Money} v=${l.adjustment} cents /></td><td class="num"><b><${Money} v=${l.gain} cents /></b></td>
        <td>${l.flags.map((f) => html`<${Pill} k=${f === "wash sale" ? "" : f === "adjusted" || f === "added by us" ? "ok" : "high"}>${f}<//> `)}<a class="small" onClick=${(e) => { e.stopPropagation(); trace(`doc:${l.doc}#page${l.page}`); }}>source</a></td></tr>`)}
    </tbody></table>${total > n ? html`<div class="pad"><button class="btn" onClick=${() => setN(n + 200)}>Show more (${total - n} left)</button></div>` : null}</div>
  </div>`;
}
