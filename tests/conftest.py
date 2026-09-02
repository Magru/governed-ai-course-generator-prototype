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


# Applied at import time, not in a fixture. A session fixture runs after every
# test module has been imported, so anything that touched credentials at module
# level — or `--collect-only`, or running a test file directly — would already
# have seen the machine's real chain.
if os.environ.get("LIVE") != "1":
    os.environ.update(SINK)
    os.environ.pop("AWS_PROFILE", None)
    os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: needs the real provider; skipped unless LIVE=1")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="needs LIVE=1")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
