"""The real guardrail gives the answers the recording assumes it gives.

Skipped unless LIVE=1; `make live` runs them with the variables that keep the
calls in the prototype's own account.
"""
from __future__ import annotations

import pytest

from scenarios.live import KNOWN

pytestmark = pytest.mark.live


@pytest.mark.parametrize("title, text, point, allowed, category", KNOWN)
def test_the_guardrail_answers_as_the_recording_assumes(title, text, point, allowed, category):
    import json
    from gateway.provider.bedrock import BedrockScreener
    from scenarios.twins import _twin
    text = text or json.dumps(_twin("01-forbidden-topic.yaml")["brief"], sort_keys=True)
    verdict = BedrockScreener().screen(text, "text", point)
    assert verdict.allowed == allowed, title
    assert category is None or verdict.category == category, title
