"""What every engine owes its caller.

One rule shapes all five: **a layer that returns false is a layer that has
failed.** Every refusal carries an artifact — an unsat core, a leak path, a
proof tree, a named rule — because that is what a person acts on, what the
repair loop feeds into the next prompt, and what an auditor reads six months
later. The verdict is the cheap part.

The second rule is what happens when an engine cannot run. It raises. It never
returns a permissive verdict, and there is no fallback path that quietly
evaluates the same rules in Python: the reference implementation this project
started from had exactly that, and it means "real OPA" stops being provable at
runtime. If a formal engine cannot run, the deployment is broken, and the honest
response is to stop admitting work rather than admit it unchecked.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


class EngineUnavailable(RuntimeError):
    """The engine could not run. Never a pass, never a fallback."""


class RefusalWithoutArtifact(AssertionError):
    """An engine said no and gave nothing to act on. A bug in the engine."""


@dataclass(frozen=True)
class Refusal:
    """What a person, a repair loop and an auditor each need from a no."""
    kind: str                       # unsat-core · leak-path · proof-tree · named-rule · …
    summary: str                    # one line a human reads first
    detail: Any = None              # the structure the repair loop consumes
    engine: str = ""

    def __str__(self) -> str:       # what shows up in a trace
        return f"{self.engine}: {self.summary}"


@dataclass(frozen=True)
class Verdict:
    ok: bool
    refusal: Refusal | None = None
    facts: dict = field(default_factory=dict)     # what the engine established

    def __post_init__(self) -> None:
        if not self.ok and self.refusal is None:
            raise RefusalWithoutArtifact(
                "a refusal must carry an artifact; a bare false is useless to "
                "the person who has to act next")


def allowed(**facts: Any) -> Verdict:
    return Verdict(ok=True, facts=facts)


def refused(kind: str, summary: str, detail: Any = None, engine: str = "") -> Verdict:
    return Verdict(ok=False, refusal=Refusal(kind, summary, detail, engine))
