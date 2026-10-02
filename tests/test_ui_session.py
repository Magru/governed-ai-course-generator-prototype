"""The page drives the real machine: the buttons a person presses reach the
same gateway and the same checks as `make run`, and a refusal is shown with
the engine and the artifact that refused it."""
from __future__ import annotations

import pytest

from scenarios import walkthrough as w
from ui.session import Session


def test_the_buttons_take_a_course_from_brief_to_publication():
    s = Session()
    steps = [("submit", None), ("approve_outline",)]
    for node in (w.T1, w.T2, w.T3, w.E1):
        steps += [("generate", node), ("approve", node)]
    steps += [("course_checks",), ("sign",), ("publish",)]
    for name, *args in steps:
        assert s.act(name, *args) == {"ok": True}, name
    snap = s.snapshot()
    assert snap["revision"]["state"] == "Published"
    assert snap["ltl"] == "every invariant holds"
    assert {e["kind"] for e in snap["engine_log"]} >= {"invented-skill", "leak-path"}


@pytest.mark.parametrize("preset, ends, engine", [
    ("forbidden", "BlockedFinal", None),
    ("infeasible", "BlockedRecoverable", "z3"),
    ("audience", "BlockedFinal", "opa"),
])
def test_each_refusal_preset_stops_where_the_specification_says(preset, ends, engine):
    s = Session(preset=preset)
    s.act("submit", None)
    snap = s.snapshot()
    assert snap["revision"]["state"] == ends
    assert [e["engine"] for e in snap["engine_log"]][-1:] == ([engine] if engine else [])


def test_a_button_the_machine_refuses_says_why_and_moves_nothing():
    s = Session()
    out = s.act("publish")
    assert not out["ok"] and out["error"].startswith("policy_allows: ")   # refused at the gate, by name
    assert s.snapshot()["revision"]["state"] == "AwaitingBrief"
