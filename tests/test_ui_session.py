"""The page drives the real machine: the buttons a person presses reach the
same gateway and the same checks as `make run`, and a refusal is shown with
the engine and the artifact that refused it."""
from __future__ import annotations

import pytest

from scenarios import walkthrough as w
from ui.session import Session


def test_the_buttons_take_a_course_from_brief_to_publication():
    s = Session()
    steps = [("submit", None), ("approve_outline",)]
    for node in (w.T1, w.T2, w.T3, w.E1):
        steps += [("generate", node), ("approve", node)]
    steps += [("course_checks",), ("sign",), ("publish",)]
    for name, *args in steps:
        assert s.act(name, *args) == {"ok": True}, name
    snap = s.snapshot()
    assert snap["revision"]["state"] == "Published"
    assert snap["ltl"] == "every invariant holds"
    assert {e["kind"] for e in snap["engine_log"]} >= {"invented-skill", "leak-path"}


@pytest.mark.parametrize("preset, ends, engine", [
    ("forbidden", "BlockedFinal", None),
    ("infeasible", "BlockedRecoverable", "z3"),
    ("audience", "BlockedFinal", "opa"),
])
def test_each_refusal_preset_stops_where_the_specification_says(preset, ends, engine):
    s = Session(preset=preset)
    s.act("submit", None)
    snap = s.snapshot()
    assert snap["revision"]["state"] == ends
    assert [e["engine"] for e in snap["engine_log"]][-1:] == ([engine] if engine else [])


def test_a_button_the_machine_refuses_says_why_and_moves_nothing():
    s = Session()
    out = s.act("publish")
    assert not out["ok"] and out["error"].startswith("policy_allows: ")   # refused at the gate, by name
    assert s.snapshot()["revision"]["state"] == "AwaitingBrief"


def test_a_rejected_lesson_is_written_again_in_recorded_mode_and_can_be_approved():
    s = Session()
    for name, *args in [("submit", None), ("approve_outline",), ("generate", w.T1)]:
        assert s.act(name, *args)["ok"], name
    assert s.act("reject", w.T1, "too short")["ok"]
    assert s.act("generate", w.T1)["ok"]
    node = next(n for n in s.snapshot()["nodes"] if n["id"] == w.T1)
    assert node["state"] == "Validated"
    assert "revised after review" in node["content"]["blocks"][0]["text"]
    assert s.act("approve", w.T1)["ok"]


def test_live_mode_is_refused_without_a_published_guardrail(monkeypatch):
    pytest.importorskip("google.genai")
    monkeypatch.setenv("GEMINI_API_KEY", "canary-gemini-0000")
    monkeypatch.delenv("BEDROCK_GUARDRAIL_ID", raising=False)
    with pytest.raises(RuntimeError, match="BEDROCK_GUARDRAIL"):
        Session(mode="live")


def test_only_this_page_may_press_the_buttons():
    import json
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from ui.server import Handler
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/api/reset"

    def post(headers):
        req = urllib.request.Request(url, data=json.dumps({"preset": "course"}).encode(), headers=headers)
        try:
            return urllib.request.urlopen(req).status
        except urllib.error.HTTPError as exc:
            return exc.code
    try:
        assert post({"Content-Type": "text/plain"}) == 403
        assert post({"Content-Type": "application/json", "Origin": "http://elsewhere.example"}) == 403
        assert post({"Content-Type": "application/json"}) == 200
    finally:
        server.shutdown()
