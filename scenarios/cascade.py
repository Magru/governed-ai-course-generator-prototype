"""`make cascade` — the staleness cascade at course scale, priced in both currencies.

`latency-budget.yaml` argues from a sum: re-verifying an unedited node costs its
checks, a hand-edited one the checks and the outbound guardrail, and every node
the cascade surfaces costs a person three minutes. This runs that argument on
courses larger than the walkthrough's four nodes.

The dependency closure is the real one — the Datalog rules the machine's
`depends_on` guard reads. Only the course is synthetic: modules of topics that
require the topic before them and sometimes an earlier one, refer back now and
then, and close with an exam over the module. The generator is seeded, so the
figures are the same on every run.

Three questions, each answered with numbers rather than asserted:
  1. an edit to one topic — how much of the course does it send back?
  2. a change that reaches the whole revision — what does re-verification cost?
  3. does the cascade settle when the edit's own repair fails and regenerates?
     Since spec-v2.9 a regeneration is an edit, so a failed repair withdraws any
     approval a dependent was given meanwhile. The repair budget bounds how often.
"""
from __future__ import annotations

import copy
import pathlib
import random
import statistics
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engines.datalog.structure import cascade                        # noqa: E402
from scenarios import walkthrough as w                               # noqa: E402
from scenarios.run import approve, the_course                        # noqa: E402

BUDGET = yaml.safe_load((ROOT / "model" / "latency-budget.yaml").read_text(encoding="utf-8"))

#: The stages an unedited node re-enters; a hand-edited one adds the outbound
#: guardrail. Named, not numbered, so the figures are read from the budget file.
CHECKS = ("schema — is the request well formed", "OPA — role, audience, limits, legal in state",
          "block schemas from the catalog", "grounding and rights — Datalog",
          "constraints and coverage — Z3, Prolog", "admission into course state", "audit append")
GUARDRAIL_OUT = "guardrail out — text and images"


def stage_ms(names) -> int:
    ms = {s["stage"]: s["ms"] for s in BUDGET["stages"]}
    return sum(ms[n] for n in names)


RECHECK_MS = stage_ms(CHECKS)
EDITED_MS = RECHECK_MS + stage_ms([GUARDRAIL_OUT])
REVIEW_S = BUDGET["capacity"]["think_time_s"]
REPAIR_FAILURE = BUDGET["repair_loop"]["assumed_first_pass_failure_rate"]
REPAIR_BUDGET = BUDGET["repair_loop"]["retry_budget"]


def course(topics: int, seed: int = 7, per_module: int = 8) -> list[dict]:
    """A course of modules, each closed by an exam over its topics."""
    rng = random.Random(seed)
    nodes, made = [], []
    for module in range((topics + per_module - 1) // per_module):
        this = []
        for _ in range(per_module):
            if len(made) == topics:
                break
            node = f"t{len(made):03d}"
            requires = {this[-1]} if this and rng.random() < 0.7 else set()
            if len(made) > 1 and rng.random() < 0.3:
                requires.add(rng.choice(made[:-1]))
            refers = [rng.choice(made)] if made and rng.random() < 0.2 else []
            nodes.append({"id": node, "requires": sorted(requires), "refers_to": refers})
            this.append(node)
            made.append(node)
        nodes.append({"id": f"e{module:02d}", "topics": this})
    return nodes


def one_edit(nodes: list[dict], sample: int | None = None, seed: int = 7) -> dict:
    topics = [n["id"] for n in nodes if not n["id"].startswith("e")]
    edited = random.Random(seed).sample(topics, sample) if sample else topics
    reached = [len(cascade(nodes, t)) for t in edited]
    share = [r / (len(nodes) - 1) for r in reached]
    return {"nodes": len(nodes), "edits": len(edited), "mean": statistics.mean(reached),
            "max": max(reached), "mean_share": statistics.mean(share), "max_share": max(share),
            "compute_s": (EDITED_MS + statistics.mean(reached) * RECHECK_MS) / 1000,
            "review_h": statistics.mean(reached) * REVIEW_S / 3600}


def whole_revision(nodes: list[dict]) -> dict:
    return {"nodes": len(nodes), "compute_s": len(nodes) * RECHECK_MS / 1000,
            "review_h": len(nodes) * REVIEW_S / 3600}


def settling_on_the_machine(approve_between: bool, failures: int = REPAIR_BUDGET) -> dict:
    """The walkthrough course on the real machine: a topic is edited, its new
    content is refused `failures` times and regenerated each time.

    The cascade withdraws approvals; it does not chase nodes that hold none. So
    the exam that tests the topic goes back once per approval it was given in
    the meantime — once if nobody approves it during the repair, once per landing
    if someone approves it after each. Either way a re-checked exam lands no
    content, so it starts no wave of its own."""
    p = the_course()
    m = p.machine
    m.fire("ReviseRequested", {"revision": 1})
    start = len(m.store.steps)
    edit = copy.deepcopy(w.CONTENT[w.T2])
    edit["blocks"][0]["text"] = "an edit that will need repair"
    m.fire("NodeEdited", {"node": w.T2, "content": edit})
    for attempt in range(failures):
        m.fire("GuardrailVerdict", {"node": w.T2, "verdict": "deny", "category": "unsafe"})
        if approve_between:
            approve(p, w.E1)
        regenerated = copy.deepcopy(w.CONTENT[w.T2]) | {"minutes": 19 - attempt}
        m.fire("NodeGenerated", {"node": w.T2, "content": regenerated,
                                 "idempotency_key": f"repair-{attempt}"})
    back, last = 0, None
    for step in m.store.steps[start:]:
        if step["revision"] == m.current.id:
            state = step["node_states"].get(w.E1)
            back += state == "NeedsRevalidation" and last != state
            last = state
    m.fire("GuardrailVerdict", {"node": w.T2, "verdict": "allow"})
    approve(p, w.T2)
    approve(p, w.E1)
    return {"landings": 1 + failures, "sent_back": back, "settled_in": m.current.state,
            "expected": 1 + failures if approve_between else 1}


def settling_at_scale(nodes: list[dict]) -> dict:
    """What the machine's behaviour costs on a larger course: each landing sends
    the same dependents back, and landings per edit are bounded by the budget."""
    topics = [n["id"] for n in nodes if not n["id"].startswith("e")]
    reached = statistics.mean(len(cascade(nodes, t)) for t in topics)
    landings = sum(REPAIR_FAILURE ** k for k in range(REPAIR_BUDGET + 1))
    return {"reached": reached, "expected_landings": landings,
            "expected_rechecks": reached * landings, "worst_rechecks": reached * (REPAIR_BUDGET + 1)}


def main() -> int:
    print(f"  re-verify an unedited node {RECHECK_MS} ms · a hand-edited one {EDITED_MS} ms · "
          f"review {REVIEW_S} s  (from latency-budget.yaml)\n")
    print("  one edit to a topic, every topic tried in turn")
    for topics in (24, 96, 240):
        r = one_edit(course(topics), sample=None if topics < 240 else 60)
        print(f"    {r['nodes']:>4} nodes: sends back {r['mean']:5.1f} on average "
              f"({r['mean_share']:.0%}), {r['max']} at most ({r['max_share']:.0%}) · "
              f"{r['compute_s']:.1f} s compute · {r['review_h']:.1f} h of review")
    print("\n  a change that reaches the whole revision (policy, catalog, knowledge base)")
    for size in (100, 500):
        r = whole_revision([{}] * size)
        print(f"    {size:>4} nodes: {r['compute_s']:.0f} s compute · {r['review_h']:.0f} h of review "
              f"if every one goes to a person")
    print(f"\n  does it settle — the machine, a topic whose repair fails {REPAIR_BUDGET} times")
    ok = True
    for between in (False, True):
        s = settling_on_the_machine(between)
        holds = s["sent_back"] == s["expected"] and s["settled_in"] == "ReadyForReview"
        ok &= holds
        print(f"    {'the exam approved after each failure' if between else 'nobody approves the exam meanwhile':<38}"
              f" {s['landings']} landings · exam sent back {s['sent_back']} · settles in {s['settled_in']}"
              f"{'' if holds else '  ✗ expected ' + str(s['expected'])}")
    a = settling_at_scale(course(96))
    print(f"    at {len(course(96))} nodes, repair failing {REPAIR_FAILURE:.0%}: {a['expected_landings']:.2f} "
          f"landings per edit · {a['reached']:.1f} re-checks if nobody approves meanwhile, "
          f"{a['worst_rechecks']:.0f} at worst")
    print("    " + ("it settles: the cascade withdraws approvals and a re-checked dependent lands no "
                    "content, so only the edited node makes waves and the repair budget bounds them"
                    if ok else "IT DOES NOT SETTLE"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
