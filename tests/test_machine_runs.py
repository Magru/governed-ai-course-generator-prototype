"""Runs through the machine: the ordinary case, the refusals, the recoveries.

Each refusal test names the engine and the state it must end in, for the reason
the refusal scenes do — a run that stops for a different reason than the one it
claims is not evidence of anything. Each recovery test reads the counter it
spends, because the difference between a legal repair and a forbidden one is a
counter, not a category.
"""
from __future__ import annotations

import copy

import pytest
import yaml

from engines.temporal import engine as temporal
from machine.machine import MachineRefused
from scenarios.machine_runs import (CONTENT, EXAM, N1, OUTLINE, ROOT, brief, happy_path,
                                    machine, node_through, to_content, to_outline_review)


def _events(m) -> list[str]:
    return [s["event"] for s in m.trace()]


@pytest.fixture(scope="module")
def published():
    return happy_path()


def test_the_ordinary_course_reaches_published(published):
    rev = published.current
    assert rev.state == "Published"
    assert {n.state for n in rev.nodes.values()} == {"NodeApproved"}
    assert published.store.live_pointer == rev.id


def test_the_machines_own_trace_satisfies_every_invariant(published):
    verdict = temporal.check(published.trace())
    assert verdict.ok, verdict.refusal


def test_every_check_batch_left_a_step_the_trace_can_point_at(published):
    events = _events(published)
    # three node batches, the outline batch, the whole-course batch, and the
    # brief's feasibility — each an (auto) step, none an invented event name.
    assert events.count("(auto)") >= 6
    assert "CheckFailed" not in events


def test_an_event_the_tables_do_not_permit_is_refused():
    m = machine()
    with pytest.raises(MachineRefused, match="PublishRequested is not permitted"):
        m.fire("PublishRequested")
    assert _events(m) == ["(initial)"]
    # recorded and discarded (transitions.html §8): in the discard log, not the trace
    assert [d["event"] for d in m.store.discarded] == ["PublishRequested"]


def test_an_audience_the_author_was_not_granted_ends_the_revision():
    m = machine()
    m.fire("BriefSubmitted", {"brief": brief(audience=["supervisors"])})
    assert m.current.state == "BlockedFinal"


def test_a_denied_brief_ends_the_revision_and_a_malformed_one_does_not():
    denied = machine()
    denied.fire("BriefSubmitted", {"brief": brief()})
    denied.fire("GuardrailVerdict", {"verdict": "deny", "artifact": "brief"})
    assert denied.current.state == "BlockedFinal"
    malformed = machine()
    malformed.fire("BriefSubmitted", {"brief": brief(objectives=[])})
    assert (malformed.current.state, malformed.current.blocked_at) == ("BlockedRecoverable", "brief")


def test_an_unsatisfiable_brief_blocks_at_the_brief_before_any_model_call():
    twin = yaml.safe_load((ROOT / "fixtures/evil-twins/02-contradictory-brief.yaml").read_text())
    m = machine()
    m.fire("BriefSubmitted", {"brief": twin["brief"]})
    m.fire("GuardrailVerdict", {"verdict": "allow", "artifact": "brief"})
    assert (m.current.state, m.current.blocked_at) == ("BlockedRecoverable", "brief")
    assert "OutlineGenerated" not in _events(m)


def test_an_invented_skill_is_repaired_once_and_the_counter_says_so():
    outline = copy.deepcopy(OUTLINE)
    outline["nodes"][0]["skill"] = "post-mortem-facilitation"
    m = machine()
    to_outline_review(m, outline=outline)
    failed = next(s for s in m.store.steps if s["event"] == "CheckFailed")
    assert failed["producer"] == "checks"
    assert (m.current.state, m.current.repair_count) == ("OutlineDrafting", 1)


def test_an_exam_cannot_be_requested_before_its_topics_are_approved():
    m = machine()
    to_content(m)
    with pytest.raises(MachineRefused, match="the exam tests material nobody has approved"):
        m.fire("NodeGenerationRequested", {"node": EXAM})
    assert m.current.nodes[EXAM].state == "Planned"


def _leaking(content=None):
    content = copy.deepcopy(content or CONTENT[N1])
    content["cites"] = ["mt-kb-008"]              # incident records: supervisors only
    return content


def test_a_leak_is_repaired_inside_the_budget():
    m = machine()
    to_content(m)
    node_through(m, N1, _leaking())
    node = m.current.nodes[N1]
    assert (node.state, node.repair_count) == ("ContentDrafting", 1)
    assert N1 in m.current.used_restricted


def test_a_timeout_whose_write_landed_is_not_generated_twice():
    m = machine()
    to_content(m)
    m.fire("NodeGenerationRequested", {"node": N1})
    m.store.used_keys.add("gen-mt-node-001")
    m.fire("Timeout", {"node": N1, "idempotency_key": "gen-mt-node-001"})
    node = m.current.nodes[N1]
    assert (node.state, node.repair_count) == ("OutputGuardrail", 0)


def test_a_node_that_spends_its_retries_stops_the_revision_until_a_person_clears_it():
    m = machine()
    to_content(m)
    m.fire("NodeGenerationRequested", {"node": N1})
    for _ in range(m.store.budget() + 1):
        m.fire("Timeout", {"node": N1})
    assert (m.current.state, m.current.blocked_at) == ("BlockedRecoverable", "node")
    m.fire("BlockedInputFixed", {"node": N1})
    node = m.current.nodes[N1]
    assert (m.current.state, node.state, node.repair_count) == \
        ("ContentInProgress", "ContentDrafting", 0)
    assert temporal.check(m.trace()).ok


def test_the_model_has_no_way_back_from_repair_once_its_budget_is_spent():
    """A finding, pinned. NodeRecovery has a BlockedInputFixed row that resets
    the counter; NodeRepair has none. A node that fails its checks past the
    budget blocks the revision, clearing the block re-blocks it at once, and
    NodeEdited is not permitted from BlockedRecoverable. Only dropping the node
    from the outline or discarding the draft leaves. This test fails on the day
    the model gives NodeRepair its way out — which is the day to delete it."""
    m = machine()
    to_content(m)
    m.fire("NodeGenerationRequested", {"node": N1})
    for _ in range(m.store.budget() + 1):
        m.fire("NodeGenerated", {"node": N1, "content": _leaking()})
        m.fire("GuardrailVerdict", {"verdict": "allow", "artifact": N1, "node": N1})
    assert (m.current.state, m.current.nodes[N1].state) == ("BlockedRecoverable", "NodeRepair")
    m.fire("BlockedInputFixed", {"node": N1})
    assert (m.current.state, m.current.nodes[N1].state) == ("BlockedRecoverable", "NodeRepair")
    with pytest.raises(MachineRefused):
        m.fire("NodeEdited", {"node": N1, "content": CONTENT[N1]})
    # The way out that does exist: drop the node through a revised, re-checked
    # outline. The held node must not re-block the revision while its outline
    # is being checked, or this way out would not exist either.
    without = {"nodes": [n for n in OUTLINE["nodes"] if n["id"] != N1]}
    m.fire("OutlineRevised", {"outline": without})
    assert m.current.state == "OutlineReview"
    m.fire("OutlineApproved", {"reason": "the topic cannot be written from sources this audience may see"})
    assert (m.current.state, m.current.nodes[N1].state) == ("ContentInProgress", "Removed")
