"""The only way anything changes: validate a command against current state, let the
server fill in what the client must not choose (what exactly was signed, the
snapshot that was frozen), then append one event."""
from __future__ import annotations

from .packet import Packet
from .state import PermissionError_, build_state, check_permission


class CommandError(Exception):
    pass


def execute(p: Packet, store, actor: str, type_: str, payload: dict, batch: str | None = None, at: str | None = None) -> dict:
    st = build_state(p, store.all(), viewer=actor)
    pl = dict(payload)
    check_permission(p, st, actor, type_, pl)  # raises PermissionError_
    if type_ == "signoff.sign":
        pl["hash"] = st["return_signoff"]["hash"] if pl["area"] == "return" else st["areas"][pl["area"]]["hash"]
    if type_ == "filing.freeze":
        pl["snapshot"] = st["filing"]["working_hash"]
        pl["summary"] = st["working"]
        pl["values"] = {k: st["current_values"].get(k, l["value"]) for k, l in p.lines["v3"].items()}
    if type_ == "client.approve":
        pl["snapshot"] = st["filing"]["working_hash"]
        pl["summary"] = st["working"]
    if type_ == "finding.accept":
        f = next((f for f in st["findings"] if f["id"] == pl.get("finding")), None)
        if not f or not f["proposal"]:
            raise CommandError("This finding has no proposed adjustment; resolve it with a reason instead.")
        if f["status"] == "accepted":
            raise CommandError("Already accepted.")
    if type_ == "seen":
        pl["seq"] = st["seq"]
    target = pl.get("finding") or pl.get("line") or pl.get("target") or pl.get("area") or pl.get("note")
    return store.append(actor, type_, pl, target=target, batch=batch, at=at)


__all__ = ["execute", "CommandError", "PermissionError_"]
