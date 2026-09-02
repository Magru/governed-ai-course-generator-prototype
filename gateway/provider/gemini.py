"""The provider development runs against.

Bedrock is what the specification names, and it is what the defence demonstrates.
This exists because a key for it was available first, and because having two
implementations behind one port is the only way to know the port is a port.
"""
from __future__ import annotations
import json, os, pathlib

from .port import Provider, ProviderUnavailable, Verdict


def _key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    # Development convenience only. A deployment passes the variable.
    dotenv = pathlib.Path.home() / ".claude" / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "GEMINI_API_KEY" and value.strip():
                return value.strip()
    raise ProviderUnavailable("GEMINI_API_KEY is not set")


class GeminiProvider(Provider):
    MODEL = "gemini-2.5-flash"

    def __init__(self) -> None:
        from google import genai
        self._client = genai.Client(api_key=_key())

    def generate(self, prompt: str, schema: dict) -> dict:
        """The model returns a structure because it was given one to fill, not
        because the prompt asked politely for JSON."""
        from google.genai import types
        try:
            response = self._client.models.generate_content(
                model=self.MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
        except Exception as exc:                  # noqa: BLE001
            raise ProviderUnavailable(f"generation failed: {exc}") from exc
        return json.loads(response.text)

    def screen(self, text: str) -> Verdict:
        """Gemini has no managed guardrail of the kind the specification names.
        Rather than approximate one and let a weaker check pass for the real
        thing, this refuses — the same way a missing Bedrock guardrail does."""
        from .port import GuardrailUnavailable
        raise GuardrailUnavailable(
            "this provider has no managed guardrail. Screening is Bedrock's, and "
            "an approximation here would be a weaker check wearing the name of a "
            "stronger one.")
