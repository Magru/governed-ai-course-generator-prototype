"""The membrane: nothing unregistered runs, and each refusal names its check."""
from __future__ import annotations

import copy

import pytest

from gateway.actions import REGISTRY
from gateway.membrane import Membrane
from scenarios.machine_runs import CONTENT, N1, machine, to_content

AUTHOR = {"id": "author-1", "kind": "person", "role": "course-author"}
SYSTEM = {"id": "orchestrator", "kind": "system", "role": "system"}


@pytest.fixture
def gate():
    m = machine()
    to_content(m)
    m.fire("NodeGenerationRequested", {"node": N1})
    return Membrane(m, "mt-course-001")


def test_the_registry_is_the_eleven_actions_the_specification_lists():
    assert len(REGISTRY) == 11
    assert {a.name for a in REGISTRY.values() if a.risk == "critical"} == \
        {"publish_revision", "move_live_pointer", "notify_learners"}


def test_an_unregistered_action_runs_nothing(gate):
    before = len(gate.machine.trace())
    out = gate.request("delete_course", {}, AUTHOR)
    assert (out.ran, out.check) == (False, "registered")
    assert len(gate.machine.trace()) == before


def test_an_extra_field_is_refused_not_ignored(gate):
    out = gate.request("generate_node_content",
                       {"node": N1, "content": CONTENT[N1], "publish_after": True}, SYSTEM)
    assert (out.ran, out.check) == (False, "schema_valid")
    assert "publish_after" in out.reason


def test_legality_is_the_machines_answer(gate):
    out = gate.request("publish_revision", {"actor": "admin-1", "revision": 1},
                       {"id": "admin-1", "kind": "person", "role": "training-administrator"})
    assert (out.ran, out.check) == (False, "legal_in_state")
    assert "PublishRequested is not permitted" in out.reason


def test_a_legal_generation_runs_once_and_its_repeat_is_a_no_op(gate):
    args = {"node": N1, "content": copy.deepcopy(CONTENT[N1])}
    first = gate.request("generate_node_content", args, AUTHOR)
    assert first.ran and gate.machine.current.nodes[N1].state == "OutputGuardrail"
    steps = len(gate.machine.trace())
    again = gate.request("generate_node_content", copy.deepcopy(args), AUTHOR)
    assert not again.ran and len(gate.machine.trace()) == steps
    # A finding, pinned. safety.html §3 orders legal_in_state (5) before
    # idempotency_key_unused (7). Once the first call has moved the node on, a
    # repeat is refused as illegal rather than recognised as already done: no
    # second effect either way, but the person is told "take the move the state
    # permits" instead of "nothing to do". The key lookup is also the cheaper
    # check, which the section's own rule puts first.
    assert again.check == "legal_in_state"


def test_issued_and_landed_are_two_facts(gate):
    key = gate.request("generate_node_content",
                       {"node": N1, "content": copy.deepcopy(CONTENT[N1])}, AUTHOR).key
    assert key in gate.issued                      # before the effect
    assert key in gate.machine.store.used_keys     # after it, recorded by the store
    refused = gate.request("publish_revision", {"actor": "admin-1", "revision": 1},
                           {"id": "admin-1", "kind": "person", "role": "training-administrator"})
    assert refused.key is None and len(gate.issued) == 1


def test_an_action_the_registry_gives_a_person_is_refused_to_the_system(gate):
    assert gate.request("generate_node_content",
                        {"node": N1, "content": copy.deepcopy(CONTENT[N1])}, AUTHOR).ran
    assert gate.request("admit_to_revision", {"node": N1, "verdict": "allow", "artifact": N1},
                        SYSTEM).ran
    out = gate.request("approve_node", {"node": N1, "actor": "author-1",
                                        "what_was_shown": "the verdict"}, SYSTEM)
    assert (out.ran, out.check) == (False, "approval_present")
    ok = gate.request("approve_node", {"node": N1, "actor": "author-1",
                                       "what_was_shown": "the verdict"}, AUTHOR)
    assert ok.ran and gate.machine.current.nodes[N1].state == "NodeApproved"


def test_the_policy_is_asked_before_the_state_is(gate):
    stranger = {"id": "compliance-1", "kind": "person", "role": "compliance-officer"}
    out = gate.request("generate_node_content", {"node": N1, "content": CONTENT[N1]}, stranger)
    assert (out.ran, out.check) == (False, "policy_allows")


def test_the_rate_limit_is_a_ceiling(gate):
    gate.rate_limit = 1
    assert gate.request("retrieve_sources", {"query": "a", "audience": ["apprentices"]}, SYSTEM).ran
    out = gate.request("retrieve_sources", {"query": "b", "audience": ["apprentices"]}, SYSTEM)
    assert (out.ran, out.check) == (False, "within_rate_limit")
