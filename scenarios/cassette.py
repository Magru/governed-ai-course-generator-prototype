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


def leaking(node: str) -> dict:
    content = copy.deepcopy(w.CONTENT[node])
    content["cites"] = ["mt-kb-008"]                  # incident records: supervisors only
    return content


def course_generator() -> RecordedGenerator:
    """The walkthrough's model calls: an outline with an invented skill and its
    repair, three topics — one citing a source its audience cannot see, one
    timing out — and the exam."""
    return RecordedGenerator({
        "outline": [copy.deepcopy(w.INVENTED), copy.deepcopy(w.OUTLINE)],
        f"node:{w.T1}": [copy.deepcopy(w.CONTENT[w.T1])],
        f"node:{w.T2}": [leaking(w.T2), copy.deepcopy(w.CONTENT[w.T2])],
        f"node:{w.T3}": ["timeout", copy.deepcopy(w.CONTENT[w.T3])],
        f"node:{w.E1}": [copy.deepcopy(w.CONTENT[w.E1])],
    })


def course_screener() -> RecordedScreener:
    allow = ["allow"]
    verdicts = {("brief-in", "brief"): allow, ("outline-out", "outline"): allow,
                ("image-out", f"{w.T1}.blocks[1]"): allow}
    for node in (w.T1, w.T2, w.T3, w.E1):
        verdicts[("node-out", node)] = allow
    for rev in (1, 2):
        verdicts[("revision", f"revision-{rev}")] = allow
    return RecordedScreener(verdicts)
