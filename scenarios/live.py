"""The live run: Gemini writes, Bedrock Guardrails screens, the machine decides.

Two parts. First the guardrail alone, on three texts whose answers are known:
a lesson sentence it must allow, the forbidden-topic brief it must refuse by
topic, and a sentence carrying an email address it must refuse as personal data.
Then the course from its brief to its first node, through the same gateway as
`make run`, with the recordings replaced by the services.

Only through `make live-run`, which exports the variables that keep every call
in the prototype's own account; the provider module checks the account again
before the first call.
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from gateway.provider.bedrock import BedrockScreener  # noqa: E402
from scenarios import walkthrough as w  # noqa: E402
from scenarios.run import AUTHOR, pipeline  # noqa: E402
from scenarios.twins import _twin  # noqa: E402

KNOWN = [
    ("a lesson sentence", "Keep the bench clear of offcuts before you start a cut.", "brief-in", True, None),
    ("the forbidden-topic brief", None, "brief-in", False, "defeating-a-guard"),
    ("a sentence with an email address", "Send your incident form to alex.rivers@example.org today.",
     "node-out", False, "email"),
]


def known_answers(screener: BedrockScreener) -> int:
    forbidden = json.dumps(_twin("01-forbidden-topic.yaml")["brief"], sort_keys=True)
    wrong = 0
    for title, text, point, allowed, category in KNOWN:
        v = screener.screen(text or forbidden, "text", point)
        ok = v.allowed == allowed and (category is None or v.category == category)
        wrong += not ok
        said = "allow" if v.allowed else f"deny: {v.category}"
        print(f"  {'·' if ok else '✗'} {title:<34} {point:<10} {said:<24} version {v.guardrail_version}")
    return wrong


def course(screener: BedrockScreener) -> bool:
    """True when a node of the live course was written, screened and checked."""
    from gateway.provider.gemini import GeminiGenerator
    p = pipeline(generator=GeminiGenerator(), screener=screener)
    m = p.machine
    m.store.current["guardrail"] = screener.version      # the guardrail in force is the one deployed
    try:
        p.submit_brief(copy.deepcopy(w.BRIEF), AUTHOR)
        while m.current.state == "OutlineDrafting":
            p.draft_outline(AUTHOR)
        if m.current.state == "OutlineReview":
            m.fire("OutlineApproved", {"actor": AUTHOR["id"]})
            first = next(n for n, node in m.current.nodes.items() if node.spec.get("type") == "topic")
            p.generate_node(first, AUTHOR)
    finally:
        for number, name, subject, result in p.stages:
            print(f"  stage {number:>2} {name:<26} {subject:<22} {result}")
        nodes = {n: node.state for n, node in m.current.nodes.items()}
        print(f"\n  revision {m.current.id}: {m.current.state} · nodes {nodes}")
    return "Validated" in nodes.values()


def main() -> int:
    screener = BedrockScreener()
    print("the guardrail on three known answers")
    wrong = known_answers(screener)
    print("\nthe course, brief to first node, live")
    reached = course(screener)
    print("\n" + ("a node was written, screened and checked" if reached
                  else "the course did not reach a checked node"))
    return 1 if wrong or not reached else 0


if __name__ == "__main__":
    raise SystemExit(main())
