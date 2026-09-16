"""walkthrough.html, as beats the machine must reproduce.

The page follows one course through twenty-four steps. The course here is the
invented organisation's, with the page's shape kept: three topics and an exam,
one outline repair, an illustration a person must look at, one timeout, an exam
fenced until its topics are approved, and a publication. Beat labels are the
page's step numbers, so a mismatch reads as "step 16 diverged".

The page runs the brief's three checks as one step; the tables make the
guardrail's answer an event of its own. Where the two differ in granularity
the tables win, because the tables are what the machine is built from.
"""
from __future__ import annotations

import copy
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scenarios.machine_runs import SIGNATURES, brief, machine   # noqa: E402
from scenarios.replay import Beat, play                          # noqa: E402

T1, T2, T3, E1 = "mt-node-201", "mt-node-202", "mt-node-203", "mt-node-204"

BRIEF = brief(id="mt-course-200", title="Workshop hygiene for apprentices",
              objectives=["bench-safety", "tool-inspection", "dust-extraction"],
              nodes=[{"id": T1, "type": "topic", "skill": "bench-safety"},
                     {"id": T2, "type": "topic", "skill": "tool-inspection"},
                     {"id": T3, "type": "topic", "skill": "dust-extraction"},
                     {"id": E1, "type": "exam", "topics": [T1, T2, T3]}])
OUTLINE = {"nodes": copy.deepcopy(BRIEF["nodes"])}
INVENTED = copy.deepcopy(OUTLINE)
INVENTED["nodes"][2]["skill"] = "post-mortem-facilitation"


def _topic(chunk: str, text: str, image: bool = False) -> dict:
    blocks = [{"type": "paragraph", "text": text, "cites": [chunk]}]
    if image:
        blocks.append({"type": "image", "src": "bench.png", "alt": "a clear bench",
                       "caption": "a bench ready for work", "cites": [chunk]})
    return {"blocks": blocks, "cites": [chunk], "minutes": 20}


CONTENT = {
    T1: _topic("mt-kb-001", "keep the bench clear of offcuts", image=True),
    T2: _topic("mt-kb-002", "check a tool for splits before every use"),
    T3: _topic("mt-kb-005", "connect extraction before cutting"),
    E1: {"blocks": [{"type": "quiz", "question": "when is extraction connected",
                     "options": ["before cutting", "after cutting"], "answer": 0, "points": 5},
                    {"type": "quiz", "question": "when is a tool checked",
                     "options": ["before every use", "once a year"], "answer": 0, "points": 5}],
         "questions": [{"points": 5}, {"points": 5}], "points_total": 10, "minutes": 20,
         "cites": []},
}


def _generate(node: str, label: str) -> list[Beat]:
    return [
        Beat(f"{label}·request", "NodeGenerationRequested", {"node": node},
             nodes={node: "ContentDrafting"}),
        Beat(f"{label}·generated", "NodeGenerated",
             {"node": node, "content": copy.deepcopy(CONTENT[node])},
             nodes={node: "OutputGuardrail"}),
        Beat(f"{label}·screened", "GuardrailVerdict",
             {"verdict": "allow", "artifact": node, "node": node}, nodes={node: "Validated"}),
    ]


def _approve(node: str, label: str, **payload) -> Beat:
    return Beat(label, "NodeApproved", {"node": node, "actor": "author-1", **payload},
                nodes={node: "NodeApproved"})


def beats() -> list[Beat]:
    repaired = ("the repair raised the counter once", lambda m: m.current.repair_count == 1)
    return [
        Beat("2", "BriefSubmitted", {"brief": copy.deepcopy(BRIEF)}, course="BriefValidation",
             check=(("policy and guardrail versions stamped",
                     lambda m: set(m.current.stamps) == {"policy", "guardrail"}),)),
        Beat("3–4", "GuardrailVerdict", {"verdict": "allow", "artifact": "brief"},
             course="OutlineDrafting"),
        Beat("5", "OutlineGenerated", {"outline": copy.deepcopy(INVENTED)}, course="OutlineGuardrail"),
        Beat("6–7", "GuardrailVerdict", {"verdict": "allow", "artifact": "outline"},
             course="OutlineDrafting", check=(repaired,)),
        Beat("7·model call #2", "OutlineGenerated", {"outline": copy.deepcopy(OUTLINE)},
             course="OutlineGuardrail"),
        Beat("8", "GuardrailVerdict", {"verdict": "allow", "artifact": "outline"},
             course="OutlineReview"),
        Beat("9", "OutlineApproved", {"outline": copy.deepcopy(OUTLINE)}, course="ContentInProgress",
             nodes={T1: "Planned", T2: "Planned", T3: "Planned", E1: "Planned"}),
        *_generate(T1, "10–13"),
        Beat("14·unreviewed visual", "NodeApproved", {"node": T1, "actor": "author-1"},
             refused="all_visuals_reviewed(node) does not hold"),
        _approve(T1, "14", visuals_reviewed=[f"{T1}.blocks[1]"],
                 what_was_shown="formal verdict and one illustration"),
        *_generate(T2, "15"),
        _approve(T2, "15·approved"),
        Beat("16·request", "NodeGenerationRequested", {"node": T3}, nodes={T3: "ContentDrafting"}),
        Beat("16", "Timeout", {"node": T3}, nodes={T3: "ContentDrafting"},
             check=(("one bounded retry was spent", lambda m: m.current.nodes[T3].repair_count == 1),)),
        Beat("17·generated", "NodeGenerated", {"node": T3, "content": copy.deepcopy(CONTENT[T3])},
             nodes={T3: "OutputGuardrail"}),
        Beat("17·screened", "GuardrailVerdict", {"verdict": "allow", "artifact": T3, "node": T3},
             nodes={T3: "Validated"}),
        Beat("18·fenced", "NodeGenerationRequested", {"node": E1},
             refused="the exam tests material nobody has approved"),
        _approve(T3, "17"),
        *_generate(E1, "18–19"),
        Beat("20–21", "NodeApproved", {"node": E1, "actor": "author-1"},
             course="ReadyForReview", nodes={E1: "NodeApproved"}),
        Beat("22", "CourseChecksRequested", course="PendingApproval"),
        Beat("23", "ApprovalGranted", {"signatures": SIGNATURES}, course="Approved"),
        Beat("24", "PublishRequested", course="Published",
             check=(("the pointer moved to the published revision",
                     lambda m: m.store.live_pointer == m.current.id),)),
    ]


def run():
    m = machine()
    return m, play(m, beats())


if __name__ == "__main__":
    _, result = run()
    print(result.report())
    raise SystemExit(0 if result.ok and result.ltl.ok else 1)
