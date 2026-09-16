"""`make run`, as tests: the course through the gateway, and the seven twins."""
from __future__ import annotations

import pytest

from engines.temporal import engine as temporal
from scenarios import run
from scenarios.twins import TWIN_RUNS


@pytest.fixture(scope="module")
def course():
    p = run.the_course()
    run.after_publication(p)
    return p


def test_the_course_ends_where_the_rollback_leaves_it(course):
    m = course.machine
    assert {r.id: r.state for r in m.store.revisions.values()} == {1: "Published", 2: "Superseded"}
    assert m.store.live_pointer == 1 and not m.store.discarded


def test_every_gateway_stage_the_run_needs_was_passed(course):
    passed = {number for number, *_ in course.stages}
    assert {1, 3, 4, 5, 6, 10} <= passed


def test_the_repair_prompt_carries_the_refusal_not_just_a_retry(course):
    asked = [prompt for task, prompt in course.generator.asked if task == "node:mt-node-202"]
    assert len(asked) == 2
    assert "cannot see" not in asked[0].instructions
    assert "cannot see" in asked[1].instructions


def test_a_timeout_is_retried_under_the_same_key_and_lands_once(course):
    timeouts = [s for s in course.machine.trace() if s["event"] == "Timeout"]
    assert len(timeouts) == 1
    generated = [s for s in course.machine.trace()
                 if s["event"] == "NodeGenerated" and s.get("node") == "mt-node-203"]
    assert len(generated) == 1


def test_the_whole_run_satisfies_every_invariant(course):
    verdict = temporal.check(course.machine.trace())
    assert verdict.ok, verdict.refusal


@pytest.mark.parametrize("title, scene, holds", TWIN_RUNS, ids=[t[0][:2] for t in TWIN_RUNS])
def test_each_twin_stops_where_the_specification_says(title, scene, holds):
    result = scene()
    assert holds(result), f"{title}: {result}"
