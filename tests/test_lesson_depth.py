"""A lesson is about its own skill, and there is enough of it for its minutes.

The model writes only from the sources it is given, so what it is given decides
what a lesson can say: scoped to the lesson's skill, so one lesson does not teach
the whole course, and counted against the minutes the lesson states, so twenty
minutes is not one paragraph.
"""
from __future__ import annotations

import copy

from engines.z3.engine import _words, check_arithmetic
from gateway.asking import node_request
from gateway.provider.port import Screener, Verdict
from gateway.provider.recorded import RecordedGenerator
from machine.world import load
from scenarios import run, walkthrough as w

TH = {"min_words_per_minute": 10}


class Allowing(Screener):
    version = "guard-1"

    def screen(self, content, modality, point, subject=""):
        return Verdict(True, None, self.version, point)


def _pipeline(**answers):
    recorded = {f"node:{n}": [copy.deepcopy(w.CONTENT[n])] for n in (w.T1, w.T2, w.T3, w.E1)}
    recorded.update(answers)
    p = run.pipeline(generator=RecordedGenerator({"outline": [copy.deepcopy(w.OUTLINE)], **recorded}),
                     screener=Allowing())
    p.submit_brief(copy.deepcopy(w.BRIEF), run.AUTHOR)
    p.draft_outline(run.AUTHOR)
    p.machine.fire("OutlineApproved", {"actor": run.AUTHOR["id"]})
    return p


def _sources(p, task):
    return [prompt.sources for asked, prompt in p.generator.asked if asked == task]


def _short(node):
    content = copy.deepcopy(w.CONTENT[node])
    content["blocks"] = [{"type": "paragraph", "text": "keep the bench clear", "cites": ["mt-kb-001"]}]
    return content


# ------------------------------------------------------------- the count

def test_a_twenty_minute_lesson_of_one_sentence_is_refused_with_the_numbers():
    node = {"id": "n1", "type": "topic", "minutes": 20,
            "blocks": [{"type": "paragraph", "text": "keep the bench clear", "cites": ["c"]}]}
    v = check_arithmetic(node, TH)
    assert not v.ok and v.refusal.kind == "failing-sum"
    assert "enough_words_for_the_minutes" in v.refusal.detail["core"]
    assert (v.refusal.detail["words"], v.refusal.detail["needed"]) == (4, 200)
    assert "4 words for 20 minutes; at least 200" in v.refusal.summary


def test_a_lesson_long_enough_for_its_minutes_passes():
    assert check_arithmetic({"id": w.T1, "type": "topic", **w.CONTENT[w.T1]}, TH).ok


def test_only_the_words_a_learner_reads_are_counted():
    blocks = [{"type": "heading", "text": "two words"}, {"type": "checklist", "items": ["one", "two three"]},
              {"type": "quiz", "question": "a b", "options": ["c", "d e"]}, {"type": "image", "src": "x.png",
              "caption": "one caption"}, 7, None]
    assert _words(blocks) == 2 + 3 + 2 + 3 + 2


def test_an_exam_and_an_organisation_without_the_floor_are_not_counted():
    exam = {"id": "e", "type": "exam", "minutes": 20, "points_total": 5,
            "blocks": [{"type": "quiz", "question": "q", "options": ["a", "b"], "answer": 0, "points": 5}]}
    assert check_arithmetic(exam, TH).ok
    assert check_arithmetic({"id": "n", "type": "topic", "minutes": 20, "blocks": []}, {}).ok


def test_a_short_lesson_is_repaired_and_the_next_draft_is_told_how_far_short_it_fell():
    p = _pipeline(**{f"node:{w.T1}": [_short(w.T1), copy.deepcopy(w.CONTENT[w.T1])]})
    p.generate_node(w.T1, run.AUTHOR)
    node = p.machine.current.nodes[w.T1]
    assert node.state == "Validated" and node.repair_count == 1
    retry = [prompt for asked, prompt in p.generator.asked if asked == f"node:{w.T1}"][-1]
    assert "at least 200" in retry.instructions


# ------------------------------------------------------------- the sources

def test_a_lesson_is_given_the_chunks_about_its_own_skill_and_no_others():
    p = _pipeline()
    p.generate_node(w.T1, run.AUTHOR)
    (sources,) = _sources(p, f"node:{w.T1}")
    assert {s.split(":")[0] for s in sources} == {"mt-kb-001", "mt-kb-012", "mt-kb-013", "mt-kb-014"}


def test_an_exam_is_given_the_chunks_of_the_topics_it_tests_and_the_outline_everything_open():
    p = _pipeline()
    for topic in (w.T1, w.T2, w.T3):
        p.generate_node(topic, run.AUTHOR)
        p.membrane.request("approve_node", {"node": topic, "what_was_shown": "formal verdict",
                                            **({"visuals_reviewed": [f"{w.T1}.blocks[1]"]} if topic == w.T1 else {})},
                           run.AUTHOR)
    p.generate_node(w.E1, run.AUTHOR)
    exam = {s.split(":")[0] for s in _sources(p, f"node:{w.E1}")[0]}
    outline = {s.split(":")[0] for s in _sources(p, "outline")[0]}
    assert exam == {"mt-kb-001", "mt-kb-012", "mt-kb-013", "mt-kb-014", "mt-kb-002", "mt-kb-015",
                    "mt-kb-016", "mt-kb-017", "mt-kb-005", "mt-kb-018", "mt-kb-019", "mt-kb-020"}
    assert exam < outline and "mt-kb-009" in outline        # lifting is open to apprentices, and on no lesson
    assert "mt-kb-008" not in outline                       # scoping never widens what an audience sees


# ------------------------------------------------------------- the ask

def test_the_model_is_told_the_skill_and_the_floor_and_the_course_title_stays_the_authors():
    world = load()
    spec = {"id": w.T1, "type": "topic", "skill": "bench-safety"}
    rules, _ = node_request(world, w.T1, spec, w.BRIEF)
    assert rules.split("\n", 1)[0] == f"node:{w.T1}"
    assert "This lesson teaches Bench safety" in rules and "at least 200 words" in rules
    assert w.BRIEF["title"] not in rules
    p = _pipeline()
    p.generate_node(w.T1, run.AUTHOR)
    prompt = [prompt for asked, prompt in p.generator.asked if asked == f"node:{w.T1}"][0]
    assert w.BRIEF["title"] in prompt.author


def test_a_lesson_is_not_offered_an_exams_fields_and_an_exam_must_state_its_total():
    world = load()
    _, topic = node_request(world, w.T1, {"id": w.T1, "type": "topic", "skill": "bench-safety"}, w.BRIEF)
    _, exam = node_request(world, w.E1, {"id": w.E1, "type": "exam", "topics": [w.T1]}, w.BRIEF)
    assert not {"points_total", "questions"} & set(topic["properties"])
    assert "points_total" in exam["required"] and "questions" in exam["properties"]
