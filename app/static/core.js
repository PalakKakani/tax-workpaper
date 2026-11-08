import { h } from "preact";
import { useState, useEffect, useRef } from "preact/hooks";
import htm from "htm";
export const html = htm.bind(h);
export { useState, useEffect, useRef };

// ------------------------------------------------------------ store
const S = { meta: null, state: null, viewer: null, drawer: [], toasts: [], route: "", tick: 0 };
const subs = new Set();
export const store = S;
export function emit() { S.tick++; subs.forEach((f) => f(S.tick)); }
export function useStore() {
  const [, set] = useState(0);
  useEffect(() => { subs.add(set); return () => subs.delete(set); }, []);
  return S;
}

// ------------------------------------------------------------ api
export async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}
export const q = (path) => api(path + (path.includes("?") ? "&" : "?") + "viewer=" + encodeURIComponent(S.viewer));

export async function act(type, payload = {}, opts = {}) {
  try {
    const st = await api("/api/events", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor: S.viewer, type, payload, batch: opts.batch || null }),
    });
    S.state = st;
    emit();
    if (opts.toast !== false) toast(opts.toast || label(type) + ".", opts.undo);
    bus.dispatchEvent(new Event("changed"));
    return st;
  } catch (e) {
    toast(e.message, null, true);
    throw e;
  }
}
export const bus = new EventTarget();

export async function refresh() {
  const st = await q("/api/state");
  const prevSeq = S.state ? S.state.seq : null;
  S.state = st;
  emit();
  if (prevSeq !== null && st.seq !== prevSeq) bus.dispatchEvent(new Event("changed"));
  return { prevSeq, st };
}

// ------------------------------------------------------------ toasts
let tid = 0;
export function toast(text, undo, err) {
  const id = ++tid;
  S.toasts = [...S.toasts, { id, text, undo, err }];
  emit();
  setTimeout(() => { S.toasts = S.toasts.filter((t) => t.id !== id); emit(); }, undo ? 9000 : 4200);
}

// ------------------------------------------------------------ drawer (trace stack)
export function trace(ref) {
  if (!ref) return;
  S.drawer = [...S.drawer.filter((r) => r !== ref), ref].slice(-8);
  emit();
}
export function closeDrawer() { S.drawer = []; emit(); }

// ------------------------------------------------------------ formatting
export function money(v, opts = {}) {
  if (v === null || v === undefined || v === "") return "–";
  if (typeof v !== "number") return String(v);
  const cents = opts.cents || (Math.abs(v % 1) > 0.001 && Math.abs(v) < 1e6);
  const s = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: cents ? 2 : 0, maximumFractionDigits: cents ? 2 : 0 });
  return v < 0 ? `(${s})` : s;
}
export function signed(v) {
  if (!v) return "0";
  const s = Math.abs(Math.round(v)).toLocaleString("en-US");
  return (v > 0 ? "+" : "−") + s;
}
export const when = (iso) => (iso ? new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) : "");
export const day = (iso) => (iso ? new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "");
export const who = (id) => (S.meta && S.meta.actors.find((a) => a.id === id)) || { name: id || "Engine", role: "" };
export const whoName = (id) => who(id).name;
export const me = () => who(S.viewer);
export const role = () => me().role;
export const can = (type) => (S.meta.permissions[role()] || []).includes(type);
export const areaLabel = (id) => (S.meta.areas.find((a) => a.id === id) || { label: id === "return" ? "Whole return" : id }).label;
export const lineOf = (key) => S.meta.lineIndex[key];

const LABELS = {
  "finding.accept": "Adjustment accepted", "finding.resolve": "Marked resolved", "finding.dismiss": "Dismissed", "finding.reopen": "Reopened",
  "adjustment.manual": "Adjustment recorded", "adjustment.revert": "Adjustment reverted", "adjustment.approve": "Approved",
  "batch.undo": "Undone", "note.add": "Note added", "evidence.attach": "Evidence attached", "verification.record": "Verification recorded",
  "bulk.verify": "Verifications recorded", "question.ask": "Question sent", "question.answer": "Answer sent", "review_note.open": "Review note opened",
  "review_note.respond": "Response posted", "review_note.clear": "Review note cleared", "signoff.sign": "Signed off", "time.log": "Time logged",
  "judgment.record": "Judgment recorded", "seen": "Marked as seen", "filing.freeze": "Return frozen at filing", "filing.amend": "Amendment started",
  "client.approve": "Return approved and Form 8879 signed", "timeline.replay": "Event replayed", "standards.update": "Standards updated",
  "assignment.set": "Assignment updated", "sensitive.view": "Sensitive value viewed",
};
export const label = (t) => LABELS[t] || t;

export function describeEvent(e) {
  const p = e.payload || {};
  const by = whoName(e.actor);
  const t = e.type;
  const f = p.finding && S.state ? (S.state.findings.find((x) => x.id === p.finding) || {}).title : null;
  switch (t) {
    case "finding.accept": return `${by} accepted “${f || p.finding}”`;
    case "finding.resolve": return `${by} resolved “${f || p.finding}”`;
    case "finding.dismiss": return `${by} dismissed “${f || p.finding}”`;
    case "finding.reopen": return `${by} reopened “${f || p.finding}”`;
    case "signoff.sign": return `${by} signed ${areaLabel(p.area)} as ${p.level}`;
    case "review_note.open": return `${by} opened a review note on ${areaLabel(p.area)}`;
    case "review_note.clear": return `${by} cleared a review note`;
    case "review_note.respond": return `${by} responded to a review note`;
    case "question.ask": return `${by} asked ${whoName(p.to)} a question`;
    case "question.answer": return `${by} answered a question`;
    case "bulk.verify": return `${by} verified ${p.targets.length} items (${(p.type || "").replaceAll("_", " ")})`;
    case "verification.record": return `${by} verified ${p.target}`;
    case "adjustment.manual": return `${by} changed ${p.line} to ${money(p.to)}`;
    case "batch.undo": return `${by} undid a batch`;
    case "time.log": return `${by} logged ${p.hours}h on ${areaLabel(p.area)}`;
    case "note.add": return `${by} added a note on ${p.target}`;
    case "judgment.record": return `${by} recorded a ${p.kind}: ${p.text.slice(0, 80)}`;
    case "timeline.replay": return `Replayed: ${(S.meta.timeline.find((x) => x.id === p.timeline) || {}).event || p.timeline}`.replaceAll("_", " ");
    case "client.approve": return `${by} approved the return and signed Form 8879`;
    case "filing.freeze": return `${by} froze the return at filing`;
    case "filing.amend": return `${by} started an amendment`;
    case "sensitive.view": return `${by} viewed ${p.ref}`;
    default: return `${by}: ${label(t)}`;
  }
}

// ------------------------------------------------------------ small components
export function Money({ v, cents, className = "" }) {
  return html`<span class=${"num " + className + (typeof v === "number" && v < 0 ? " neg" : "")}>${money(v, { cents })}</span>`;
}

export function refKind(r) {
  if (/^(doc:)?D\d\d/.test(r)) return "doc";
  if (/^(qa|msg|call)-/.test(r)) return "client";
  if (/^(chk|eng)-/.test(r)) return "finding";
  if (/^ev-/.test(r)) return "doc";
  if (S.meta && S.meta.lineIndex[r]) return "line";
  return "other";
}
export function refLabel(r) {
  const m = /^doc:(D\d\d)(?:#page(\d+))?$/.exec(r);
  if (m) { const d = S.meta.docIndex[m[1]]; return `${m[1]}${m[2] ? " p" + m[2] : ""} ${d ? shortTitle(d.title) : ""}`; }
  if (/^D\d\d$/.test(r)) { const d = S.meta.docIndex[r]; return `${r} ${d ? shortTitle(d.title) : ""}`; }
  if (S.meta.lineIndex[r]) return r;
  if (/^(chk|eng)-/.test(r)) { const f = S.state.findings.find((x) => x.id === r); return f ? f.title.slice(0, 48) : r; }
  return r;
}
export const shortTitle = (t) => t.replace(/^2025 /, "").replace(/ \(.*\)$/, "").slice(0, 46);

export function Ref({ r }) {
  const k = refKind(r);
  return html`<span class=${"ref " + k} role="link" tabindex="0" onClick=${(e) => { e.stopPropagation(); trace(r); }}
    onKeyDown=${(e) => e.key === "Enter" && trace(r)} title=${r}>${refLabel(r)}</span>`;
}
export function Refs({ refs }) {
  if (!refs || !refs.length) return null;
  return html`<div class="refs">${refs.map((r) => html`<${Ref} r=${r} />`)}</div>`;
}
export function Pill({ k, children }) { return html`<span class=${"pill " + (k || "")}>${children}</span>`; }

export function Seg({ value, options, onChange }) {
  return html`<div class="seg" role="tablist">${options.map(([v, l]) => html`<button role="tab" aria-selected=${v === value} class=${v === value ? "on" : ""} onClick=${() => onChange(v)}>${l}</button>`)}</div>`;
}

export function useFetch(path, deps = []) {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let live = true;
    const load = () => q(path).then((d) => live && setData(d)).catch((e) => live && setErr(e.message));
    load();
    bus.addEventListener("changed", load);
    return () => { live = false; bus.removeEventListener("changed", load); };
  }, [path, S.viewer, ...deps]);
  return [data, err];
}

export function Effect({ te, pe }) {
  const parts = [];
  if (te && (te.federal || te.california)) parts.push(html`<div><span class="faint small">Tax </span><b class=${te.federal + te.california > 0 ? "neg" : ""}>${signed(te.federal)}</b> <span class="faint small">fed</span> <b>${signed(te.california)}</b> <span class="faint small">CA</span></div>`);
  if (pe && (pe.federal || pe.california)) parts.push(html`<div class="small"><span class="faint">Payments </span>${signed(pe.federal)} fed ${signed(pe.california)} CA</div>`);
  if (!parts.length) return html`<span class="faint small">No tax effect</span>`;
  return html`<div>${parts}</div>`;
}

export function statusPill(f) {
  const m = { open: f.kind === "error" ? "open-error" : f.kind, accepted: "accepted", resolved: "resolved", dismissed: "dismissed", verified: "verified" };
  const t = { open: f.kind === "error" ? "Open error" : f.kind === "judgment" ? "Needs judgment" : f.kind === "diagnostic" ? "Engine flag" : "Open", accepted: "Adjusted", resolved: "Resolved", dismissed: "Dismissed", verified: "Verified by check" };
  return html`<${Pill} k=${m[f.status]}>${t[f.status] || f.status}<//>`;
}

export async function fileToB64(file) {
  const buf = await file.arrayBuffer();
  let s = "";
  const b = new Uint8Array(buf);
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
  return btoa(s);
}
export async function upload(file) {
  return api("/api/upload", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ actor: S.viewer, name: file.name, type: file.type || "application/octet-stream", data_b64: await fileToB64(file) }) });
}
