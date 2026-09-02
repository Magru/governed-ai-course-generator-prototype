"""The three trust levels must survive the port.

The specification keeps system instructions, the author's text and retrieved
sources apart rather than concatenating them, and says in as many words that the
separation is the defence. An earlier port took `prompt: str`, which forced the
caller to join them before a provider ever saw them — the port itself made the
architecture impossible to implement.
"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from gateway.provider.port import Generator, Prompt, Screener


def test_a_prompt_carries_its_positions_separately():
    p = Prompt(instructions="rules", author="make it shorter", sources=("a doc",))
    assert (p.instructions, p.author, p.sources) == ("rules", "make it shorter", ("a doc",))


def test_a_prompt_cannot_be_flattened_by_accident():
    """Frozen, so nothing downstream can quietly replace the parts with a join."""
    import dataclasses, pytest
    p = Prompt(instructions="rules")
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.instructions = "rules\nand the author's text"


def test_generation_and_screening_are_different_ports():
    """Gemini generates and Bedrock screens; one interface could not say that."""
    assert not hasattr(Generator, "screen")
    assert not hasattr(Screener, "generate")
