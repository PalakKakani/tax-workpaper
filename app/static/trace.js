import { html, useState, useEffect, store as S, q, api, act, trace, closeDrawer, money, Money, Ref, Refs, Pill, when, day, whoName, can,
  areaLabel, statusPill, Effect, refLabel, useStore, bus, upload, toast, signed } from "./core.js";

export function Drawer() {
  const s = useStore();
  useEffect(() => {
    const k = (e) => e.key === "Escape" && closeDrawer();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);
  if (!s.drawer.length) return null;
  const ref = s.drawer[s.drawer.length - 1];
  return html`
    <div class="drawer-backdrop" onClick=${closeDrawer}></div>
    <aside class="drawer" role="dialog" aria-label="Trace">
      <div class="drawer-head">
        <div class="crumbs">${s.drawer.map((r, i) => html`${i ? html`<span class="faint">›</span>` : ""}
          <a onClick=${() => { S.drawer = S.drawer.slice(0, i + 1); S.tick++; trace(r); }} class=${i === s.drawer.length - 1 ? "" : "faint"}>${refLabel(r).slice(0, 34)}</a>`)}</div>
        <button class="btn small" onClick=${closeDrawer} aria-label="Close">Close</button>
      </div>
      <div class="drawer-body">${body(ref)}</div>
    </aside>`;
}

function body(ref) {
  const doc = /^(?:doc:)?(D\d\d)(?:#page(\d+))?$/.exec(ref);
  if (doc) return html`<${DocTrace} id=${doc[1]} page=${doc[2] ? +doc[2] : null} key=${ref} />`;
  if (/^ev-\d+$/.test(ref)) return html`<${EvTrace} id=${ref} key=${ref} />`;
  if (/^(chk|eng)-/.test(ref)) return html`<${FindingTrace} id=${ref} key=${ref} />`;
  if (S.meta.lineIndex[ref]) return html`<${LineTrace} k=${ref} key=${ref} />`;
  return html`<${OtherTrace} r=${ref} key=${ref} />`;
}

// ------------------------------------------------------------ a number
function LineTrace({ k }) {
  const [d, setD] = useState(null);
  const load = () => q(`/api/line/${encodeURIComponent(k)}`).then(setD).catch((e) => setD({ error: e.message }));
  useEffect(() => { load(); bus.addEventListener("changed", load); return () => bus.removeEventListener("changed", load); }, [k]);
  if (!d) return html`<p class="muted">Tracing ${k}…</p>`;
  if (d.error) return html`<p>${d.error}</p>`;
  const l = d.line;
  const changed = d.current !== l.value;
  const firstDocSrc = d.sources.find((s) => s.doc);
  return html`<div class="stack">
    <div>
      <div class="faint small">${l.jurisdiction === "california" ? "California" : "Federal"} · ${l.form} line ${l.line} · ${areaLabel(l.area)}</div>
      <h2 style="margin:2px 0 8px">${l.label}</h2>
      <div class="trace-value">
        <span class="big">${typeof d.current === "number" ? money(d.current) : d.current}</span>
        ${changed ? html`<span class="muted">engine said <s>${money(l.value)}</s></span>` : null}
        ${d.verifications.length ? html`<span class="tick" title="Verified">✓ ${d.verifications.length} verified</span>` : null}
        ${d.findings.map((f) => html`<a onClick=${() => trace(f.id)}>${statusPill(f)} ${f.title}</a>`)}
      </div>
    </div>
    <div class="history">
      ${d.history.map((x) => html`<div><div class="lbl">${x.version} · ${day(x.computed_at)}</div><b>${money(x.value)}</b></div>`)}
      <div class=${"now"}><div class="lbl">Working (ours)</div><b>${money(d.current)}</b></div>
      <div><div class="lbl">2024 as filed</div><b>${d.prior_year === null || d.prior_year === undefined ? "–" : money(d.prior_year)}</b></div>
    </div>
    <div class="sheet pad">
      <h3>How it was built</h3>
      <p class="small muted" style="margin-top:4px"><span class="mono">${l.rule || "input"}</span> ${l.rule_text}</p>
      ${l.note ? html`<p class="small">${l.note}</p>` : null}
      <div class="chain">
        <div class="col"><div class="faint small">Built from</div>
          ${d.inputs.length ? d.inputs.map((i) => html`<a onClick=${() => trace(i.key)}><span>${i.label} <span class="faint mono">${i.key}</span></span><span>${money(i.value)}</span></a>`) : html`<div class="small muted" style="padding:4px 8px">Source documents directly (below)</div>`}
        </div>
        <div class="col"><div class="faint small">Feeds into</div>
          ${d.used_by.length ? d.used_by.map((i) => html`<a onClick=${() => trace(i.key)}><span>${i.label} <span class="faint mono">${i.key}</span></span><span>${money(i.value)}</span></a>`) : html`<div class="small muted" style="padding:4px 8px">Nothing downstream</div>`}
        </div>
      </div>
    </div>
    <div class="sheet">
      <div class="section-title"><h3>Where it came from</h3><span class="faint small">${d.sources.length} source${d.sources.length === 1 ? "" : "s"}</span></div>
      ${d.sources.length ? html`<table><tbody>${d.sources.map((s) => html`<tr class="click" onClick=${() => trace(s.kind === "value" ? s.ref : s.ref)}>
        <td>${s.title}<div class="faint small">${s.subtitle}</div></td>
        <td class="num">${s.value !== undefined && s.value !== null ? (typeof s.value === "number" ? money(s.value) : String(s.value).slice(0, 60)) : ""}
          ${s.confidence !== undefined ? html`<div class=${"small " + (s.confidence < 0.6 ? "neg" : "faint")}>read ${Math.round(s.confidence * 100)}%</div>` : null}</td></tr>`)}</tbody></table>`
        : html`<p class="pad small muted">Computed from other lines; trace the inputs above.</p>`}
    </div>
    ${firstDocSrc ? html`<${DocTrace} id=${firstDocSrc.doc} page=${firstDocSrc.page} focusEv=${firstDocSrc.kind === "value" ? firstDocSrc.ref : null} compact=${true} />` : null}
    <${Changes} adjustments=${d.adjustments} />
    <${Trail} target=${k} verifications=${d.verifications} notes=${d.notes} evidence=${d.evidence} />
    <${Actions} target=${k} line=${l} current=${d.current} />
  </div>`;
}

function Changes({ adjustments }) {
  if (!adjustments.length) return null;
  return html`<div class="sheet"><div class="section-title"><h3>Changes to this number</h3><span class="faint small">original kept</span></div>
    <table><thead><tr><th>From → to</th><th>Who and why</th><th class="num">Tax effect</th><th></th></tr></thead><tbody>
    ${adjustments.map((a) => html`<tr style=${a.active ? "" : "opacity:.55"}>
      <td class="mono">${money(a.from)} → ${money(a.to)}${!a.active ? html`<div class="small faint">${a.reverted ? "reverted" : "superseded"}</div>` : ""}</td>
      <td>${whoName(a.by)} · ${when(a.at)}<div class="small muted">${a.reason || ""}</div>
        ${a.finding ? html`<a class="small" onClick=${() => trace(a.finding)}>from finding</a>` : ""} ${a.approved_by ? html`<span class="small tick">approved by ${whoName(a.approved_by)}</span>` : ""}
        ${a.phase === "amendment" ? html`<${Pill} k="amber">amendment<//>` : ""}</td>
      <td class="num small">${signed(a.effect.federal)} fed<br/>${signed(a.effect.california)} CA</td>
      <td>${a.active && can("adjustment.revert") ? html`<button class="btn small" onClick=${() => act("adjustment.revert", { adjustment: a.id, reason: prompt("Why revert?") || "" })}>Revert</button>` : ""}</td>
    </tr>`)}</tbody></table></div>`;
}

function Trail({ target, verifications = [], notes = [], evidence = [] }) {
  const items = [
    ...verifications.map((v) => ({ at: v.at, el: html`<span class="tick">✓</span> <b>${(v.type || "").replaceAll("_", " ")}</b> by ${whoName(v.by)}${v.note ? html` — <span class="muted">${v.note}</span>` : ""}` })),
    ...notes.map((n) => ({ at: n.at, el: html`<b>Note</b> by ${whoName(n.by)}: ${n.text}` })),
    ...evidence.map((e) => ({ at: e.at, el: html`<b>Evidence</b> ${e.file ? html`<a href=${"/api/file/" + e.file.id} target="_blank">${e.file.name}</a>` : e.name || ""} from ${whoName(e.by)}${e.note ? html` — <span class="muted">${e.note}</span>` : ""}` })),
  ].sort((a, b) => (a.at < b.at ? -1 : 1));
  if (!items.length) return null;
  return html`<div class="sheet pad"><h3>Audit trail</h3>${items.map((i) => html`<div class="small" style="margin-top:6px">${i.el} <span class="faint">· ${when(i.at)}</span></div>`)}</div>`;
}

export function Actions({ target, line, current }) {
  const [mode, setMode] = useState(null);
  const [f, setF] = useState({});
  const types = S.state.standards.verification_types;
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const done = () => { setMode(null); setF({}); };
  const btn = (m, l, perm) => (can(perm) ? html`<button class=${"btn small" + (mode === m ? " primary" : "")} onClick=${() => setMode(mode === m ? null : m)}>${l}</button>` : null);
  return html`<div class="sheet pad no-print">
    <div class="row">${btn("verify", "Record verification", "verification.record")} ${btn("note", "Add note", "note.add")} ${btn("attach", "Attach evidence", "evidence.attach")}
      ${line ? btn("adjust", "Adjust this number", "adjustment.manual") : null} ${btn("ask", "Ask a question", "question.ask")}</div>
    ${mode === "verify" ? html`<div style="margin-top:10px"><label class="f">How was it verified?<select class="f" onChange=${set("type")}><option value="">Choose…</option>${types.map((t) => html`<option value=${t}>${t.replaceAll("_", " ")}</option>`)}</select></label>
      <label class="f">What you checked<input type="text" onInput=${set("note")} placeholder="e.g. agreed to W-2 box 1 on D08" /></label>
      <button class="btn primary" disabled=${!f.type} onClick=${() => act("verification.record", { target, type: f.type, note: f.note }).then(done)}>Record verification</button></div>` : null}
    ${mode === "note" ? html`<div style="margin-top:10px"><textarea onInput=${set("text")} placeholder="Note for the file"></textarea>
      <button class="btn primary" style="margin-top:6px" disabled=${!f.text} onClick=${() => act("note.add", { target, text: f.text }).then(done)}>Add note</button></div>` : null}
    ${mode === "attach" ? html`<div style="margin-top:10px"><input type="file" onChange=${(e) => setF({ ...f, file: e.target.files[0] })} />
      <label class="f" style="margin-top:6px">What it shows<input type="text" onInput=${set("note")} /></label>
      <button class="btn primary" disabled=${!f.file} onClick=${async () => { const up = await upload(f.file); await act("evidence.attach", { target, file: up, note: f.note }); done(); }}>Attach</button></div>` : null}
    ${mode === "adjust" ? html`<div style="margin-top:10px" class="grid2">
      <label class="f">New value (now ${money(current)})<input type="number" onInput=${set("to")} /></label>
      <label class="f">Tax category (prices the effect)<select class="f" onChange=${set("category")}><option value="">Choose…</option>${Object.keys(S.meta.rates).map((c) => html`<option value=${c}>${c.replaceAll("_", " ")}</option>`)}</select></label>
      <label class="f" style="grid-column:1/-1">Why (kept with the change)<input type="text" onInput=${set("reason")} /></label>
      ${f.to && f.category ? html`<div class="small muted" style="grid-column:1/-1">Estimated effect: ${signed((f.to - current) * S.meta.rates[f.category].federal_per_dollar)} federal, ${signed((f.to - current) * S.meta.rates[f.category].california_per_dollar)} California (rate × change; the engine is not rerun).</div>` : null}
      <div><button class="btn primary" disabled=${!(f.to && f.category && f.reason)} onClick=${() => act("adjustment.manual", { line: target, to: +f.to, category: f.category, reason: f.reason }).then(done)}>Record adjustment</button></div></div>` : null}
    ${mode === "ask" ? html`<div style="margin-top:10px"><label class="f">To<select class="f" onChange=${set("to")}><option value="">Choose…</option>${S.meta.actors.filter((a) => a.id !== S.viewer).map((a) => html`<option value=${a.id}>${a.name} (${a.role.replaceAll("_", " ")})</option>`)}</select></label>
      <textarea onInput=${set("text")} placeholder="The answer becomes evidence on this item."></textarea>
      <button class="btn primary" style="margin-top:6px" disabled=${!(f.to && f.text)} onClick=${() => act("question.ask", { to: f.to, target, text: f.text }).then(done)}>Send question</button></div>` : null}
  </div>`;
}

// ------------------------------------------------------------ a document
export function DocTrace({ id, page, focusEv, compact }) {
  const [d, setD] = useState(null);
  const [sel, setSel] = useState(focusEv || null);
  const [revealed, setRevealed] = useState(null);
  useEffect(() => { q(`/api/doc/${id}`).then(setD); }, [id, S.state && S.state.seq]);
  useEffect(() => {
    if (!d || compact) return;
    const el = document.querySelector(`[data-ev="${sel}"]`) || document.querySelector(`[data-page="${id}-${page}"]`);
    if (el) el.scrollIntoView({ block: "center" });
  }, [d, sel]);
  if (!d) return html`<p class="muted">Opening ${id}…</p>`;
  const s = d.summary;
  const hl = d.highlights.filter((x) => x.found);
  const selH = d.highlights.find((x) => x.ev === sel);
  const pages = compact && page ? d.pages.filter((p) => p.page === page) : d.pages;
  const reveal = async () => {
    try { const r = await q(`/api/reveal?ref=${id}`); setRevealed(r.value); toast("Unmasked. This view is logged."); }
    catch (e) { toast(e.message, null, true); }
  };
  return html`<div class="stack">
    ${compact ? html`<div class="row" style="justify-content:space-between"><h3>Source: ${id} ${s.title}</h3><a class="small" onClick=${() => trace("doc:" + id)}>Open full document</a></div>` : html`
    <div>
      <div class="faint small">${s.type} · ${s.issuer || ""} · received ${day(s.received_at)} · ${s.pages} page${s.pages > 1 ? "s" : ""}</div>
      <h2 style="margin:2px 0 6px">${id} ${s.title}</h2>
      <div class="row">
        <${Pill} k=${s.status === "used" ? "ok" : s.status === "superseded" ? "amber" : ""}>${s.status === "used" ? `Used on ${s.lines.length} lines` : s.status === "superseded" ? "Superseded" : "Not on the return"}<//>
        ${s.extraction.status !== "extracted" ? html`<${Pill} k="amber">extraction ${s.extraction.status}<//>` : null}
        ${d.superseded_by ? html`<span class="small">Replaced by <${Ref} r=${d.superseded_by} /></span>` : null}
        ${d.supersedes ? html`<span class="small">Corrects <${Ref} r=${d.supersedes} /></span>` : null}
        ${can("sensitive.view") ? html`<button class="btn small" onClick=${reveal}>Show unmasked (logged)</button>` : html`<span class="small faint">SSNs and account numbers masked for your role</span>`}
      </div>
      ${d.not_used_reason ? html`<div class="callout" style="margin-top:8px">Why it isn't on the return: ${d.not_used_reason}</div>` : null}
      ${s.extraction.reason ? html`<div class="callout red" style="margin-top:8px">${s.extraction.reason}</div>` : null}
      ${d.findings.length ? html`<div style="margin-top:8px" class="small">Findings that cite it: ${d.findings.map((f) => html` <a onClick=${() => trace(f.id)}>${f.title}</a>`)}</div>` : null}
      ${s.lines.length ? html`<div class="small" style="margin-top:6px">Landed on: <${Refs} refs=${s.lines.slice(0, 40)} /></div>` : null}
    </div>`}
    ${selH ? html`<div class="field-pop">
      <b>${selH.label}</b> <span class="faint mono">${selH.ev} · field ${selH.field}</span><br/>
      Read as <b>${typeof selH.value === "number" ? money(selH.value, { cents: true }) : String(selH.value)}</b>${" "}at <span class=${selH.confidence < 0.6 ? "neg" : ""}>${Math.round(selH.confidence * 100)}% confidence</span>.
      ${selH.used_by.length ? html` Landed on ${selH.used_by.map((u) => html` <${Ref} r=${u} />`)}` : html` <span class="muted">Not used on any return line.</span>`}
    </div>` : null}
    ${revealed ? html`<div class="docpage">${revealed}</div>` : pages.map((p) => html`<div class="docpage" data-page=${id + "-" + p.page}>
      <span class="pno">${id} · page ${p.page} of ${s.pages}</span>
      ${p.page === 1 || pages.length === 1 ? html`<div class="dochead">Simulated from the packet's printed_content. A scanned original slots in here: highlights use each value's position box.</div>` : null}
      ${isForm(s.type, p.text) && !revealed ? renderForm(p, hl.filter((x) => x.page === p.page), sel, setSel, s.type) : renderPage(p, hl.filter((x) => x.page === p.page), sel, setSel)}</div>`)}
    ${compact ? null : html`<${Trail} target=${id} verifications=${d.verifications} notes=${d.notes} evidence=${d.evidence} /><${Actions} target=${id} />`}
  </div>`;
}

// ------------------------------------------------------------ form layout
// The packet prints forms as run-on text ("Box 1 104,600.00; Box 2 15,800.00; ..."). We split it into
// segments by character offset, so every highlight stays attached to the exact characters it came from.
const FORM_TYPES = /^(W-2|1099|1098|K-1|5498|3921|3922)/;
const W2 = { 1: "Wages, tips, other compensation", 2: "Federal income tax withheld", 3: "Social security wages", 4: "Social security tax withheld",
  5: "Medicare wages and tips", 6: "Medicare tax withheld", 10: "Dependent care benefits", 12: "Codes", 13: "Checkboxes", 14: "Other",
  15: "State", 16: "State wages", 17: "State income tax" };
const isForm = (type, text) => FORM_TYPES.test(type || "") && /\bBox \w+/.test(text);

function segments(text) {
  const out = [];
  const re = /(?<=[.;])\s+(?=[A-Z0-9(])/g;
  const depth = (k) => { let d = 0; for (let j = 0; j < k; j++) d += text[j] === "(" ? 1 : text[j] === ")" ? -1 : 0; return d; };
  let i = 0, m;
  while ((m = re.exec(text))) { if (depth(m.index) > 0) continue; out.push([i, m.index]); i = m.index + m[0].length; }
  out.push([i, text.length]);
  return out.map(([a, b]) => { let e = b; while (e > a && /[;.\s]/.test(text[e - 1]) && !/\d\.\d\d$/.test(text.slice(a, e))) e--; return [a, e]; }).filter(([a, b]) => b > a);
}

function marked(text, a, b, spans, sel, setSel) {
  const out = [];
  let i = a;
  for (const s of spans) {
    if (s.start < i || s.end > b) continue;
    out.push(text.slice(i, s.start));
    const cls = "field" + (s.used_by.length ? " used" : "") + (s.ev === sel ? " focus" : "") + (s.confidence < 0.6 ? " low" : "");
    out.push(html`<mark class=${cls} data-ev=${s.ev} title=${`${s.label} (${s.ev})${s.used_by.length ? " → " + s.used_by.join(", ") : ""}`} onClick=${() => setSel(s.ev)}>${text.slice(s.start, s.end)}</mark>`);
    i = s.end;
  }
  out.push(text.slice(i, b));
  return out;
}

function renderForm(p, spans, sel, setSel, type) {
  spans = [...spans].sort((a, b) => a.start - b.start);
  const t = p.text;
  const segs = segments(t);
  const head = segs[0];
  const title = t.slice(head[0], head[1]);
  const boxes = [], parties = [], notes = [];
  for (const sg of segs.slice(1)) {
    const s = t.slice(sg[0], sg[1]);
    const bm = /^Box (\w+)\s*/.exec(s);
    if (bm) boxes.push({ sg, no: bm[1], skip: bm[0].length, label: type === "W-2" ? W2[parseInt(bm[1])] : null });
    else if (/^(Employer|Employee|Payer|Recipient|Filer|Payee|Corporation|Shareholder|Partnership|Partner|Lender|Borrower|Trustee|Participant|Student|School|Donee|Donor|Transferors?|Issuer|Account)/.test(s)) parties.push(sg);
    else notes.push(sg);
  }
  return html`<div class="form">
    <div class="form-title">${marked(t, head[0], head[1], spans, sel, setSel)}</div>
    ${parties.length ? html`<div class="form-parties">${parties.map(([a, b]) => html`<div class="party">${marked(t, a, b, spans, sel, setSel)}</div>`)}</div>` : null}
    <div class="form-boxes">${boxes.map((x) => { const [a, b] = x.sg; let body = a + x.skip;
      const hasMark = spans.some((s) => s.start >= a && s.end <= b && s.used_by.length);
      // the printed description before the first number moves up into the box label, like a real form
      const dm = x.label ? null : /^([A-Za-z][^0-9]*?)\s+(?=[\d(-])/.exec(t.slice(body, b));
      const desc = dm && !spans.some((s) => s.start < body + dm[1].length && s.end > body) ? dm[1] : null;
      if (desc) body += dm[0].length;
      return html`<div class=${"fbox" + (hasMark ? " has" : "")}><div class="fno">${x.no}${x.label || desc ? html` <span>${x.label || desc}</span>` : null}</div><div class="fval">${marked(t, body, b, spans, sel, setSel)}</div></div>`; })}</div>
    ${notes.length ? html`<div class="form-notes">${notes.map(([a, b]) => html`<div>${marked(t, a, b, spans, sel, setSel)}</div>`)}</div>` : null}
  </div>`;
}

function renderPage(p, spans, sel, setSel) {
  spans = [...spans].sort((a, b) => a.start - b.start);
  const out = [];
  let i = 0;
  for (const s of spans) {
    if (s.start < i) continue;
    out.push(p.text.slice(i, s.start));
    const cls = "field" + (s.used_by.length ? " used" : "") + (s.ev === sel ? " focus" : "") + (s.confidence < 0.6 ? " low" : "");
    out.push(html`<mark class=${cls} data-ev=${s.ev} title=${`${s.label} (${s.ev})${s.used_by.length ? " → " + s.used_by.join(", ") : ""}`} onClick=${() => setSel(s.ev)}>${p.text.slice(s.start, s.end)}</mark>`);
    i = s.end;
  }
  out.push(p.text.slice(i));
  return out;
}

function EvTrace({ id }) {
  const [r, setR] = useState(null);
  useEffect(() => { api(`/api/ref?r=${id}`).then(setR); }, [id]);
  if (!r) return null;
  return html`<${DocTrace} id=${r.doc} page=${r.page} focusEv=${id} />`;
}

// ------------------------------------------------------------ a finding
export function FindingTrace({ id }) {
  const s = useStore();
  const f = s.state.findings.find((x) => x.id === id);
  if (!f) return html`<p>Unknown finding.</p>`;
  const judg = s.state.judgments.filter((j) => j.target === id);
  const ev = s.state.evidence.filter((e) => e.target === id);
  const qs = s.state.questions.filter((x) => x.target === id);
  return html`<div class="stack">
    <div><div class="row">${statusPill(f)} <${Pill} k=${f.severity}>${f.severity}<//> <span class="engine-tag">${engineTag(f)}</span></div>
      <h2 style="margin:6px 0">${f.title}</h2><p>${f.plain}</p></div>
    <div class="sheet pad"><h3>For the reviewer</h3><p class="small" style="margin-top:4px">${f.detail}</p><p class="small"><b>Fix:</b> ${f.fix}</p>
      <div class="small muted">Evidence</div><${Refs} refs=${f.sources} />
      <div class="small muted" style="margin-top:8px">Return lines</div><${Refs} refs=${f.lines.filter((l) => S.meta.lineIndex[l])} /></div>
    ${f.proposal.length ? html`<div class="sheet"><div class="section-title"><h3>Proposed adjustment</h3><${Effect} te=${f.tax_effect} pe=${f.payment_effect} /></div>
      <table><tbody>${f.proposal.map((a) => html`<tr><td><${Ref} r=${a.line} /></td><td class="mono num">${money(a.from)} → ${money(a.to)}</td><td class="small muted">${a.note || a.category.replaceAll("_", " ")}</td></tr>`)}</tbody></table>
      ${f.tax_effect_source ? html`<p class="small muted pad" style="padding-top:6px">Tax effect from the engine's own what-if (${f.what_if}), not the per-dollar rates.</p>` : null}</div>` : null}
    <${FindingActions} f=${f} />
    ${qs.map((x) => html`<div class="callout"><b>${whoName(x.by)} asked ${whoName(x.to)}:</b> ${x.text}${x.answer ? html`<div style="margin-top:4px"><b>${whoName(x.answer.by)}:</b> ${x.answer.text} <span class="faint small">${when(x.answer.at)}</span></div>` : html`<div class="small faint">Waiting for an answer</div>`}</div>`)}
    ${judg.map((j) => html`<div class="callout green"><b>${j.kind}</b> by ${whoName(j.by)} · ${when(j.at)}<div>${j.text}</div><div class="small">Authority: ${j.authority}</div></div>`)}
    ${ev.length ? html`<${Trail} target=${id} evidence=${ev} />` : null}
    ${f.history.length ? html`<div class="sheet pad"><h3>History</h3>${f.history.map((h) => html`<div class="small" style="margin-top:4px">${when(h.at)} · ${whoName(h.by)} ${h.what}${h.reason ? ": " + h.reason : ""}</div>`)}</div>` : null}
    <${Actions} target=${id} />
  </div>`;
}

export const engineTag = (f) => (f.engine === "missed" ? "Engine missed this" : f.engine === "flagged" ? "Engine flagged this" : f.engine === "handled" ? "Engine handled this" : "");

export function FindingActions({ f }) {
  const [reason, setReason] = useState("");
  const [jk, setJk] = useState("judgment");
  const [auth, setAuth] = useState("");
  const open = f.status === "open" || f.status === "verified";
  return html`<div class="sheet pad no-print">
    ${open ? html`<label class="f">Reason (kept with the decision)<input type="text" value=${reason} onInput=${(e) => setReason(e.target.value)} /></label>
      <div class="row">
        ${f.proposal.length && can("finding.accept") ? html`<button class="btn good" onClick=${() => act("finding.accept", { finding: f.id, reason }, { undo: true })}>Accept adjustment</button>` : null}
        ${can("finding.resolve") ? html`<button class="btn" disabled=${!reason} onClick=${() => act("finding.resolve", { finding: f.id, reason, authority: auth })}>Resolve without adjustment</button>` : null}
        ${can("finding.dismiss") ? html`<button class="btn danger" disabled=${!reason} onClick=${() => act("finding.dismiss", { finding: f.id, reason, authority: auth })}>Dismiss</button>` : null}
      </div>
      ${can("judgment.record") ? html`<details style="margin-top:10px"><summary class="small">Record a judgment call, election, due diligence or penalty decision</summary>
        <div class="grid2" style="margin-top:8px"><label class="f">Kind<select class="f" onChange=${(e) => setJk(e.target.value)}>${["judgment", "election", "due diligence", "penalty decision", "advice", "outside filing"].map((k) => html`<option>${k}</option>`)}</select></label>
        <label class="f">Authority relied on (firm rule)<input type="text" onInput=${(e) => setAuth(e.target.value)} placeholder="e.g. IRC 162(l)(2)(B)" /></label></div>
        <button class="btn" disabled=${!(reason && auth)} onClick=${() => act("judgment.record", { target: f.id, kind: jk, text: reason, authority: auth })}>Record ${jk}</button></details>` : null}`
      : html`<div class="row"><span>This is ${f.status}.</span>${can("finding.reopen") ? html`<button class="btn small" onClick=${() => act("finding.reopen", { finding: f.id, reason: prompt("Why reopen?") || "" })}>Reopen</button>` : null}</div>`}
  </div>`;
}

// ------------------------------------------------------------ anything else
function OtherTrace({ r }) {
  const [d, setD] = useState(null);
  useEffect(() => { api(`/api/ref?r=${encodeURIComponent(r)}`).then(setD); }, [r]);
  if (!d) return null;
  if (r === "household:residency") return html`<div class="stack"><h2>Residency</h2>${S.meta.client.residency.map((x) => html`<div class="sheet pad">${x.state} ${x.status}: ${day(x.from)} – ${day(x.to)}</div>`)}</div>`;
  return html`<div class="stack"><div class="faint small">${d.kind} · ${d.subtitle}</div><h2>${d.title}</h2>
    ${d.value !== undefined ? html`<div class="docpage">${typeof d.value === "number" ? money(d.value) : String(d.value)}</div>` : null}
    <${Actions} target=${r} /></div>`;
}
