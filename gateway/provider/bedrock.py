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

from .port import (Generated, Generator, GuardrailNotConfigured, GuardrailUnavailable,
                   Modality, Point, Prompt, ProviderUnavailable, Screener, Verdict)


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


def client(service: str):
    """Every client comes from here, with the signer pinned.

    botocore reads AWS_BEARER_TOKEN_BEDROCK from the environment on each
    bedrock-runtime request and switches signer accordingly. Caching the session
    does not pin that: a token set after the identity check would silently
    authenticate the calls as somebody else while the check still reported the
    account we expected. Fixing the signature version at construction closes it.
    """
    from botocore.config import Config
    # Bounded, so a service that does not answer becomes the Timeout row's
    # business in seconds rather than botocore's default minute and retries.
    return session().client(service, config=Config(signature_version="v4", connect_timeout=5, read_timeout=20,
                                                   retries={"max_attempts": 2, "mode": "standard"}))


class BedrockGenerator(Generator):
    def __init__(self) -> None:
        self._model = _required("BEDROCK_MODEL_ID")

    def generate(self, prompt: Prompt, schema: dict) -> Generated:
        raise NotImplementedError("Bedrock generation is not built; development generates with Gemini")


class BedrockScreener(Screener):
    """Amazon Bedrock Guardrails, through ApplyGuardrail: the managed service
    the specification names, screening content the pipeline hands it.

    Separate from the generator so the pair that development actually runs —
    Gemini generating, Bedrock screening — can be expressed at all.

    The version is the one the request names. Bedrock evaluates exactly the
    version it is asked for, so the stamp on the verdict is the version that
    answered — which is why a DRAFT is refused: it can change under a verdict
    already recorded as screened by it."""

    def __init__(self, runtime=None) -> None:
        self._guardrail = os.environ.get("BEDROCK_GUARDRAIL_ID", "").strip()
        self._version = os.environ.get("BEDROCK_GUARDRAIL_VERSION", "").strip()
        self._runtime = runtime
        self.guardrail = self._guardrail or None
        self.version = self._version or None

    def screen(self, content: str, modality: Modality, point: Point, subject: str = "") -> Verdict:
        if not self._guardrail:
            raise GuardrailNotConfigured(
                "no guardrail is configured. A deployment error rather than a "
                "runtime one — but still not a reason to proceed, because the "
                "absence of a verdict is not a permissive verdict.")
        if not self._version.isdigit():
            raise GuardrailNotConfigured(
                f"guardrail version {self._version or '(none)'!r} is not a published version; "
                f"a DRAFT can change after a verdict is recorded as screened by it")
        try:
            response = (self._runtime or client("bedrock-runtime")).apply_guardrail(
                guardrailIdentifier=self._guardrail, guardrailVersion=self._version,
                # What a model is about to be asked is input; what one said is output.
                source="INPUT" if point in ("brief-in", "image-prompt-out") else "OUTPUT",
                content=[_content(content, modality)])
        except (GuardrailNotConfigured, GuardrailUnavailable):
            raise
        except Exception as exc:                  # noqa: BLE001 — no answer is not an answer
            raise GuardrailUnavailable(f"the guardrail did not answer at {point}: {exc}") from exc
        action = response.get("action") if isinstance(response, dict) else None
        if action not in ("NONE", "GUARDRAIL_INTERVENED"):
            raise GuardrailUnavailable(f"the guardrail answered at {point} with no action: {action!r}")
        if action == "NONE":
            return Verdict(True, None, self._version, point)
        return Verdict(False, _category(response.get("assessments") or []), self._version, point)


#: Where an image a node names must be. The name is model output, so it is
#: resolved inside this folder and nowhere else: a node naming any other file on
#: the machine must not get that file sent to a third party.
ASSETS = pathlib.Path(__file__).resolve().parents[2] / "assets"


def _content(content: str, modality: Modality) -> dict:
    """Text goes as text. An image goes as its bytes, and only when there are
    bytes to send: screening the name of an image is not screening the image."""
    if modality == "text":
        return {"text": {"text": content}}
    path = (ASSETS / content).resolve()
    kind = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg"}.get(path.suffix.lower())
    if kind is None or not path.is_relative_to(ASSETS) or not path.is_file():
        raise GuardrailUnavailable(f"no image in assets/ to screen at {content!r}")
    return {"image": {"format": kind, "source": {"bytes": path.read_bytes()}}}


def _blocked(entries) -> list:
    """Entries that acted. A response may also list what was detected and let
    through, and that is not why the guardrail intervened."""
    return [e for e in entries or [] if e.get("action", "BLOCKED") == "BLOCKED"]


def _category(assessments: list) -> str:
    """The policy that intervened, by name — never the text it matched."""
    for a in assessments:
        for topic in _blocked((a.get("topicPolicy") or {}).get("topics")):
            return topic.get("name", "denied-topic")
        sensitive = a.get("sensitiveInformationPolicy") or {}
        for entity in _blocked(sensitive.get("piiEntities")):
            return entity.get("type", "personal-data").lower().replace("_", "-")
        for regex in _blocked(sensitive.get("regexes")):
            return regex.get("name", "personal-data")
        for f in _blocked((a.get("contentPolicy") or {}).get("filters")):
            return f.get("type", "content").lower().replace("_", "-")
        words = a.get("wordPolicy") or {}
        if words.get("customWords") or words.get("managedWordLists"):
            return "word-policy"
    return "intervened"
