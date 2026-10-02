"""What Gemini is asked to return is a schema Gemini accepts.

The SDK refuses keywords outside its subset on the client, before any request,
and the adapter can only read that as an outage — so a schema it cannot send
would spend a node's retries on a fault no retry fixes.
"""
from __future__ import annotations

import pytest

from engines.schema.schemas import OUTLINE
from gateway.pipeline import NODE_SCHEMA

genai = pytest.importorskip("google.genai")


def _walk(schema, path="$"):
    yield path, schema
    for name, sub in (schema.get("properties") or {}).items():
        yield from _walk(sub, f"{path}.{name}")
    if isinstance(schema.get("items"), dict):
        yield from _walk(schema["items"], f"{path}[]")


@pytest.mark.parametrize("name, schema", [("outline", OUTLINE), ("node", NODE_SCHEMA)])
def test_the_sdk_accepts_the_schema_it_is_sent(name, schema):
    from google.genai import _transformers
    from gateway.provider.gemini import for_gemini
    assert _transformers.t_schema(None, for_gemini(schema)) is not None


@pytest.mark.parametrize("name, schema", [("outline", OUTLINE), ("node", NODE_SCHEMA)])
def test_every_array_says_what_it_holds_and_every_object_what_it_carries(name, schema):
    from gateway.provider.gemini import for_gemini
    for path, node in _walk(for_gemini(schema)):
        if node.get("type") == "array":
            assert isinstance(node.get("items"), dict), path
        if node.get("type") == "object":
            assert node.get("properties"), path


def test_the_full_schema_is_kept_for_the_checks_that_follow():
    from gateway.provider.gemini import for_gemini
    assert "not" in OUTLINE["properties"]["nodes"]["items"]["properties"]["id"]
    assert "not" not in for_gemini(OUTLINE)["properties"]["nodes"]["items"]["properties"]["id"]


def test_an_enum_is_sent_with_its_type_or_gemini_does_not_hold_the_model_to_it():
    from gateway.provider.gemini import for_gemini
    kind = for_gemini(OUTLINE)["properties"]["nodes"]["items"]["properties"]["type"]
    assert kind == {"type": "string", "enum": ["topic", "exam"]}


def test_the_model_is_told_the_catalogs_skills_and_blocks_and_held_to_them():
    from gateway.asking import node_request, outline_request
    from machine.world import load
    world = load()
    rules, schema = outline_request(world)
    assert "outline" == rules.split("\n", 1)[0] and "bench-safety" in rules
    assert schema["properties"]["nodes"]["items"]["properties"]["skill"]["enum"] == world.skills
    rules, schema = node_request(world, "mt-node-201")
    assert rules.split("\n", 1)[0] == "node:mt-node-201" and "quiz (question, options, answer, points)" in rules
    assert schema["properties"]["blocks"]["items"]["properties"]["type"]["enum"] == world.block_types


class _Unreadable:
    """Stands where Google's API does, and answers with something unreadable."""

    def __init__(self, error):
        from types import SimpleNamespace
        self.error = error
        self.models = SimpleNamespace(generate_content=self.generate_content)

    def generate_content(self, **_):
        if isinstance(self.error, Exception):
            raise self.error
        from types import SimpleNamespace
        return SimpleNamespace(text=self.error, usage_metadata=None)


@pytest.mark.parametrize("error, kind", [
    (ValueError("Exceeds the limit (4300 digits) for integer string conversion"), "MalformedAnswer"),
    ("{not json", "MalformedAnswer"),
    (ConnectionError("reset by peer"), "ProviderUnavailable"),
])
def test_an_answer_that_cannot_be_read_is_a_model_fault_not_an_outage(monkeypatch, error, kind):
    from gateway.provider import gemini
    from gateway.provider.port import Prompt
    monkeypatch.setenv("GEMINI_API_KEY", "canary-gemini-0000")
    generator = gemini.GeminiGenerator()
    generator._client = _Unreadable(error)
    with pytest.raises(Exception) as raised:
        generator.generate(Prompt("node:x"), NODE_SCHEMA)
    assert type(raised.value).__name__ == kind


def test_the_gateway_reads_an_unreadable_answer_as_a_model_error():
    import copy
    from gateway.provider.port import MalformedAnswer
    from scenarios import run, walkthrough as w

    class Unreadable:
        model_id = "unreadable"
        asked = []

        def generate(self, prompt, schema):
            raise MalformedAnswer("a number thousands of digits long")

    p = run.pipeline(generator=Unreadable())
    p.submit_brief(copy.deepcopy(w.BRIEF), run.AUTHOR)
    p.draft_outline(run.AUTHOR)
    events = [s["event"] for s in p.machine.store.steps]
    assert "ModelError" in events and "Timeout" not in events
