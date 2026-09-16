"""What the providers answered once, recorded, for the end-to-end run.

Generation answers are queued per task, so a repair or a retry receives the
next recording. Screening verdicts are keyed by evaluation point and subject.
Nothing is defaulted: a call the cassette does not cover is unavailable, and the
run shows the table's recovery rows rather than an invented answer.
"""
from __future__ import annotations

import copy
import pathlib

import yaml

from gateway.provider.recorded import RecordedGenerator, RecordedScreener
from scenarios import walkthrough as w

ROOT = pathlib.Path(__file__).resolve().parents[1]
KB_CHUNKS = yaml.safe_load((ROOT / "fixtures" / "kb.yaml").read_text())["knowledge_base"]["chunks"]


def leaking(node: str, in_block: bool = False) -> dict:
    """Content citing incident records, which only supervisors may see — at the
    node's own list, or only inside a block while the node declares a harmless
    source."""
    content = copy.deepcopy(w.CONTENT[node])
    if in_block:
        content["blocks"][0]["cites"] = ["mt-kb-008"]
    else:
        content["cites"] = ["mt-kb-008"]
    return content


def course_generator() -> RecordedGenerator:
    """The walkthrough's model calls: an outline with an invented skill and its
    repair, three topics — one citing a source its audience cannot see, one
    timing out — and the exam, whose first answer is an empty object."""
    return RecordedGenerator({
        "outline": [copy.deepcopy(w.INVENTED), copy.deepcopy(w.OUTLINE)],
        f"node:{w.T1}": [copy.deepcopy(w.CONTENT[w.T1])],
        f"node:{w.T2}": [leaking(w.T2), copy.deepcopy(w.CONTENT[w.T2])],
        f"node:{w.T3}": ["timeout", copy.deepcopy(w.CONTENT[w.T3])],
        f"node:{w.E1}": [{}, copy.deepcopy(w.CONTENT[w.E1])],
    })


def course_screener() -> RecordedScreener:
    """One answer per screening the run makes, and no more. The outline and the
    exam are screened twice because their first answer was repaired. Topic two
    is too, but not for its repair — the leaking draft differed from its repair
    only in citations, which are not screened text, so the same text was not
    screened twice; its second screening is the edit after publication. The
    published revision is screened when it is verified again after the
    rollback, not again for the policy change that leaves text and guardrail as
    they were, and once more when the guardrail itself changes."""
    allow = lambda times: ["allow"] * times
    return RecordedScreener({
        ("brief-in", "brief"): allow(1),
        ("outline-out", "outline"): allow(2),
        ("image-out", f"{w.T1}.blocks[1]"): allow(1),
        ("node-out", w.T1): allow(1),
        ("node-out", w.T2): allow(2),
        ("node-out", w.T3): allow(1),
        ("node-out", w.E1): allow(2),
        ("revision", "revision-1"): allow(2),
        ("notice-out", "notice:revision-1"): allow(1),
    })
