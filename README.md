# Workpaper: Okafor-Lindqvist 2025

A web-native tax workpaper for the MiraFlores case study, by Palak Kakani.

**Core idea:** the engine's output is evidence; the workpaper is a record of decisions about it.
The packet is loaded exactly as delivered and never edited. Everything people do (accept a finding,
adjust a number, verify, ask, sign, file) is one event in an append-only, hash-chained log. The screen
you see is always `packet + events` replayed, so history, undo, "what changed since I looked",
comparing two moments, freezing at filing and amending on top all come from the same mechanism.

## Run it locally

```bash
pip install -r requirements.txt
cd app
uvicorn server:app --reload
# open http://localhost:8000
```

The packet ships at `app/data/packet.json` (the delivered `Instructions.json`, unmodified).
Set `PACKET_PATH` to load a different packet.

## Deploy (Render, free)

1. Push this folder to a GitHub repository.
2. On render.com: **New > Blueprint**, pick the repository. `render.yaml` does the rest.
3. Open the URL Render gives you. First load on the free plan can take ~30 seconds while it wakes up.

Without `DATABASE_URL` the event log is SQLite on the instance's disk, and the demo re-seeds itself
if the instance restarts. To keep events across restarts, add a Render Postgres database and set
`DATABASE_URL` to its connection string. A `Dockerfile` is included for any other host.

## Using it

- **Viewing as** (top right) switches people and roles: preparer, reviewer, partner, a preparer without
  sensitive-data clearance, firm administrator, quality reviewer, and both clients. Permissions are
  enforced by the server, not just hidden in the UI.
- Click any number, document, finding or reference to open the **trace**: how it was built, what it
  feeds, its source document with the exact field highlighted, its history across engine runs and last
  year, and every change, verification and note on it.
- **Demo data** (bottom of the left menu) resets the shared log to: June 2026 mid-review (default), the
  season played through to the 2028 IRS letter, or blank engine output.

## Layout

```
app/
  server.py              HTTP API and static files
  workpaper/
    packet.py            read-only packet access, reference resolver, field highlighting, masking
    checks.py            independent checks that recompute from the documents (the error findings)
    store.py             append-only, hash-chained event log (SQLite or Postgres)
    state.py             replays events into the current workpaper; permissions; filing gate; inbox
    commands.py          the one path for every change: validate, server-fills, append
    views.py             reconciliations, sales detail, books to tax, state split, variance,
                         records, notice packet, roll-forward
    seed.py              demo scenarios (each step goes through the same permission checks)
  static/                Preact + htm UI, no build step
scripts/                 analysis scripts used while looking for errors; export_findings.py
tests/                   pytest: full season passes every gate, sign-off reopening, undo, roles, freeze/amend
```

## Tests

```bash
pip install pytest
pytest -q
```
