"""Run: pytest -q   (from the repo root)"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import pytest

from workpaper.commands import execute
from workpaper.packet import get_packet
from workpaper.seed import seed_demo, seed_filed
from workpaper.state import PermissionError_, build_state
from workpaper.store import EventStore
from workpaper import views

P = get_packet()


@pytest.fixture
def store():
    s = EventStore(sqlite_path=os.path.join(tempfile.mkdtemp(), "t.db"))
    seed_demo(P, s)
    return s


def test_every_check_runs():
    st = build_state(P, [])
    assert not [f for f in st["findings"] if f["code"].startswith("CHECK_FAILED")]
    assert len([f for f in st["findings"] if f["kind"] == "error"]) >= 18


def test_full_season_passes_every_gate(store):
    seed_filed(P, store)  # raises if any permission or filing rule blocks a step
    st = build_state(P, store.all())
    assert st["filing"]["frozen"] and st["filing"]["blockers"] == []
    assert all(r["status"] == "agrees" for r in views.reconciliations(P, st))
    assert abs(views.books_to_tax(P, st)["diff"]) < 1
    assert store.verify()["ok"]


def test_cannot_review_own_work(store):
    st = build_state(P, store.all())
    execute(P, store, "st-02", "review_note.clear", {"note": st["review_notes"][0]["id"]})
    execute(P, store, "st-01", "signoff.sign", {"area": "california", "level": "preparer"})
    with pytest.raises(PermissionError_):
        execute(P, store, "st-01", "signoff.sign", {"area": "california", "level": "reviewer"})


def test_signoff_reopens_when_area_changes(store):
    execute(P, store, "st-01", "signoff.sign", {"area": "payments", "level": "preparer"})
    assert not build_state(P, store.all())["areas"]["payments"]["signoffs"]["preparer"]["stale"]
    execute(P, store, "st-01", "finding.accept", {"finding": "chk-estimates-vs-irs", "reason": "transcript"})
    assert build_state(P, store.all())["areas"]["payments"]["signoffs"]["preparer"]["stale"]


def test_batch_undo_restores_original(store):
    execute(P, store, "st-01", "finding.accept", {"finding": "chk-fx-wrong-year", "reason": "t"}, batch="b1")
    assert "SchB.1.6" in build_state(P, store.all())["current_values"]
    execute(P, store, "st-01", "batch.undo", {"batch": "b1"})
    st = build_state(P, store.all())
    assert "SchB.1.6" not in st["current_values"] and P.lines["v3"]["SchB.1.6"]["value"] == 1747


def test_roles_and_masking(store):
    with pytest.raises(PermissionError_):
        execute(P, store, "cu-01", "finding.accept", {"finding": "chk-fx-wrong-year"})
    with pytest.raises(PermissionError_):
        execute(P, store, "st-04", "sensitive.view", {"ref": "D08"})  # no clearance


def test_frozen_return_needs_amendment(store):
    seed_filed(P, store)
    with pytest.raises(PermissionError_):
        execute(P, store, "st-01", "adjustment.manual", {"line": "SchC.8", "to": 2000, "category": "schc_profit"})
    execute(P, store, "st-03", "filing.amend", {"reason": "test"})
    execute(P, store, "st-01", "adjustment.manual", {"line": "SchC.8", "to": 2000, "category": "schc_profit"})
    st = build_state(P, store.all())
    assert st["filing"]["frozen_values"]["SchC.8"] == 2100 and st["current_values"]["SchC.8"] == 2000
