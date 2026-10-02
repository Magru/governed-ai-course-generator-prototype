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
