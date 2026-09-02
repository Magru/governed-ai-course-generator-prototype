"""What the generator asks of a model provider, and nothing more.

Two implementations exist: Gemini, which is what development runs against, and
Bedrock, which is what the specification names. The point of the port is that
neither can widen the question — a provider answers `generate` and `screen`, and
the architecture decides everything else.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol


class ProviderUnavailable(RuntimeError):
    """The provider could not be reached. An unknown, never a permission."""


class GuardrailUnavailable(RuntimeError):
    """No verdict was obtained. The specification is explicit that the absence of
    a verdict is not a permissive verdict, so this is raised rather than returned
    — there is no value a caller could mistake for 'clean'."""


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    category: str | None = None   # a category, never the matched string
    version: str | None = None    # the guardrail version that judged it


class Provider(Protocol):
    def generate(self, prompt: str, schema: dict) -> dict:
        """Return a structure matching the schema. The model is given a tool
        signature; it does not return a structure because it was asked nicely."""

    def screen(self, text: str) -> Verdict:
        """Screen an artifact. Raises GuardrailUnavailable rather than guessing."""
