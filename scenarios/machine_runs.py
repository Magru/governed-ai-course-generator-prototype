"""Runs driven through the machine rather than written as traces.

`legal_run.py` writes a trace by hand, so the temporal checks can be tested
against a run nobody had to execute. This module is the other half: the same
course, fed as events to the machine built from the tables, with every
formal engine answering at the transitions the tables put it on. The trace
comes out of the store. If the two ever disagree about what is legal, one of
them is wrong about the model.

Generation is not called here. The content below is what a provider returned
once — recorded, so a run is the same run every time.
"""
from __future__ import annotations

import copy
import pathlib

import yaml

from machine import world as world_module
from machine.machine import Machine

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIEF = yaml.safe_load((ROOT / "fixtures" / "brief.yaml").read_text())["brief"]
N1, N2, EXAM = (n["id"] for n in BRIEF["nodes"])
OUTLINE = {"nodes": [dict(n) for n in BRIEF["nodes"]]}

CONTENT = {
    N1: {"blocks": [{"type": "paragraph", "text": "keep the bench clear of offcuts",
                     "cites": ["mt-kb-001"]}],
         "cites": ["mt-kb-001"], "minutes": 20},
    N2: {"blocks": [{"type": "paragraph", "text": "check a tool before every use",
                     "cites": ["mt-kb-002"]}],
         "cites": ["mt-kb-002"], "minutes": 20},
    EXAM: {"blocks": [{"type": "quiz", "question": "when is a tool checked",
                       "options": ["before every use", "once a year"], "answer": 0,
                       "points": 10}],
           "questions": [{"points": 10}], "points_total": 10, "minutes": 20, "cites": []},
}
SIGNATURES = [{"actor": "admin-1", "role": "training-administrator"},
              {"actor": "compliance-1", "role": "compliance-officer"}]


def machine(**config) -> Machine:
    world = world_module.load()
    return Machine(world, {"thresholds": world.thresholds, "author": "author-1", **config})


def brief(**changes) -> dict:
    return {**copy.deepcopy(BRIEF), **changes}


def to_outline_review(m: Machine, the_brief: dict | None = None, outline: dict | None = None):
    m.fire("BriefSubmitted", {"brief": the_brief or brief()})
    m.fire("GuardrailVerdict", {"verdict": "allow", "artifact": "brief"})
    m.fire("OutlineGenerated", {"outline": outline or copy.deepcopy(OUTLINE)})
    m.fire("GuardrailVerdict", {"verdict": "allow", "artifact": "outline"})


def to_content(m: Machine) -> None:
    to_outline_review(m)
    m.fire("OutlineApproved", {"outline": copy.deepcopy(OUTLINE)})


def node_through(m: Machine, node: str, content: dict | None = None) -> None:
    m.fire("NodeGenerationRequested", {"node": node})
    m.fire("NodeGenerated", {"node": node, "content": content or copy.deepcopy(CONTENT[node])})
    m.fire("GuardrailVerdict", {"verdict": "allow", "artifact": node, "node": node})


def to_published(m: Machine) -> None:
    to_content(m)
    for node in (N1, N2, EXAM):
        node_through(m, node)
        m.fire("NodeApproved", {"node": node, "actor": "author-1"})
    m.fire("CourseChecksRequested")
    m.fire("ApprovalGranted", {"signatures": SIGNATURES})
    m.fire("PublishRequested")
    m.fire("LearnersNotified", {"actor": "admin-1", "notice_screening": {
        "verdict": "allow", "guardrail_version": m.store.current["guardrail"]}})


def happy_path() -> Machine:
    m = machine()
    to_published(m)
    return m
