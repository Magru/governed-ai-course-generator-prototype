"""What the generator asks of a provider, and nothing more.

Two shapes here matter more than the rest.

**A prompt is not a string.** The specification assembles it from three inputs
with different levels of trust and keeps them apart rather than concatenating
them — that separation *is* the defence. A port that accepted `prompt: str`
would force the caller to join them before the provider ever saw them, which is
the one thing the architecture forbids. So the port takes the parts.

**Generation and screening are separate ports.** The model provider and the
managed guardrail are different services with different owners, and development
runs one against the other: Gemini generates, Bedrock screens. Bundling them in
one interface made that combination impossible to express, and every live run
stalled at the first screening.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Protocol


class ProviderUnavailable(RuntimeError):
    """The service could not be reached. An unknown, never a permission."""


class GuardrailNotConfigured(RuntimeError):
    """No guardrail is configured at all — a deployment error, not a runtime one."""


class GuardrailUnavailable(RuntimeError):
    """A guardrail exists and did not answer. Held apart from the case above
    because one is fixed by configuration and the other by waiting or failing;
    the specification forbids reading either as a permissive verdict, so neither
    returns a value a caller could mistake for 'clean'."""


Modality = Literal["text", "image"]
Point = Literal["brief-in", "outline-out", "node-out", "image-prompt-out", "image-out"]


@dataclass(frozen=True)
class Prompt:
    """The three positions, kept apart. Only a provider adapter may join them,
    and it does so in the way its own API expects — a system field, a user turn,
    a documents block — never by string concatenation in our code."""
    instructions: str                     # trusted · ours. the phase's rules and schema
    author: str = ""                      # authorized · untrusted. emphasis, tone, depth
    sources: tuple[str, ...] = ()         # untrusted. retrieved, inert by position


@dataclass(frozen=True)
class Generated:
    """What came back, and enough provenance to stamp it. A bare dict lost the
    model identity that every approved artifact is supposed to carry."""
    content: dict
    model_id: str
    model_version: str = ""
    usage: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    category: str | None = None           # a category, never the matched string
    guardrail_version: str | None = None
    point: Point | None = None


class Generator(Protocol):
    def generate(self, prompt: Prompt, schema: dict) -> Generated:
        """Return a structure matching the schema. The model returns a structure
        because it was given a tool signature, not because it was asked nicely."""


class Screener(Protocol):
    def screen(self, content: str, modality: Modality, point: Point) -> Verdict:
        """Screen one artifact at one evaluation point. Raises rather than
        guessing: absence of a verdict is not a permissive verdict."""
