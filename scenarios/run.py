"""`make run` — one course from an empty brief to a rollback, through the gateway.

Every model call and every screening crosses the membrane and the eleven stages;
every state change is the machine's; the trace at the end goes to the temporal
engine. Generation answers come from a recording, so the run is the same run
every time. Afterwards, each evil twin runs as a branch of its own and must stop
where the specification says it stops.
"""
from __future__ import annotations

import copy
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from engines.temporal import engine as temporal                    # noqa: E402
from gateway.pipeline import Pipeline                              # noqa: E402
from gateway.screened_text import screened_text                    # noqa: E402
from gateway.provider.port import GuardrailUnavailable             # noqa: E402
from scenarios import cassette, walkthrough as w                   # noqa: E402
from scenarios.machine_runs import SIGNATURES, machine, signatures  # noqa: E402

AUTHOR = {"id": "author-1", "kind": "person", "role": "course-author"}
ADMIN = {"id": "admin-1", "kind": "person", "role": "training-administrator"}
from scenarios.machine_runs import NOTICE                          # noqa: E402,F401


def pipeline(generator=None, screener=None) -> Pipeline:
    m = machine()
    p = Pipeline(m, generator or cassette.course_generator(),
                 screener or cassette.course_screener(), w.BRIEF["id"], cassette.KB_CHUNKS)
    m.screener = lambda rev, version: _revision_verdict(p, rev, version)
    return p


def _revision_verdict(p: Pipeline, rev, version: str) -> tuple[str, str]:
    """StaleReview asks the screening port from inside the machine; a service
    that does not answer is a ConnectionError there, which the Timeout row takes."""
    asked = len(p.screenings)
    try:
        v = p.screen(_revision_text(rev), "text", "revision", f"revision-{rev.id}")
    except GuardrailUnavailable as exc:
        raise ConnectionError(str(exc)) from exc
    verdict = "allow" if v.allowed else v.category
    version = v.guardrail_version
    if len(p.screenings) > asked:             # a guard asking twice is one screening
        p._stage(6, f"guardrail revision · {version}", f"revision-{rev.id}", verdict)
    return verdict, version


def _revision_text(rev) -> str:
    """What a live revision is re-screened on: the prose of every node in it."""
    return " ".join(screened_text(n.content) for n in rev.nodes.values())


def approve(p: Pipeline, node: str, **extra) -> None:
    out = p.membrane.request("approve_node", {"node": node, "what_was_shown": "formal verdict",
                                              **extra}, AUTHOR)
    assert out.ran, out


def publish(p: Pipeline, notice: str = NOTICE) -> None:
    """Consent is to the notice the approvers were shown, so publishing names it."""
    m = p.machine
    m.fire("CourseChecksRequested")
    m.fire("ApprovalGranted", {"signatures": signatures(notice)})
    out = p.membrane.request("publish_revision", {"revision": m.current.id}, ADMIN)
    assert out.ran, out


def the_course() -> Pipeline:
    p = pipeline()
    m = p.machine
    p.submit_brief(copy.deepcopy(w.BRIEF), AUTHOR)
    while m.current.state == "OutlineDrafting":
        p.draft_outline(AUTHOR)
    m.fire("OutlineApproved", {"actor": AUTHOR["id"]})
    for node in (w.T1, w.T2, w.T3):
        p.generate_node(node, AUTHOR)
        approve(p, node, **({"visuals_reviewed": [f"{w.T1}.blocks[1]"]} if node == w.T1 else {}))
    p.generate_node(w.E1, AUTHOR)
    approve(p, w.E1)
    publish(p)
    out = p.notify_learners(NOTICE, 40, ADMIN)
    assert out.ran, out
    return p


def after_publication(p: Pipeline) -> None:
    m = p.machine
    m.fire("ReviseRequested", {"revision": 1})
    edited = copy.deepcopy(w.CONTENT[w.T2])
    edited["blocks"][0]["text"] = "check every tool for splits and loose handles before use"
    m.fire("NodeEdited", {"node": w.T2, "content": edited})
    p._screen_node(w.T2)
    for node in (w.T2, w.E1):
        if m.current.nodes[node].state != "NodeApproved":
            approve(p, node)
    publish(p)
    m.fire("RollbackRequested", {"revision": 1, "reason": "the new wording confused learners"})
    m.fire("PolicyChanged", {"to": "pol-2", "reaches": {1: True, 2: False}})
    # A new guardrail version reaches the live course: the same text is screened
    # again, because a verdict under guard-1 says nothing about guard-2.
    p.screener.version = "guard-2"                # the service rolled out first
    m.fire("GuardrailChanged", {"to": "guard-2", "reaches": {1: True, 2: False}})


def report(p: Pipeline) -> int:
    m = p.machine
    for number, name, subject, result in p.stages:
        print(f"  stage {number:>2} {name:<26} {subject:<22} {result}")
    states = {r.id: r.state for r in m.store.revisions.values()}
    print(f"\n  revisions {states} · live pointer {m.store.live_pointer} · "
          f"{len(m.trace())} trace steps · {len(m.store.discarded)} discarded")
    verdict = temporal.check(m.trace())
    print("  LTL: every invariant holds" if verdict.ok else f"  LTL: {verdict.refusal.summary}")
    return 0 if verdict.ok else 1


def main() -> int:
    from scenarios.twins import run_twins
    p = the_course()
    after_publication(p)
    status = report(p)
    print()
    return status or run_twins()


if __name__ == "__main__":
    raise SystemExit(main())
