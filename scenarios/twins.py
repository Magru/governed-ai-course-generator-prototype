"""The seven evil twins, each run through the gateway and the machine.

A twin is a request built to be refused, and fixtures/evil-twins says by whom
and where the run must end. Each branch here starts a fresh course and passes
only if it stops at that layer, in that state — a twin refused for a different
reason is a scene that proves nothing.
"""
from __future__ import annotations

import copy

import yaml

from gateway.provider.recorded import RecordedGenerator, RecordedScreener
from machine.machine import MachineRefused
from scenarios import cassette, walkthrough as w
from scenarios.run import AUTHOR, pipeline

TWINS = cassette.ROOT / "fixtures" / "evil-twins"


def _twin(name: str) -> dict:
    return yaml.safe_load((TWINS / name).read_text())


def forbidden_topic():
    twin = _twin("01-forbidden-topic.yaml")
    screener = RecordedScreener({("brief-in", "brief"): [twin["expect"]["matches"]]})
    p = pipeline(screener=screener)
    p.submit_brief(twin["brief"], {"id": "author-1", "kind": "person"})
    return p.machine.current.state, p.stages[-2][3]


def contradictory_brief():
    p = pipeline(screener=RecordedScreener({("brief-in", "brief"): ["allow"]}))
    p.submit_brief(_twin("02-contradictory-brief.yaml")["brief"], AUTHOR)
    return p.machine.current.state, p.machine.current.blocked_at


def restricted_source():
    generator = RecordedGenerator({"outline": [copy.deepcopy(w.OUTLINE)],
                                   f"node:{w.T1}": [cassette.leaking(w.T1),
                                                    copy.deepcopy(w.CONTENT[w.T1])]})
    p = pipeline(generator=generator)
    p.submit_brief(copy.deepcopy(w.BRIEF), AUTHOR)
    p.draft_outline(AUTHOR)
    p.machine.fire("OutlineApproved")
    p.screener.verdicts[("image-out", f"{w.T1}.blocks[1]")] = ["allow"]
    p.generate_node(w.T1, AUTHOR)
    node = p.machine.current.nodes[w.T1]
    return node.state, node.last_refusal


def exam_before_material():
    p = pipeline(generator=RecordedGenerator({"outline": [copy.deepcopy(w.OUTLINE)]}))
    p.submit_brief(copy.deepcopy(w.BRIEF), AUTHOR)
    p.draft_outline(AUTHOR)
    p.machine.fire("OutlineApproved")
    try:
        p.generate_node(w.E1, AUTHOR)
    except MachineRefused as exc:
        return p.machine.current.nodes[w.E1].state, str(exc).split("datalog: ")[-1]
    return p.machine.current.nodes[w.E1].state, "was not refused"


def stale_node_at_publication():
    from scenarios.run import the_course
    p = the_course()
    m = p.machine
    m.fire("ReviseRequested", {"revision": 1})
    m.fire("NodeEdited", {"node": w.T2, "content": copy.deepcopy(w.CONTENT[w.T2])})
    out = p.membrane.request("publish_revision", {"actor": "admin-1", "revision": m.current.id},
                             {"id": "admin-1", "kind": "person"})
    return out.check, out.reason.split(";")[0]


def unregistered_action():
    twin = _twin("06-unregistered-action.yaml")["action"]
    p = pipeline()
    out = p.membrane.request(twin["name"], {}, {"id": twin["actor"], "kind": "person"})
    return out.check, out.reason


def injection_in_a_source():
    twin = _twin("07-injection-in-a-source.yaml")["chunk"]
    generator = RecordedGenerator({"outline": [copy.deepcopy(w.OUTLINE)]})
    p = pipeline(generator=generator)
    p.kb_chunks = cassette.KB_CHUNKS + [twin]
    p.machine.world.articles[0]["chunks"].append(twin["id"])
    try:
        p.submit_brief(copy.deepcopy(w.BRIEF), AUTHOR)
        p.draft_outline(AUTHOR)
    finally:
        p.machine.world.articles[0]["chunks"].remove(twin["id"])
    _, prompt = generator.asked[0]
    in_sources = any(twin["text"] in s for s in prompt.sources)
    in_instructions = twin["text"] in prompt.instructions or twin["text"] in prompt.author
    return ("sources" if in_sources and not in_instructions else "LEAKED INTO INSTRUCTIONS",
            p.machine.current.state)


TWIN_RUNS = [
    ("01 a forbidden topic in the brief", forbidden_topic, lambda r: r[0] == "BlockedFinal"),
    ("02 a brief that contradicts itself", contradictory_brief,
     lambda r: r == ("BlockedRecoverable", "brief")),
    ("03 a node citing a source its audience cannot see", restricted_source,
     lambda r: r[0] == "Validated" and "cannot see" in (r[1] or "")),
    ("04 an exam before its material", exam_before_material,
     lambda r: r[0] == "Planned" and "nobody has approved" in r[1]),
    ("05 a stale node at publication", stale_node_at_publication,
     lambda r: r[0] == "legal_in_state"),
    ("06 an action nobody registered", unregistered_action, lambda r: r[0] == "registered"),
    ("07 an instruction hidden in a source", injection_in_a_source,
     lambda r: r == ("sources", "OutlineReview")),
]


def run_twins() -> int:
    failures = 0
    for title, scene, holds in TWIN_RUNS:
        result = scene()
        ok = holds(result)
        failures += not ok
        print(f"  {'·' if ok else '✗'} {title}\n      {result}")
    print("\n  every twin stopped where it must" if not failures
          else f"\n  {failures} twin(s) did not stop where they must")
    return 1 if failures else 0
