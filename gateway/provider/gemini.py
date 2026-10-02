"""The provider development runs against.

Bedrock is what the specification names, and it is what the defence demonstrates.
This exists because a key for it was available first, and because having two
implementations behind one port is the only way to know the port is a port.
"""
from __future__ import annotations
import json, os, pathlib

from .port import Generated, Generator, MalformedAnswer, Prompt, ProviderUnavailable


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


#: The part of JSON Schema Gemini's response_schema accepts. The rest — `not`,
#: `pattern`, `minLength`, closed objects — is not lost: the machine validates
#: every answer against the full schema at its checks, and a failure there is a
#: repair with a reason. Sending them would be refused on the client, before any
#: request, and read as an outage.
GEMINI_KEYWORDS = {"type", "properties", "required", "items", "enum", "description", "minItems",
                   "maxItems", "nullable", "format", "minimum", "maximum", "anyOf", "title"}


def for_gemini(schema):
    """The schema in the subset Gemini accepts, recursively."""
    if isinstance(schema, list):
        return [for_gemini(s) for s in schema]
    if not isinstance(schema, dict):
        return schema
    out = {k: for_gemini(v) for k, v in schema.items() if k in GEMINI_KEYWORDS and k != "properties"}
    if "enum" in out and "type" not in out:
        # An enum with no type is not read as a constraint by Gemini.
        out["type"] = "string"
    if "properties" in schema:
        out["properties"] = {name: for_gemini(sub) for name, sub in schema["properties"].items()}
    return out


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
                    response_schema=for_gemini(schema),
                    # Generation only; nothing here may become a call.
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
        except ValueError as exc:
            # The SDK parses the answer against the schema inside the call. A
            # parse that fails is an answer that cannot be read — a number
            # thousands of digits long, a string where an object belongs.
            raise MalformedAnswer(f"the answer could not be read: {exc}") from exc
        except Exception as exc:                  # noqa: BLE001
            raise ProviderUnavailable(f"generation failed: {exc}") from exc
        try:
            content = json.loads(response.text)
        except (TypeError, ValueError) as exc:
            raise MalformedAnswer(f"the answer is not JSON: {exc}") from exc
        usage = getattr(response, "usage_metadata", None)
        return Generated(
            content=content,
            model_id=self.MODEL,
            usage={"total_tokens": getattr(usage, "total_token_count", 0)} if usage else {},
        )

    # No screen() here on purpose. This provider has no managed guardrail, and
    # a Screener is a separate port precisely so that Gemini can generate while
    # Bedrock screens. Approximating one here would be a weaker check wearing a
    # stronger one's name.
