"""The leak scan must fire. A scanner that never fails is indistinguishable
from a broken one, so the canary is a test rather than a note in a runbook."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import tools_allowlist_scan as scanner


def test_the_real_fixtures_are_clean():
    assert scanner.scan() == []


def test_a_slug_from_outside_the_universe_is_caught(tmp_path):
    """The token is invented, and must stay that way: a test that proves the scan
    catches borrowed names is the last place one should be written down."""
    (tmp_path / "leak.yaml").write_text("org: kestrelbank\n", encoding="utf-8")
    assert any("kestrelbank" in f for f in scanner.scan(tmp_path))


def test_a_real_uuid_is_caught(tmp_path):
    (tmp_path / "leak.yaml").write_text(
        "chunk: 3f2a91c4-7b6e-4d21-9a03-1c8e5f7b2d90\n", encoding="utf-8")
    assert any("UUID" in f for f in scanner.scan(tmp_path))


def test_another_alphabet_is_caught(tmp_path):
    (tmp_path / "leak.yaml").write_text("title: מבוא\n", encoding="utf-8")
    assert any("Hebrew" in f for f in scanner.scan(tmp_path))


def test_the_invented_vocabulary_passes(tmp_path):
    (tmp_path / "ok.yaml").write_text(
        "org: meridian-tools\nskill: bench-safety\naudience: apprentices\n", encoding="utf-8")
    assert scanner.scan(tmp_path) == []
