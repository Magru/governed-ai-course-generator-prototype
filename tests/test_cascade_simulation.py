"""The cascade simulation reads its prices from the budget and its dependencies
from the real Datalog closure, and the machine settles the way it reports."""
from __future__ import annotations

import pytest

from scenarios import cascade as sim


def test_the_prices_are_the_budget_files_not_the_simulations():
    """The budget file states about 111 ms unedited and 311 ms hand-edited."""
    assert (sim.RECHECK_MS, sim.EDITED_MS) == (111, 311)


def test_an_edit_reaches_part_of_a_course_through_the_real_closure():
    nodes = sim.course(24)
    r = sim.one_edit(nodes)
    assert r["edits"] == 24 and 0 < r["mean"] <= r["max"] < len(nodes)
    exam = next(n for n in nodes if n["id"] == "e00")
    assert set(exam["topics"]) <= {n["id"] for n in nodes}


@pytest.mark.parametrize("between, expected", [(False, 1), (True, 1 + sim.REPAIR_BUDGET)])
def test_the_cascade_withdraws_approvals_and_settles(between, expected):
    s = sim.settling_on_the_machine(between)
    assert (s["sent_back"], s["settled_in"]) == (expected, "ReadyForReview")
