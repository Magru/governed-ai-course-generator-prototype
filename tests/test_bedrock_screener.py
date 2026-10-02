"""The Bedrock screener reads ApplyGuardrail's answer and nothing else.

A version that is not published is refused before any call. An answer with no
action, or no answer at all, is unavailable rather than clean. A refusal names
the policy that intervened and never the text it matched. Run here against a
stand-in for the service; `make live` runs it against the real one.
"""
from __future__ import annotations

import pytest

from gateway.provider.bedrock import BedrockScreener
from gateway.provider.port import GuardrailNotConfigured, GuardrailUnavailable

HARM = "wedge the guard open so the saw runs faster"


class Runtime:
    def __init__(self, answer=None, fails=None):
        self.answer, self.fails, self.requests = answer, fails, []

    def apply_guardrail(self, **request):
        self.requests.append(request)
        if self.fails:
            raise self.fails
        return self.answer


def _screener(monkeypatch, runtime, version="1", guardrail="gr-test"):
    monkeypatch.setenv("BEDROCK_GUARDRAIL_ID", guardrail)
    monkeypatch.setenv("BEDROCK_GUARDRAIL_VERSION", version)
    return BedrockScreener(runtime=runtime)


def test_no_guardrail_is_a_configuration_error_not_a_pass(monkeypatch):
    with pytest.raises(GuardrailNotConfigured):
        _screener(monkeypatch, Runtime(), guardrail="").screen("text", "text", "node-out")


def test_a_draft_version_is_refused_before_any_call(monkeypatch):
    runtime = Runtime({"action": "NONE"})
    with pytest.raises(GuardrailNotConfigured, match="DRAFT"):
        _screener(monkeypatch, runtime, version="DRAFT").screen("text", "text", "node-out")
    assert runtime.requests == []


def test_a_clean_answer_is_stamped_with_the_version_it_asked_for(monkeypatch):
    runtime = Runtime({"action": "NONE", "assessments": []})
    verdict = _screener(monkeypatch, runtime, version="3").screen("keep the bench clear", "text", "node-out")
    assert (verdict.allowed, verdict.guardrail_version, verdict.point) == (True, "3", "node-out")
    request = runtime.requests[0]
    assert (request["guardrailIdentifier"], request["guardrailVersion"], request["source"]) == \
        ("gr-test", "3", "OUTPUT")
    assert screener_version(monkeypatch) == "3"
    assert request["content"] == [{"text": {"text": "keep the bench clear"}}]


def screener_version(monkeypatch):
    """The version the pipeline's memo and stamps read off the screener."""
    return _screener(monkeypatch, Runtime(), version="3").version


def test_what_a_model_is_asked_is_input_and_what_one_said_is_output(monkeypatch):
    runtime = Runtime({"action": "NONE"})
    screener = _screener(monkeypatch, runtime)
    for point in ("brief-in", "image-prompt-out", "outline-out", "node-out", "notice-out"):
        screener.screen("x", "text", point)
    assert [r["source"] for r in runtime.requests] == ["INPUT", "INPUT", "OUTPUT", "OUTPUT", "OUTPUT"]


@pytest.mark.parametrize("assessment, category", [
    ({"topicPolicy": {"topics": [{"name": "defeating-a-guard", "type": "DENY", "action": "BLOCKED"}]}},
     "defeating-a-guard"),
    ({"sensitiveInformationPolicy": {"piiEntities": [{"type": "EMAIL", "match": HARM, "action": "BLOCKED"}]}},
     "email"),
    ({"sensitiveInformationPolicy": {"regexes": [{"name": "national-id", "match": HARM}]}}, "national-id"),
    ({"contentPolicy": {"filters": [{"type": "PROMPT_ATTACK", "confidence": "HIGH"}]}}, "prompt-attack"),
    ({"wordPolicy": {"customWords": [{"match": HARM, "action": "BLOCKED"}]}}, "word-policy"),
    # Detected and let through is not why it intervened.
    ({"topicPolicy": {"topics": [{"name": "unqualified-repair", "action": "NONE"},
                                 {"name": "defeating-a-guard", "action": "BLOCKED"}]}}, "defeating-a-guard"),
])
def test_a_refusal_names_the_policy_and_never_the_matched_text(monkeypatch, assessment, category):
    runtime = Runtime({"action": "GUARDRAIL_INTERVENED", "assessments": [assessment]})
    verdict = _screener(monkeypatch, runtime).screen(HARM, "text", "node-out")
    assert (verdict.allowed, verdict.category) == (False, category)
    assert HARM not in verdict.category


@pytest.mark.parametrize("runtime", [Runtime(fails=ConnectionError("reset")), Runtime({}),
                                     Runtime({"action": "MAYBE"}), Runtime("not a response")])
def test_no_answer_or_an_answer_without_an_action_is_unavailable(monkeypatch, runtime):
    with pytest.raises(GuardrailUnavailable):
        _screener(monkeypatch, runtime).screen("text", "text", "node-out")


def test_an_image_is_screened_by_its_bytes_and_a_name_alone_is_not_an_image(monkeypatch, tmp_path):
    from gateway.provider import bedrock
    monkeypatch.setattr(bedrock, "ASSETS", tmp_path)
    runtime = Runtime({"action": "NONE"})
    screener = _screener(monkeypatch, runtime)
    with pytest.raises(GuardrailUnavailable, match="no image"):
        screener.screen("bench.png", "image", "image-out")
    png = tmp_path / "bench.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    screener.screen("bench.png", "image", "image-out")
    assert runtime.requests[-1]["content"] == [
        {"image": {"format": "png", "source": {"bytes": b"\x89PNG\r\n\x1a\n"}}}]


@pytest.mark.parametrize("named", ["../../../etc/passwd.png", "/etc/hosts.png"])
def test_an_image_a_node_names_outside_the_assets_is_never_read(monkeypatch, tmp_path, named):
    from gateway.provider import bedrock
    monkeypatch.setattr(bedrock, "ASSETS", tmp_path / "assets")
    (tmp_path / "assets").mkdir()
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"\x89PNG")
    runtime = Runtime({"action": "NONE"})
    with pytest.raises(GuardrailUnavailable):
        _screener(monkeypatch, runtime).screen(str(outside) if named.startswith("/") else "../secret.png",
                                               "image", "image-out")
    assert runtime.requests == []
