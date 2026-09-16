"""A provider that answers from a recording — the same run, every run.

Behind the same two ports as the live adapters, so the pipeline cannot tell
which it is talking to, and a demonstration that must not depend on the network
still goes through every stage a live run does.

A recording is not a default. A request the cassette has no answer for raises
the port's own "unavailable" exception — a missing verdict is an unknown, and
the table routes unknowns to recovery. Answering "allow" for anything
unrecorded would be a second guardrail that says yes to everything.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .port import (Generated, Generator, GuardrailUnavailable, Modality, Point, Prompt,
                   ProviderUnavailable, Screener, Verdict)


@dataclass
class RecordedGenerator(Generator):
    """Answers are queued per task: a repair asks the same task again and gets
    the next recording, the way a model given feedback returns something new."""
    answers: dict                              # task → list of content dicts, or "timeout"
    model_id: str = "recorded-model"
    asked: list = field(default_factory=list)

    def task(self, prompt: Prompt) -> str:
        return prompt.instructions.split("\n", 1)[0]

    def generate(self, prompt: Prompt, schema: dict) -> Generated:
        task = self.task(prompt)
        self.asked.append((task, prompt))
        queue = self.answers.get(task)
        if not queue:
            raise ProviderUnavailable(f"nothing recorded for {task!r}")
        answer = queue.pop(0)
        if answer == "timeout":
            raise ProviderUnavailable(f"{task}: the recorded call timed out")
        return Generated(content=answer, model_id=self.model_id, model_version="cassette")


@dataclass
class RecordedScreener(Screener):
    verdicts: dict                             # (point, subject) → list of "allow" · category · "unreachable"
    version: str = "guard-1"
    asked: list = field(default_factory=list)

    def screen(self, content: str, modality: Modality, point: Point, subject: str = "") -> Verdict:
        self.asked.append((point, subject, modality))
        queue = self.verdicts.get((point, subject))
        if not queue:
            raise GuardrailUnavailable(f"no screening recorded for {subject!r} at {point}")
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if answer == "unreachable":
            raise GuardrailUnavailable(f"{subject} at {point}: the recorded call did not answer")
        if answer == "allow":
            return Verdict(True, None, self.version, point)
        return Verdict(False, answer, self.version, point)
