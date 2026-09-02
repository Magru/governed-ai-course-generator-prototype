"""The provider development runs against.

Bedrock is what the specification names, and it is what the defence demonstrates.
This exists because a key for it was available first, and because having two
implementations behind one port is the only way to know the port is a port.
"""
from __future__ import annotations
import json, os, pathlib

from .port import Generated, Generator, Prompt, ProviderUnavailable


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


class GeminiGenerator(Generator):
    MODEL = "gemini-2.5-flash"

    def __init__(self) -> None:
        from google import genai
        self._client = genai.Client(api_key=_key())

    def generate(self, prompt: Prompt, schema: dict) -> Generated:
        """The three positions are handed to the API in the places it keeps
        apart: instructions go to the system field, the author's text is the
        turn, and sources are separate parts the model may read and may not
        obey. They are never joined into one string here."""
        from google.genai import types
        parts = [prompt.author] if prompt.author else []
        parts += [f"<source>{s}</source>" for s in prompt.sources]
        try:
            response = self._client.models.generate_content(
                model=self.MODEL,
                contents=parts or [""],
                config=types.GenerateContentConfig(
                    system_instruction=prompt.instructions,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
        except Exception as exc:                  # noqa: BLE001
            raise ProviderUnavailable(f"generation failed: {exc}") from exc
        usage = getattr(response, "usage_metadata", None)
        return Generated(
            content=json.loads(response.text),
            model_id=self.MODEL,
            usage={"total_tokens": getattr(usage, "total_token_count", 0)} if usage else {},
        )

    # No screen() here on purpose. This provider has no managed guardrail, and
    # a Screener is a separate port precisely so that Gemini can generate while
    # Bedrock screens. Approximating one here would be a weaker check wearing a
    # stronger one's name.
