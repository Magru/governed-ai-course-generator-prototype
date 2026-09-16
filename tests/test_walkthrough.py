"""walkthrough.html reproduced by the machine, and a harness that can say no."""
from __future__ import annotations

import dataclasses

import pytest

from scenarios import walkthrough
from scenarios.replay import play


@pytest.fixture(scope="module")
def played():
    return walkthrough.run()


def test_every_step_of_the_walkthrough_happens_as_the_page_says(played):
    _, result = played
    assert result.ok, result.report()


def test_the_walkthroughs_trace_satisfies_every_invariant(played):
    _, result = played
    assert result.ltl.ok, result.report()


def test_the_run_has_the_pages_shape(played):
    m, _ = played
    events = [s["event"] for s in m.trace()]
    assert events.count("OutlineGenerated") == 2          # one repair
    assert events.count("CheckFailed") == 1
    assert events.count("Timeout") == 1
    assert events.count("NodeApproved") == 4
    assert events[-1] == "LivePointerMoved"


def test_the_harness_reports_a_wrong_expectation_and_an_unexpected_permission():
    beats = walkthrough.beats()
    wrong = [dataclasses.replace(b, course="Approved") if b.label == "9" else b for b in beats]
    wrong = [dataclasses.replace(b, refused=None) if b.label == "18·fenced" else b for b in wrong]
    wrong = [dataclasses.replace(b, refused="anything") if b.label == "22" else b for b in wrong]
    result = play(walkthrough.machine(), wrong)
    assert any(m.startswith("9: course is ContentInProgress") for m in result.mismatches)
    assert any(r.startswith("18·fenced") for r in result.refused)
    assert any(m.startswith("22: CourseChecksRequested was permitted") for m in result.mismatches)
