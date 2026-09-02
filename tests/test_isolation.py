"""The isolation must be a mechanism, not a habit."""
import pathlib, re, sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ALLOWED = ROOT / "gateway" / "provider" / "bedrock.py"


def test_only_one_module_imports_the_aws_sdk():
    """A second place that builds a session is a second place that can resolve to
    the wrong account, and it will not be reviewed as carefully as the first.

    Read as an import graph rather than as text: a regex over source missed
    `import boto3 as b3`, `from boto3 import client`, and anything reached
    through importlib. Forbidding the import at all is both simpler and stricter
    than trying to recognise every way a client gets built."""
    import ast
    banned = {"boto3", "botocore", "aioboto3"}
    # This file imports the sdk to prove the sink holds; that is its job. No
    # other test may, and no other module at all — including the rest of tests/,
    # which an earlier version of this check excluded wholesale.
    permitted = {ALLOWED, pathlib.Path(__file__).resolve()}
    offenders = []
    for path in sorted(ROOT.rglob("*.py")):
        if path.resolve() in permitted or ".venv" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            else:
                continue
            if names & banned:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == [], f"the AWS sdk is imported outside the one module: {offenders}"


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
