"""The operators themselves, before anything domain-specific rests on them."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.temporal import ltl

TRACE = [{"n": 1}, {"n": 2}, {"n": 3}, {"n": 4}]


def test_always_returns_the_first_failing_step():
    assert ltl.always(TRACE, lambda s: s["n"] < 3) == 2
    assert ltl.always(TRACE, lambda s: s["n"] < 9) is None


def test_eventually_finds_the_first_and_respects_after():
    assert ltl.eventually(TRACE, lambda s: s["n"] == 2) == 1
    assert ltl.eventually(TRACE, lambda s: s["n"] == 2, after=2) is None


def test_next_is_false_at_the_end_because_there_is_no_next():
    assert ltl.next_step(TRACE, 0, lambda s: s["n"] == 2)
    assert not ltl.next_step(TRACE, 3, lambda s: True)


def test_once_looks_strictly_backwards():
    assert ltl.once(TRACE, 2, lambda s: s["n"] == 1)
    assert not ltl.once(TRACE, 0, lambda s: s["n"] == 1)   # nothing precedes step 0


def test_until_needs_the_second_to_actually_arrive():
    assert ltl.until(TRACE, lambda s: s["n"] < 3, lambda s: s["n"] == 3)
    assert not ltl.until(TRACE, lambda s: s["n"] < 3, lambda s: s["n"] == 99)
