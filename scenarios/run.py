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
from gateway.provider.port import GuardrailUnavailable             # noqa: E402
from scenarios import cassette, walkthrough as w                   # noqa: E402
from scenarios.machine_runs import SIGNATURES, machine             # noqa: E402

AUTHOR = {"id": "author-1", "kind": "person", "role": "course-author"}
ADMIN = {"id": "admin-1", "kind": "person", "role": "training-administrator"}


def pipeline(generator=None, screener=None) -> Pipeline:
    m = machine()
    p = Pipeline(m, generator or cassette.course_generator(),
                 screener or cassette.course_screener(), w.BRIEF["id"], cassette.KB_CHUNKS)
    m.screener = lambda rev, version: _revision_verdict(p, rev)
    return p


def _revision_verdict(p: Pipeline, rev) -> str:
    """StaleReview asks the screening port from inside the machine; a service
    that does not answer is a ConnectionError there, which the Timeout row takes."""
    try:
        v = p.screener.screen("", "text", "revision", subject=f"revision-{rev.id}")
    except GuardrailUnavailable as exc:
        raise ConnectionError(str(exc)) from exc
    return "allow" if v.allowed else v.category


def approve(p: Pipeline, node: str, **extra) -> None:
    out = p.membrane.request("approve_node", {"node": node, "actor": AUTHOR["id"],
                                              "what_was_shown": "formal verdict", **extra}, AUTHOR)
    assert out.ran, out


def publish(p: Pipeline) -> None:
    m = p.machine
    m.fire("CourseChecksRequested")
    m.fire("ApprovalGranted", {"signatures": SIGNATURES})
    out = p.membrane.request("publish_revision", {"actor": ADMIN["id"], "revision": m.current.id}, ADMIN)
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
    out = p.membrane.request("notify_learners", {"actor": ADMIN["id"], "notice_approved": True,
                                                 "recipients": 40}, ADMIN)
    assert out.ran, out
    return p


def after_publication(p: Pipeline) -> None:
    m = p.machine
    m.fire("ReviseRequested", {"revision": 1})
    edited = copy.deepcopy(w.CONTENT[w.T2])
    edited["blocks"][0]["text"] = "check every tool for splits and loose handles before use"
    p.screener.verdicts[("node-out", w.T2)] = ["allow"]
    m.fire("NodeEdited", {"node": w.T2, "content": edited})
    p._screen_node(w.T2)
    for node in (w.T2, w.E1):
        if m.current.nodes[node].state != "NodeApproved":
            approve(p, node)
    publish(p)
    m.fire("RollbackRequested", {"revision": 1, "reason": "the new wording confused learners"})
    m.fire("PolicyChanged", {"to": "pol-2", "reaches": {1: True, 2: False}})


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
