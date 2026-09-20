"""A course has one line of work, and each revision is judged on its own.

The trace holds every revision of a course, so a step of the live one sitting
between two steps of a draft must not be read as the draft's own past. A second
revision cannot be opened while a draft is still open. A fork carries the author
who submitted the brief. And a consent to a notice is consent to that text, once.
"""
from __future__ import annotations

import copy

import pytest

from engines.schema import engine as schema
from engines.temporal import engine as temporal
from machine.refusal import MachineRefused
from scenarios import run, walkthrough as w


def _published(notices=0):
    p = run.the_course()
    # One more recorded answer per further notice: the cassette records exactly
    # the screenings the run makes.
    p.screener.verdicts[("notice-out", "notice:revision-1")] += ["allow"] * notices
    return p, p.machine


def test_a_notice_on_the_live_course_is_not_read_as_the_drafts_own_past():
    p, m = _published(notices=1)
    m.fire("ReviseRequested", {"revision": 1})
    draft = m.current.id
    m.fire("ApprovalGranted", {"signatures": run.signatures("A second note."), "revision": 1})
    assert p.notify_learners("A second note.", 40, run.ADMIN, revision=1).ran
    m.current = m.store.revisions[draft]
    edited = copy.deepcopy(w.CONTENT[w.T2])
    edited["blocks"][0]["text"] = "check every tool for splits before use"
    m.fire("NodeEdited", {"node": w.T2, "content": edited})
    p.screen_node(w.T2)
    assert temporal.check(m.trace()).ok


def test_a_second_revision_cannot_be_opened_while_a_draft_is_open():
    p, m = _published()
    m.fire("ReviseRequested", {"revision": 1})
    opened = m.current.id
    with pytest.raises(MachineRefused):
        m.fire("ReviseRequested", {"revision": 1})
    assert m.current.id == opened
    m.fire("DraftDiscarded", {"reason": "starting over", "actor": run.AUTHOR["id"]})
    m.fire("ReviseRequested", {"revision": 1})
    assert m.current.id != opened


def test_a_fork_carries_the_author_who_submitted_the_brief():
    p, m = _published()
    m.fire("ReviseRequested", {"revision": 1})
    assert m.current.author == m.store.revisions[1].author


def test_nodes_of_a_revision_nobody_is_working_on_do_not_move():
    p, m = _published()
    with pytest.raises(MachineRefused):
        m.fire("Timeout", {"node": w.T2, "revision": 1})
    assert m.store.revisions[1].nodes[w.T2].state == "NodeApproved"


def test_a_node_may_not_take_the_name_of_an_artifact_the_record_screens():
    outline = copy.deepcopy(w.OUTLINE)
    outline["nodes"][0]["id"] = "revision"
    assert not schema.check(outline, "outline").ok


def test_a_withdrawn_course_can_tell_its_learners_and_needs_consent_to_do_it():
    p, m = _published(notices=1)
    p.membrane.request("withdraw_revision", {"revision": 1, "reason": "an error in module two"},
                       run.ADMIN)
    assert m.store.revisions[1].state == "Withdrawn"
    notice = "Hand tool safety is off air while we correct module two."
    assert not p.notify_learners(notice, 40, run.ADMIN, revision=1).ran   # nobody consented to it
    m.fire("ApprovalGranted", {"signatures": run.signatures(notice), "revision": 1})
    assert p.notify_learners(notice, 40, run.ADMIN, revision=1).ran
    assert temporal.check(m.trace()).ok


def test_an_action_naming_a_revision_that_does_not_exist_is_refused_not_crashed_on():
    p, m = _published()
    out = p.membrane.request("withdraw_revision", {"revision": 99, "reason": "a typo"}, run.ADMIN)
    assert (out.ran, out.check) == (False, "legal_in_state")
    assert "does not exist" in out.reason
    assert m.store.revisions[1].state == "Published"


def test_a_notice_to_nobody_is_not_a_notice():
    p, m = _published(notices=1)
    m.store.enrolled_learners = 0
    assert not p.notify_learners("Anyone there?", 0, run.ADMIN, revision=1).ran


def test_a_notice_finds_the_revision_learners_were_reading_when_the_course_is_off_air():
    p, m = _published(notices=1)
    p.membrane.request("withdraw_revision", {"revision": 1, "reason": "an error in module two"},
                       run.ADMIN)
    assert m.store.live_pointer is None
    notice = "Hand tool safety is off air while we correct module two."
    m.fire("ApprovalGranted", {"signatures": run.signatures(notice), "revision": 1})
    assert p.notify_learners(notice, 40, run.ADMIN).ran        # no revision named
