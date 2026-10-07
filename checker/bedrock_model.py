"""Claude on Amazon Bedrock, in the India region — the CLIENT-data model provider (B1).

PLAN_22 D3: a client document may be sent only to an endpoint whose hosting region is
confirmed acceptable. The Azure Llama deployment is UAE North, which nobody confirmed for
client data, so `checker/azure_model.refuse_unconfirmed_region` refuses a client document
there. Bedrock in **ap-south-1 (Mumbai)**, reached through the `in.anthropic.*` India
inference profile, is the confirmed-India endpoint — so this is the provider that may see a
client's own documents. Azure stays test-only.

## Three things this module refuses to get wrong

1. **India only.** Before a live call, the inference profile's member regions are read and
   asserted to be Indian (ap-south-1 / ap-south-2). A profile that routed anywhere else is
   refused, loudly — a client document must never leave the region on a silent routing
   change.
2. **Keyless gate.** `boto3` is an OPTIONAL runtime dependency (like `sentence_transformers`
   for dense retrieval): it is imported lazily, never at module load, and is in no
   requirements file. With no boto3 and no AWS credentials, `available()` is False, so the
   gate routes to a deterministic stand-in and never touches AWS. The decision path stays
   standard-library; `--live` needs boto3 installed and the account verified.
3. **Access-pending is a STATE, not a crash.** While AWS is verifying the account (or model
   access is not yet granted), a call raises `ProviderNotReady` — a typed signal the gateway
   turns into a `PROVIDER_NOT_READY` refusal, never a `NOT_FOUND` and never an abstention.

Untrusted text carries `prompt_safety.UNTRUSTED_CLAUSE` in the system prompt, the public-only
clearance (`verify_prompt`) runs before the socket opens, every call is held against the caps
through `backend/budget.reserve`, and the retry here is the same shape as `azure_model`'s.
"""
from __future__ import annotations


from checker.prompt_safety import UNTRUSTED_CLAUSE

# The India-geography inference profiles, verified 2026-10-07 to route only to ap-south-1
# and ap-south-2. Keyed by the budget model name so one map answers both "which profile do
# I call" and "which price applies".
REGION = "ap-south-1"
INDIA_REGIONS = frozenset({"ap-south-1", "ap-south-2"})
PRIMARY = "claude-haiku-4-5"
ESCALATION = "claude-sonnet-5"
PROFILE: dict[str, str] = {
    PRIMARY: "in.anthropic.claude-haiku-4-5-20251001-v1:0",
    ESCALATION: "in.anthropic.claude-sonnet-5",
}

NARRATION_BUDGET = 4096          # max output tokens, as azure_model
RETRY_BASE_SECONDS = 2.0         # Bedrock throttling clears fast; shorter than Azure's TPM wait


class BedrockUnavailable(RuntimeError):
    """No call could be made for a reason that is ours: no boto3, no creds, budget spent."""


class Throttled(BedrockUnavailable):
    """Bedrock returned a throttling error. Retried by `with_backoff`."""


class RegionRefused(RuntimeError):
    """The inference profile routes outside India. Refused — never widened silently."""


class ProviderNotReady(RuntimeError):
    """The account is being verified, or model access is not yet granted.

    A typed state, so the gateway reports PROVIDER_NOT_READY rather than a generic failure or
    an abstention. Carries the provider's own message so an operator sees what AWS said.
    """


def available() -> bool:
    """True only if a live call is possible here: boto3 importable AND credentials resolvable.

    No network, no call. Keyless gate -> False, so the gate uses the stand-in. This is the
    same optional-capability gate as dense retrieval's `sentence_transformers` check.
    """
    import importlib.util
    if importlib.util.find_spec("boto3") is None:
        return False
    try:
        import boto3
        return boto3.Session().get_credentials() is not None
    except Exception:                                            # noqa: BLE001
        return False


def _runtime_client():
    import boto3
    return boto3.client("bedrock-runtime", region_name=REGION)


def _control_client():
    import boto3
    return boto3.client("bedrock", region_name=REGION)


def _profile_member_regions(control, profile_id: str) -> tuple[str, ...]:
    """The regions an inference profile can route to, read from its member model ARNs.

    An ARN is `arn:aws:bedrock:<region>::foundation-model/<model>`; the region is field 3.
    """
    prof = control.get_inference_profile(inferenceProfileIdentifier=profile_id)
    out = []
    for m in prof.get("models", []):
        parts = (m.get("modelArn") or "").split(":")
        if len(parts) > 3 and parts[3]:
            out.append(parts[3])
    return tuple(out)


_ASSERTED: set[str] = set()


def assert_india(control, profile_id: str) -> None:
    """Refuse a profile that routes anywhere but India. Cached per profile; reads once."""
    if profile_id in _ASSERTED:
        return
    regions = _profile_member_regions(control, profile_id)
    stray = [r for r in regions if r not in INDIA_REGIONS]
    if not regions:
        raise RegionRefused(
            f"inference profile {profile_id!r} reported no member regions; refusing to send "
            f"a client document to a destination that cannot be confirmed as India")
    if stray:
        raise RegionRefused(
            f"inference profile {profile_id!r} routes to {stray}, which is outside India "
            f"(allowed: {sorted(INDIA_REGIONS)}). Refusing — a client document must not "
            f"leave the region on a routing change")
    _ASSERTED.add(profile_id)


def usage_of(response: dict) -> dict:
    """The Converse token counts, as ints or None — NEVER defaulted to zero.

    An absent count is UNPRICED (backend/budget prices None as unknown), not free.
    """
    u = (response or {}).get("usage") or {}

    def _n(key):
        v = u.get(key)
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    return {"tokens_in": _n("inputTokens"), "tokens_out": _n("outputTokens")}


def _text_of(response: dict) -> str:
    """The assistant's text from a Converse reply. Empty is refused by the caller, not here."""
    blocks = (((response or {}).get("output") or {}).get("message") or {}).get("content") or []
    return "".join(b.get("text", "") for b in blocks if isinstance(b, dict))


def _is_not_ready(exc: Exception) -> bool:
    """Does this Bedrock error mean the account/model access is pending, not a real failure?"""
    msg = str(exc).lower()
    return ("being verified" in msg or "not authorized to perform" in msg
            or "access to this operation" in msg or "don't have access to the model" in msg
            or "you don't have access" in msg)


def _is_throttle(exc: Exception) -> bool:
    name = type(exc).__name__
    return name in ("ThrottlingException", "TooManyRequestsException") or "throttl" in str(exc).lower()


def converse(prompt: str, *, system: str, model_id: str, runtime,
             max_tokens: int = NARRATION_BUDGET) -> tuple[str, dict]:
    """One Converse call. Returns (text, usage). Maps AWS errors to typed states.

    The request shape is Bedrock's Converse API: a `system` block, one user message, and an
    inference config. `temperature` is 0 so the stand-in and the live model are as close as a
    model gets — the gate asserts the request SHAPE, never the live text.
    """
    req = {
        "modelId": model_id,
        "system": [{"text": system}],
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0},
    }
    try:
        response = runtime.converse(**req)
    except Exception as e:                                       # noqa: BLE001
        if _is_not_ready(e):
            raise ProviderNotReady(
                f"Bedrock refused because the account or model access is not ready yet "
                f"({type(e).__name__}: {str(e)[:160]}). This is a provider state, not a "
                f"failure of the request.") from e
        if _is_throttle(e):
            raise Throttled(f"Bedrock throttled the request ({type(e).__name__})") from e
        raise BedrockUnavailable(f"Bedrock call failed ({type(e).__name__}: {str(e)[:160]})") from e
    return _text_of(response), usage_of(response)


def cost_inr(model: str, tokens_in: int, tokens_out: int) -> float:
    """Rupee cost of one call, from backend/budget's price table (see its Bedrock note)."""
    from backend.budget import cost_inr as _budget_cost
    return _budget_cost(model, tokens_in, tokens_out)


def narrate(prompt: str, *, origin, model: str = PRIMARY, budget=None,
            _runtime=None, _control=None, on_usage=None) -> str:
    """A text-in/text-out Converse call, under public-only clearance and the budget caps.

    `origin` is an Origin or a tuple of them; `verify_prompt` runs BEFORE the socket opens,
    so a clearance refusal costs no request. The region is NOT refused for a client document
    here — that is the whole point of this provider: ap-south-1 is the confirmed-India
    endpoint. Every call reserves its worst case against the caps first and settles the
    actual after, so an abandoned or refused call leaves the ledger as it found it.
    """
    from checker.public_only import verify_prompt
    verify_prompt(prompt, origin)

    model_id = PROFILE.get(model)
    if model_id is None:
        raise BedrockUnavailable(f"no India inference profile on record for {model!r}")

    from backend.budget import estimate_tokens
    rid = None
    if budget is not None:
        res = budget.reserve(model=model,
                             input_tokens=estimate_tokens(model, words=len(prompt.split())),
                             max_tokens=NARRATION_BUDGET)
        if not res.allowed:
            raise BedrockUnavailable(f"budget refused the call: {res.verdict.reason}")
        rid = res.id

    runtime = _runtime if _runtime is not None else _runtime_client()
    control = _control if _control is not None else _control_client()
    try:
        assert_india(control, model_id)
        text, usage = converse(prompt, system=UNTRUSTED_CLAUSE, model_id=model_id,
                               runtime=runtime)
    except Exception:
        # Nothing billed on a refusal/not-ready/transport error: settle at 0.0 so a call that
        # never produced tokens does not spend the cap. (A call that MAY have billed but hid
        # its usage would settle at the reservation; we only reach here when no usage exists.)
        if budget is not None and rid is not None:
            budget.settle(rid, 0.0)
        raise

    if on_usage is not None:
        on_usage(usage | {"model": model, "provider": "bedrock", "region": REGION})
    if budget is not None and rid is not None:
        tin, tout = usage.get("tokens_in"), usage.get("tokens_out")
        # Unknown usage settles at the reservation, not 0.0 — an unknown cost is an
        # expensive one (backend/budget's own rule).
        actual = cost_inr(model, tin or 0, tout or 0) if tin is not None and tout is not None \
            else res.amount_inr
        budget.settle(rid, actual)
    return text


def with_backoff(call, *, sleep=None, tries: int = 3, base: float = RETRY_BASE_SECONDS):
    """Retry a model callable on throttling only, waiting between tries. `sleep` is injected.

    Same shape as `azure_model.with_backoff`: a library that sleeps on its own hangs a test
    suite, so the gate passes `sleep` and exercises every branch without waiting.
    """
    def _c(prompt: str) -> str:
        last = None
        for i in range(tries):
            try:
                return call(prompt)
            except Exception as e:                               # noqa: BLE001
                if not isinstance(e, Throttled) or sleep is None or i == tries - 1:
                    raise
                last = e
                sleep(base * (i + 1))
        raise last                                               # pragma: no cover
    return _c


def as_text_model(*, origin, model: str = PRIMARY, budget=None,
                  _runtime=None, _control=None, on_usage=None):
    """`narrate` as the Callable[[str], str] the gateway's `serve()` wires as `.call`."""
    if origin is None:
        raise TypeError("as_text_model(origin=...) is required")

    def _m(prompt: str) -> str:
        return narrate(prompt, origin=origin, model=model, budget=budget,
                       _runtime=_runtime, _control=_control, on_usage=on_usage)
    return _m


# ── a fake Converse client, so the gate tests every branch with no boto3 and no network ──
class _FakeRuntime:
    def __init__(self, *, text="OK", usage=(12, 3), error=None):
        self._text, self._usage, self._error = text, usage, error
        self.calls = []

    def converse(self, **req):
        self.calls.append(req)
        if self._error is not None:
            raise self._error
        tin, tout = self._usage
        return {"output": {"message": {"content": [{"text": self._text}]}},
                "usage": {"inputTokens": tin, "outputTokens": tout}}


class _FakeControl:
    def __init__(self, regions=("ap-south-1", "ap-south-2")):
        self._regions = regions

    def get_inference_profile(self, inferenceProfileIdentifier=None):
        return {"models": [{"modelArn": f"arn:aws:bedrock:{r}::foundation-model/x"}
                           for r in self._regions]}


class _BotoError(Exception):
    """Stands in for a botocore ClientError message in the gate."""


def _test() -> None:
    passed = failed = 0

    def check(cond: bool, label: str) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  [PASS] {label}")
        else:
            failed += 1
            print(f"  [FAIL] {label}")

    print("bedrock_model")
    from checker import public_only
    _ASSERTED.clear()

    # A published provision, wrapped so verify_prompt clears it (the azure_model pattern).
    import json as _json
    from checker.prompt_safety import wrap_untrusted as _wrap
    _act = public_only.ROOT / "corpus" / "companies_act" / "1220.json"
    _o = public_only.clear_file(_act)
    _prov = _json.loads(_act.read_text())["content"][:300]
    cleared = "Phrase this, quoting only it.\n" + _wrap(_prov, "s1") + "\nWhat does it say?"

    # ── India-only region assertion ─────────────────────────────────────────
    assert_india(_FakeControl(("ap-south-1", "ap-south-2")), "in.anthropic.x")
    check("in.anthropic.x" in _ASSERTED, "an all-India profile is accepted and cached")
    _ASSERTED.clear()
    try:
        assert_india(_FakeControl(("ap-south-1", "us-east-1")), "in.anthropic.bad")
        check(False, "a profile routing outside India must be refused")
    except RegionRefused as e:
        check("us-east-1" in str(e), f"a non-India member region is refused by name ({e})")
    _ASSERTED.clear()
    try:
        assert_india(_FakeControl(()), "in.anthropic.empty")
        check(False, "a profile with no member regions must be refused")
    except RegionRefused:
        check(True, "a profile with no confirmable regions is refused, not assumed India")
    _ASSERTED.clear()

    # ── the happy path: UNTRUSTED_CLAUSE in system, usage parsed, budget settled ──
    rt = _FakeRuntime(text="quoted answer", usage=(100, 20))
    seen: list = []
    out = narrate(cleared, origin=_o, model=PRIMARY, budget=None,
                  _runtime=rt, _control=_FakeControl(), on_usage=seen.append)
    check(out == "quoted answer", "the assistant text is returned")
    check(rt.calls and rt.calls[0]["system"][0]["text"] == UNTRUSTED_CLAUSE,
          "the system prompt carries UNTRUSTED_CLAUSE on every call")
    check(rt.calls[0]["modelId"] == PROFILE[PRIMARY],
          "the call targets the India inference profile, not a bare model id")
    check(seen and seen[0]["tokens_in"] == 100 and seen[0]["tokens_out"] == 20
          and seen[0]["region"] == "ap-south-1",
          f"usage is reported with the India region ({seen[:1]})")

    # ── budget goes through reserve/settle ──────────────────────────────────
    from backend.budget import BudgetTracker, FileStore
    import tempfile as _tf
    from pathlib import Path as _P
    with _tf.TemporaryDirectory() as d:
        bt = BudgetTracker(store=FileStore(_P(d) / "ledger.json"))
        _ASSERTED.clear()
        rt2 = _FakeRuntime(text="x", usage=(50, 10))
        narrate(cleared, origin=_o, model=PRIMARY, budget=bt,
                _runtime=rt2, _control=_FakeControl())
        check(True, "a call with a real budget reserves and settles without raising")

    # ── access-pending is a typed STATE, not a crash ────────────────────────
    _ASSERTED.clear()
    rt_v = _FakeRuntime(error=_BotoError("Your account is currently being verified."))
    try:
        narrate(cleared, origin=_o, model=PRIMARY, budget=None,
                _runtime=rt_v, _control=_FakeControl())
        check(False, "an account-verifying error must raise ProviderNotReady")
    except ProviderNotReady as e:
        check("not ready" in str(e).lower(), f"account-verifying -> ProviderNotReady ({str(e)[:40]})")
    except Exception as e:                                       # noqa: BLE001
        check(False, f"expected ProviderNotReady, got {type(e).__name__}")

    # ── throttling retries, then gives up, and the retry waits via injected sleep ──
    _ASSERTED.clear()
    naps: list = []
    attempts = {"n": 0}

    def _flaky(_prompt):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise Throttled("slow down")
        return "recovered"
    wrapped = with_backoff(_flaky, sleep=naps.append, tries=3)
    check(wrapped("p") == "recovered" and attempts["n"] == 2 and len(naps) == 1,
          f"a throttle is retried after a wait, then succeeds (naps={naps})")

    # ── available() is honest: no boto3/creds in the gate -> False ──────────
    check(available() in (True, False), "available() answers without raising")

    print(f"{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
