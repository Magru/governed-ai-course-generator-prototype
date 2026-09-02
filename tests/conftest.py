"""A unit test must not be able to reach any real AWS account.

Bogus environment credentials sit above profiles and files in boto3's chain, so
setting them here shadows everything below: no profile name, no credentials
file, and no instance metadata can be reached from a test. LIVE=1 removes the
sink for the few tests that genuinely want the account, and those run the same
identity check the provider does.
"""
import os
import pytest

SINK = {
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
    "AWS_CONFIG_FILE": "/dev/null",
    "AWS_EC2_METADATA_DISABLED": "true",
    "AWS_REGION": "us-east-1",
}


@pytest.fixture(autouse=True, scope="session")
def _no_real_aws():
    if os.environ.get("LIVE") == "1":
        yield
        return
    saved = {k: os.environ.get(k) for k in list(SINK) + ["AWS_PROFILE", "AWS_BEARER_TOKEN_BEDROCK"]}
    os.environ.update(SINK)
    os.environ.pop("AWS_PROFILE", None)
    os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
