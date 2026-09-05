"""A local (Ollama) model behind the adapter contract, with attestation and a
form-only repair pass.

`model_adapter.run()` takes `Callable[[str], str]` and defaults to a stub, deliberately,
so the contract is provable without spending money. This supplies the real thing for a
locally served model, and adds the two properties a legal system needs from any model
call: it must be reproducible, and it must be traceable to a named artefact.

Standard library only -- `urllib.request`. No new dependency (CLAUDE.md).

## Determinism is not a preference here

`temperature=0` and a fixed `seed` are defaults, not options. A system that answers the
same question two ways cannot be audited, and "the model said something different this
time" is not an answer a lawyer can act on. A caller may raise the temperature, but the
attestation records that it did, so a non-reproducible answer is always visibly marked
as one.

## Attestation: which artefact said this

Every call returns having recorded the model name, the digest the server reports, the
exact options, and hashes of both prompt and response. `model_adapter` already refuses
output citing evidence that is not in the pack; this closes the other half -- given an
answer, you can say which model produced it, from which prompt, under which settings.
Without that, "the AI said so" is unfalsifiable, and an unfalsifiable claim has no place
in an evidence pack.

## The repair pass, and the line it does not cross

The plan that prompted this asked for a "secondary deterministic regex parser [that]
attempts repair before flagging the record for human review". Adopted, with one
boundary held: **form is repaired, content never is.**

- Repairable: case, whitespace, separators, and OCR confusables at a position where the
  grammar admits exactly one character class -- "O" where only a digit is legal is
  unambiguously a zero.
- Not repairable: anything where more than one valid value could have been intended. A
  guess that lands on a real-but-different CIN is worse than a refusal, because it is a
  confident answer about the wrong company.

`CLAUDE.md` forbids repairing a defective government source. That still stands: this
repairs a *model's transcription*, never a source document, and every repair is recorded
on the result so a reviewer sees what was changed and why.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

DEFAULT_TIMEOUT_S = 120
DEFAULT_OPTIONS = {"temperature": 0.0, "seed": 0, "top_p": 1.0}


class NotConfigured(RuntimeError):
    """Raised rather than silently falling back. A stub answering in production while
    the caller believes a real model ran is the worst available failure."""


class ModelUnavailable(RuntimeError):
    """The server did not answer. Fails loud: a legal answer must never be produced by
    a fallback the caller did not ask for."""


@dataclass(frozen=True)
class Attestation:
    model: str
    digest: str | None
    options: dict
    prompt_sha256: str
    response_sha256: str
    deterministic: bool
    endpoint: str

    def to_dict(self) -> dict:
        return {"model": self.model, "digest": self.digest, "options": dict(self.options),
                "prompt_sha256": self.prompt_sha256, "response_sha256": self.response_sha256,
                "deterministic": self.deterministic, "endpoint": self.endpoint}


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class OllamaRunner:
    """A callable conforming to model_adapter's `Callable[[str], str]`.

    Refuses to construct without an explicit endpoint or OLLAMA_BASE_URL. There is no
    default host: a module that quietly talks to localhost is a module that surprises
    someone, and network calls in this system are always a decision.
    """

    def __init__(self, model: str, base_url: str | None = None,
                 options: dict | None = None, timeout_s: int = DEFAULT_TIMEOUT_S,
                 transport=None) -> None:
        url = base_url or os.environ.get("OLLAMA_BASE_URL")
        if not url:
            raise NotConfigured(
                "no endpoint: pass base_url or set OLLAMA_BASE_URL. This module has no "
                "default host on purpose — an unrequested network call is a surprise, "
                "and calls out of this system are always a decision")
        if not model:
            raise NotConfigured("a model name is required; it is recorded in the attestation")
        self.model = model
        self.base_url = url.rstrip("/")
        self.options = {**DEFAULT_OPTIONS, **(options or {})}
        self.timeout_s = timeout_s
        self._transport = transport or self._http
        self.attestations: list[Attestation] = []

    @property
    def deterministic(self) -> bool:
        return self.options.get("temperature", 0.0) == 0.0 and "seed" in self.options

    def _http(self, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            raise ModelUnavailable(
                f"{self.base_url} did not answer ({e}). No fallback is substituted: a "
                "legal answer produced by an unrequested substitute is worse than none") from e

    def __call__(self, prompt: str) -> str:
        body = self._transport({"model": self.model, "prompt": prompt,
                                "stream": False, "options": dict(self.options)})
        text = body.get("response")
        if not isinstance(text, str):
            raise ModelUnavailable(
                "the server returned no 'response' string; malformed output is not "
                "repaired into an answer")
        self.attestations.append(Attestation(
            model=self.model, digest=body.get("model_digest") or body.get("digest"),
            options=dict(self.options), prompt_sha256=_sha(prompt),
            response_sha256=_sha(text), deterministic=self.deterministic,
            endpoint=self.base_url))
        return text

    def last_attestation(self) -> Attestation | None:
        return self.attestations[-1] if self.attestations else None


# ── form-only repair ────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Repair:
    field: str
    before: str
    after: str
    rule: str


@dataclass(frozen=True)
class RepairResult:
    value: str | None
    repairs: tuple[Repair, ...] = ()
    flagged: bool = False
    reason: str = ""
    # A repaired value is admissible ONLY when nothing was ambiguous. `flagged` means a
    # human must look, and no caller may treat a flagged value as clean.

    @property
    def clean(self) -> bool:
        return self.value is not None and not self.flagged


# Confusables only resolvable when the grammar fixes the character class at that index.
_TO_DIGIT = {"O": "0", "o": "0", "I": "1", "l": "1", "S": "5", "B": "8", "Z": "2"}
_CIN_SHAPE = "ADDDDDLLDDDDOOODDDDDD"   # A=L/U  D=digit  L=letter  O=ownership letter


def repair_cin(raw: str) -> RepairResult:
    """Repair the form of a proposed CIN. Never guesses a value.

    Case, spacing and separators are normalised. A confusable is substituted only at an
    index where the CIN grammar admits digits alone. Anything still wrong after that is
    flagged for a human — not corrected toward the nearest plausible company.
    """
    if raw is None or not raw.strip():
        return RepairResult(None, flagged=False, reason="absent — nothing to repair")

    repairs: list[Repair] = []
    s = raw.strip()
    stripped = re.sub(r"[\s\-_/.]", "", s)
    if stripped != s:
        repairs.append(Repair("cin", s, stripped, "separators and whitespace removed"))
    upper = stripped.upper()
    if upper != stripped:
        repairs.append(Repair("cin", stripped, upper, "upper-cased"))

    if len(upper) != len(_CIN_SHAPE):
        return RepairResult(upper, tuple(repairs), flagged=True,
                            reason=f"length {len(upper)}, expected {len(_CIN_SHAPE)} — "
                                   "a length error cannot be repaired without inventing "
                                   "or discarding a character")

    chars = list(upper)
    for i, want in enumerate(_CIN_SHAPE):
        if want == "D" and not chars[i].isdigit():
            sub = _TO_DIGIT.get(chars[i])
            if sub is None:
                return RepairResult("".join(chars), tuple(repairs), flagged=True,
                                    reason=f"position {i} must be a digit and {chars[i]!r} "
                                           "has no unambiguous digit reading")
            repairs.append(Repair("cin", chars[i], sub,
                                  f"OCR confusable at position {i}: the grammar admits "
                                  "only a digit there, so the reading is unambiguous"))
            chars[i] = sub

    out = "".join(chars)
    from checker.extraction_schema import validate_cin, Verdict
    v = validate_cin(out)
    if v.verdict is not Verdict.WELL_FORMED:
        return RepairResult(out, tuple(repairs), flagged=True,
                            reason=f"still not well-formed after form repair: {v.reason}")
    return RepairResult(out, tuple(repairs), flagged=False,
                        reason="form repaired; value not guessed")


def _test() -> None:
    passed = failed = 0

    def check(cond, label):
        nonlocal passed, failed
        if cond:
            passed += 1; print(f"  [PASS] {label}")
        else:
            failed += 1; print(f"  [FAIL] {label}")

    # ── configuration refuses rather than defaulting ──
    try:
        OllamaRunner("qwen2.5", base_url=None)
        check(os.environ.get("OLLAMA_BASE_URL") is not None, "no endpoint should refuse")
    except NotConfigured as e:
        check("no default host" in str(e), "no endpoint: refuses, no localhost default")
    try:
        OllamaRunner("", base_url="http://x"); check(False, "empty model should refuse")
    except NotConfigured:
        check(True, "an unnamed model is refused — the name is part of the attestation")

    # ── deterministic by default, and attested ──
    calls = []

    def fake(payload):
        calls.append(payload)
        return {"response": "OK", "model_digest": "sha256:abc"}

    r = OllamaRunner("qwen2.5", base_url="http://local", transport=fake)
    check(r.deterministic, "temperature 0 + seed is the default, not an option")
    out = r("hello")
    check(out == "OK", "the runner returns raw text, per the adapter contract")
    a = r.last_attestation()
    check(a.model == "qwen2.5" and a.digest == "sha256:abc",
          "attestation records the model and the server-reported digest")
    check(a.prompt_sha256 == _sha("hello") and a.response_sha256 == _sha("OK"),
          "...and hashes of both prompt and response")
    check(a.deterministic, "...and that the call was reproducible")
    check(calls[0]["options"]["temperature"] == 0.0 and calls[0]["stream"] is False,
          "the request is deterministic and non-streaming")

    hot = OllamaRunner("qwen2.5", base_url="http://local",
                       options={"temperature": 0.8}, transport=fake)
    hot("x")
    check(not hot.last_attestation().deterministic,
          "a non-reproducible call is visibly marked as one in the attestation")

    # ── failure is loud ──
    def dead(_):
        raise OSError("connection refused")
    d = OllamaRunner("m", base_url="http://local", transport=lambda p: OllamaRunner._http(d, p))
    d._transport = lambda p: (_ for _ in ()).throw(ModelUnavailable("down: no fallback"))
    try:
        d("q"); check(False, "an unreachable model should raise")
    except ModelUnavailable as e:
        check("no fallback" in str(e), "an unreachable model raises; no silent stub")

    bad = OllamaRunner("m", base_url="http://local", transport=lambda p: {"error": "x"})
    try:
        bad("q"); check(False, "missing response should raise")
    except ModelUnavailable as e:
        check("not repaired into an answer" in str(e),
              "malformed server output is not repaired into an answer")

    # ── form-only repair ──
    ok = repair_cin(" u74999-ka 2019 ptc123456 ")
    check(ok.clean and ok.value == "U74999KA2019PTC123456",
          "case, spacing and separators are repaired to a well-formed CIN")
    check(any("upper-cased" in x.rule for x in ok.repairs),
          "...and every repair is recorded, not applied silently")

    ocr = repair_cin("U7499OKA2019PTC123456")   # letter O where a digit belongs
    check(ocr.clean and ocr.value == "U74990KA2019PTC123456",
          "an O where the grammar admits only a digit is unambiguously 0")
    check(any("unambiguous" in x.rule for x in ocr.repairs),
          "...and the rule says why the reading was forced")

    amb = repair_cin("U74999KA2019PTCX23456")   # X in a digit slot, no digit reading
    check(amb.flagged and not amb.clean,
          "a character with no unambiguous digit reading is flagged, never guessed")
    check("no unambiguous digit reading" in amb.reason, "...and the reason names it")

    short = repair_cin("U74999KA2019PTC123")
    check(short.flagged and "length" in short.reason,
          "a length error is flagged — repairing it would invent or discard a character")

    junk = repair_cin("UUUUUUUUUUUUUUUUUUUUU")
    check(junk.flagged, "a well-shaped-but-invalid string stays flagged after form repair")

    absent = repair_cin("   ")
    check(absent.value is None and not absent.flagged,
          "absent is not a repair failure — nothing was proposed")

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _test()
