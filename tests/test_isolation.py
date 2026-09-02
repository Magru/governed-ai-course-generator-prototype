"""The isolation must be a mechanism, not a habit."""
import pathlib, re, sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ALLOWED = ROOT / "gateway" / "provider" / "bedrock.py"


def test_only_one_module_constructs_an_aws_client():
    """A second place that builds a session is a second place that can resolve
    to the wrong account, and it will not be reviewed as carefully as the first."""
    offenders = []
    for path in ROOT.rglob("*.py"):
        if path == ALLOWED or ".venv" in path.parts or path.parent.name == "tests":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"\bboto3\.(client|Session|resource)\b|\bimport +botocore\b", text):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"AWS clients built outside the one module: {offenders}"


def test_the_sink_makes_a_real_account_unreachable():
    import boto3
    creds = boto3.Session().get_credentials()
    assert creds is not None and creds.access_key == "testing", (
        "a test resolved real credentials; the sink in conftest is not holding")


def test_no_account_id_means_refusal():
    from gateway.provider.bedrock import WrongAccount, session
    import os
    session.cache_clear()
    os.environ.pop("BEDROCK_ACCOUNT_ID", None)
    with pytest.raises(WrongAccount, match="no default on purpose"):
        session()


def test_ambient_keys_are_refused(monkeypatch):
    from gateway.provider.bedrock import WrongAccount, session
    session.cache_clear()
    monkeypatch.setenv("BEDROCK_ACCOUNT_ID", "631412641947")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "anything")
    with pytest.raises(WrongAccount, match="outranks the profile"):
        session()
