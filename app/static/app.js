import { render } from "preact";
import { html, useState, useEffect, useStore, store as S, api, q, act, emit, refresh, trace, toast, describeEvent, who, role, bus } from "./core.js";
import { Drawer } from "./trace.js";
import { Overview, Issues, Return, Documents, Recon, Sales } from "./pages1.js";
import { Books, States, Records, Variance, Areas, People, Filing, Notice, ClientCopy, Firm, Activity, WhatIf, ClientHome } from "./pages2.js";

const ROUTES = {
  "": [Overview, "Overview"], issues: [Issues, "Findings"], return: [Return, "Return lines"], docs: [Documents, "Documents"],
  recon: [Recon, "Reconciliations"], sales: [Sales, "Sales detail"], books: [Books, "Books to tax"], states: [States, "State split"],
  records: [Records, "Records"], variance: [Variance, "Against last year"], whatif: [WhatIf, "What-ifs"],
  areas: [Areas, "Areas & sign-off"], people: [People, "Questions & notes"], filing: [Filing, "Filing & after"],
  activity: [Activity, "Activity & versions"], firm: [Firm, "Firm"], notice: [Notice, "Notice response"], clientcopy: [ClientCopy, "Client copy"], client: [ClientHome, "My return"],
};
const NAV = [
  ["Review", ["", "issues", "return", "docs"]],
  ["Prove it", ["recon", "sales", "books", "states", "records", "variance", "whatif"]],
  ["People & filing", ["areas", "people", "filing", "activity"]],
  ["Firm", ["firm"]],
];

function useRoute() {
  const [r, setR] = useState(location.hash.replace(/^#\/?/, ""));
  useEffect(() => { const f = () => setR(location.hash.replace(/^#\/?/, "")); addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []);
  return r;
}

function Search() {
  const [t, setT] = useState("");
  const [res, setRes] = useState([]);
  useEffect(() => {
    if (t.length < 2) { setRes([]); return; }
    const id = setTimeout(() => q(`/api/search?q=${encodeURIComponent(t)}`).then(setRes), 160);
    return () => clearTimeout(id);
  }, [t]);
  const go = (r) => { setT(""); setRes([]); trace(r.kind === "value" ? r.id : r.kind === "doc" ? "doc:" + r.id : r.id); };
  return html`<div style="position:relative"><input class="search" type="search" placeholder="Search numbers, documents, findings, client answers" value=${t} onInput=${(e) => setT(e.target.value)}
    onKeyDown=${(e) => { if (e.key === "Enter" && res[0]) go(res[0]); if (e.key === "Escape") setT(""); }} aria-label="Search" />
    ${res.length ? html`<div class="pop searchres">${res.slice(0, 14).map((r) => html`<div class="item" style="cursor:pointer" onClick=${() => go(r)}><span class="pill">${r.kind}</span> <b>${r.title}</b><div class="faint small">${r.subtitle}</div></div>`)}</div>` : null}</div>`;
}

function Bell() {
  const s = useStore();
  const [open, setOpen] = useState(false);
  const n = s.state.inbox.length + s.state.since_last_seen.length;
  return html`<div style="position:relative"><button class="bell" onClick=${() => setOpen(!open)} aria-expanded=${open}>For you<span class="count">${n}</span></button>
    ${open ? html`<div class="pop" onClick=${() => setOpen(false)}>
      <div class="item"><b>To do</b></div>${s.state.inbox.length ? s.state.inbox.map((i) => html`<div class="item" style="cursor:pointer" onClick=${() => i.target ? trace(i.target) : (location.hash = i.kind === "approve_return" ? "#/client" : i.kind === "approve" ? "#/filing" : "#/areas")}>${i.text}</div>`) : html`<div class="item faint">Nothing waiting on you.</div>`}
      <div class="item"><b>Changed since you last looked</b></div>${s.state.since_last_seen.slice(-10).reverse().map((e) => html`<div class="item">${describeEvent(e)}</div>`)}
      ${s.state.since_last_seen.length ? html`<div class="item"><button class="btn small" onClick=${() => act("seen", {}, { toast: "Marked as seen." })}>Mark as seen</button></div>` : null}</div>` : null}</div>`;
}

function Toasts() {
  const s = useStore();
  const undo = async (u) => {
    let batch = u.batch;
    if (!batch) {
      const mine = s.state.adjustments.filter((a) => a.by === S.viewer && a.active).sort((a, b) => b.seq - a.seq)[0];
      batch = mine && mine.batch;
    }
    if (batch) act("batch.undo", { batch }, { toast: "Undone. The original numbers are back." });
  };
  return html`<div class="toasts" role="status" aria-live="polite">${s.toasts.map((t) => html`<div class=${"toast" + (t.err ? " err" : "")}>${t.text}${t.undo ? html`<button onClick=${() => undo(t.undo)}>Undo</button>` : null}</div>`)}</div>`;
}

function Welcome({ onClose }) {
  const go = (fn) => { onClose(); fn(); };
  const tries = [
    ["See a mistake and its proof", "Open the California wages finding: the rule, the paystub, the highlighted field.", () => { location.hash = "#/issues"; setTimeout(() => trace("chk-ca-wages-after-move"), 300); }],
    ["Trace any number", "Click a number on the return and follow it back to the exact spot on the source form.", () => { location.hash = "#/return"; setTimeout(() => trace("SchC.1"), 300); }],
    ["Watch figures reconcile", "20 figures that should agree. Red breaks name the finding that explains them.", () => { location.hash = "#/recon"; }],
    ["Switch roles", "Use “Viewing as” (top right). Try Marcus (no SSN clearance) or Ngozi (the client).", () => {}],
    ["Play the season through", "Reset to the filed season: frozen return, e-file events, the 2028 IRS letter.", () => { location.hash = "#/filing"; }],
  ];
  return html`<div class="drawer-backdrop" onClick=${onClose}></div>
  <div class="welcome" role="dialog" aria-label="Welcome">
    <h2>A workpaper that proves the return is right</h2>
    <p class="muted" style="margin-top:6px">Okafor-Lindqvist, 2025. The engine's numbers are evidence and are never edited. Every decision people make is saved as an event, so nothing is lost: history, undo, sign-offs and filing all come from that log. 26 independent checks found 18 errors the engine missed or only flagged.</p>
    <div class="tries">${tries.map(([t, d, f], i) => html`<button class="try" onClick=${() => go(f)}><b>${t}</b><span>${d}</span></button>`)}</div>
    <p class="small muted">Shared demo: other people's changes appear live. Reset it any time from the bottom of the left menu. Built by Palak Kakani.</p>
    <div class="row" style="justify-content:flex-end"><button class="btn primary" onClick=${onClose}>Start reviewing</button></div>
  </div>`;
}

function App() {
  const s = useStore();
  const r = useRoute();
  const [welcome, setWelcome] = useState(() => { try { return !localStorage.getItem("wp.welcomed"); } catch { return true; } });
  const closeWelcome = () => { setWelcome(false); try { localStorage.setItem("wp.welcomed", "1"); } catch {} };
  const isClient = role() === "client";
  const key = r.split("/")[0];
  let [Page] = ROUTES[key] || ROUTES[""];
  if (isClient && !["client", "clientcopy"].includes(key)) Page = ClientHome;
  const counts = { issues: s.state.findings.filter((f) => f.status === "open" && f.kind === "error").length };
  const switchTo = async (id) => {
    S.viewer = id;
    try { localStorage.setItem("wp.viewer", id); } catch {}
    await refresh();
    if (who(id).role === "client") location.hash = "#/client";
    else if (location.hash.startsWith("#/client")) location.hash = "#/";
  };
  const reset = async (scenario) => {
    if (!confirm(`Reset the shared demo to "${scenario}"? Everyone's changes are replaced.`)) return;
    await api(`/api/demo/reset?scenario=${scenario}`, { method: "POST" });
    await refresh(); bus.dispatchEvent(new Event("changed")); toast(`Demo reset: ${scenario}.`);
  };
  const st = s.state.filing;
  return html`<div class="shell">
    <header class="top">
      <div class="brand"><span class="logo" aria-hidden="true">W</span><div class="client"><b>Okafor-Lindqvist · 2025</b><span>Form 1040 + California 540NR · client ${s.meta.packet.client_id}</span></div></div>
      <span class=${"status-chip" + (st.frozen ? " frozen" : st.blockers.length ? "" : " ready")}>${st.frozen ? (st.amending ? "Filed · amending" : "Filed · frozen") : st.blockers.length ? `${st.blockers.length} things block filing` : "Ready to file"}</span>
      ${isClient ? null : html`<${Search} />`}
      <div class="grow"></div>
      <${Bell} />
      <label class="small" style="color:#b9c4cf">Viewing as
        <select value=${S.viewer} onChange=${(e) => switchTo(e.target.value)} aria-label="Switch role">
          ${s.meta.actors.map((a) => html`<option value=${a.id}>${a.name} · ${a.role.replaceAll("_", " ")}</option>`)}</select></label>
    </header>
    <nav class="nav" aria-label="Sections">
      ${isClient ? html`<a href="#/client" class="on">My return</a>${st.frozen ? html`<a href="#/clientcopy">My copy</a>` : null}` :
        NAV.map(([g, items]) => html`<div class="grp">${g}</div>${items.map((k) => html`<a href=${"#/" + k} class=${key === k ? "on" : ""}>${ROUTES[k][1]}${k === "issues" && counts.issues ? html`<span class="badge">${counts.issues}</span>` : k === "issues" ? html`<span class="badge ok">0</span>` : null}</a>`)}`)}
      <div class="grp">Demo data</div>
      <a onClick=${() => setWelcome(true)}>What to try first</a>
      <a onClick=${() => reset("midseason")}>Reset: June 2026, mid-review</a>
      <a onClick=${() => reset("filed")}>Reset: season played through</a>
      <a onClick=${() => reset("empty")}>Reset: blank (engine output only)</a>
    </nav>
    <main id="main"><${Page} /></main>
    <${Drawer} /><${Toasts} />${welcome ? html`<${Welcome} onClose=${closeWelcome} />` : null}
  </div>`;
}

async function boot() {
  const meta = await api("/api/meta");
  meta.lineIndex = Object.fromEntries(meta.lines.map((l) => [l.key, l]));
  meta.docIndex = Object.fromEntries(meta.documents.map((d) => [d.id, d]));
  S.meta = meta;
  let v = null;
  try { v = localStorage.getItem("wp.viewer"); } catch {}
  S.viewer = meta.actors.some((a) => a.id === v) ? v : "st-02";
  await refresh();
  const root = document.getElementById("app");
  root.innerHTML = "";  // drop the "Loading" placeholder before the app mounts
  render(html`<${App} />`, root);
  // several people at once: poll and announce what others did
  setInterval(async () => {
    if (document.hidden) return;
    const before = S.state.seq;
    const { st } = await refresh();
    if (st.seq > before) {
      const fresh = st.since_last_seen.filter((e) => e.seq > before && e.actor !== S.viewer);
      if (fresh.length) toast(describeEvent(fresh[fresh.length - 1]) + (fresh.length > 1 ? ` (+${fresh.length - 1} more)` : ""));
    }
  }, 4000);
}
boot().catch((e) => { document.getElementById("app").innerHTML = `<p class="boot">Couldn't load the workpaper: ${e.message}</p>`; });
