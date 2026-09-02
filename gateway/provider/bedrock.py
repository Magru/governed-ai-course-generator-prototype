"""The only module in this repository that constructs an AWS client.

The machine this runs on has a default AWS profile that is an administrator of
someone else's account. A bare `boto3.client(...)` anywhere in this tree would
reach it and succeed. So there is one place, it checks who it is before it does
anything, and an architecture test fails the build if a second place appears.

The check runs on the same Session that will make the calls. Asking the CLI, or
a second session, would prove something about a different credential resolution
than the one in use.
"""
from __future__ import annotations
import os, pathlib
from functools import lru_cache

from .port import GuardrailUnavailable, Provider, ProviderUnavailable, Verdict


class WrongAccount(RuntimeError):
    """Refuse rather than act. The account this resolved to is not ours."""


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise WrongAccount(
            f"{name} is not set. It has no default on purpose: without it the "
            f"credential chain falls through to whatever profile the machine "
            f"happens to have, which here is an administrator of a different "
            f"account.")
    return value


def _refuse_ambient_credentials() -> None:
    """Environment keys sit above profiles in the chain, and a Bedrock bearer
    token bypasses STS entirely — the identity check would pass while the calls
    authenticated as someone else."""
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SESSION_TOKEN", "AWS_BEARER_TOKEN_BEDROCK"):
        if os.environ.get(name):
            raise WrongAccount(
                f"{name} is set. It outranks the profile in boto3's credential "
                f"chain, so the identity this module verified would not be the "
                f"identity that makes the call.")
    for name in ("AWS_SHARED_CREDENTIALS_FILE", "AWS_CONFIG_FILE"):
        path = os.environ.get(name, "")
        if not path or not pathlib.Path(path).expanduser().exists():
            raise WrongAccount(
                f"{name} does not point at an existing file. Without it boto3 "
                f"reads ~/.aws/credentials, where the default profile is not ours.")


@lru_cache(maxsize=1)
def session():
    """One session, checked once, reused. Cached so the check cannot drift from
    the calls it authorised."""
    import boto3

    expected = _required("BEDROCK_ACCOUNT_ID")
    _refuse_ambient_credentials()

    s = boto3.Session(region_name=os.environ.get("AWS_REGION", "us-east-1"))
    try:
        identity = s.client("sts").get_caller_identity()
    except Exception as exc:                      # noqa: BLE001 — any failure is a refusal
        raise ProviderUnavailable(f"could not establish who we are: {exc}") from exc

    if identity["Account"] != expected:
        raise WrongAccount(
            f"resolved to account {identity['Account']} ({identity['Arn']}), "
            f"expected {expected}. Refusing before any call is made.")
    return s


class BedrockProvider(Provider):
    def __init__(self) -> None:
        self._model = _required("BEDROCK_MODEL_ID")

    def generate(self, prompt: str, schema: dict) -> dict:
        raise NotImplementedError("generation lands with the gateway, phase 03")

    def screen(self, text: str) -> Verdict:
        guardrail = os.environ.get("BEDROCK_GUARDRAIL_ID", "").strip()
        if not guardrail:
            raise GuardrailUnavailable(
                "no guardrail is configured. The specification forbids reading a "
                "missing verdict as a permissive one, so this stops rather than "
                "returns.")
        raise NotImplementedError("screening lands with the gateway, phase 03")
