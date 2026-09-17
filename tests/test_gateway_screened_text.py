"""The screened text is every string a node keeps, bar what is not prose."""
from gateway.screened_text import screened_text


def test_keys_and_fields_beside_the_blocks_are_read():
    content = {"blocks": [{"type": "paragraph", "text": "a", "cites": ["k-1"]}],
               "cites": ["k-2"], "id": "an id", "meta": {"a key": "a value"}}
    text = screened_text(content)
    for said in ("an id", "a key", "a value"):
        assert said in text
    assert "k-1" not in text and "k-2" not in text


def test_what_sits_in_an_id_field_without_being_an_id_is_read():
    content = {"blocks": {"x": "in a dict of blocks"}, "cites": [{"c": "in a cite"}]}
    text = screened_text(content)
    assert "in a dict of blocks" in text and "in a cite" in text
    block = {"blocks": [{"type": "image", "src": {"s": "in a source"}, "cites": [{"c": "a"}]}]}
    assert "in a source" in screened_text(block)


def test_a_source_is_prose_everywhere_but_on_an_image():
    content = {"blocks": [{"type": "paragraph", "text": "a", "src": "said"},
                          {"type": "image", "src": "img.png", "alt": "b"}]}
    text = screened_text(content)
    assert "said" in text and "img.png" not in text
