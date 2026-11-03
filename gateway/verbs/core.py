"""Field, Verb and Context; the REST/MCP/CLI name derivations; small shared helpers (dates, as_of, access arguments)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


STRING = "string"
OBJECT = "object"
BOOLEAN = "boolean"
# A list, and it is a separate kind because `mcp_tools()` puts `Field.kind` straight into
# the JSON Schema as the declared type. Declaring a list field OBJECT told every MCP client
# to send `{...}` where the handler reads a list -- a schema that lies about the verb.
ARRAY = "array"
KINDS = (STRING, OBJECT, BOOLEAN, ARRAY)

V2 = "/v2"
MCP_NAMESPACE = "themis"


@dataclass(frozen=True)
class Field:
    name: str
    kind: str = STRING
    required: bool = False
    in_path: bool = False
    describes: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.name!r}: {self.kind!r} is not a field kind; one of "
                             f"{KINDS}. The kind is published as the JSON Schema type, so "
                             f"an unknown one is a contract nobody can read")
        if self.in_path and not self.required:
            raise ValueError(
                f"{self.name!r} is in the path and optional, which cannot be: a URL either "
                f"has that segment or is a different route")


@dataclass(frozen=True)
class Verb:
    name: str
    summary: str
    inputs: tuple[Field, ...]
    method: str = "POST"
    read_only: bool = False
    # Whether this verb is exported as an MCP tool. Read-only verbs are, by default, and
    # this is how one opts OUT without lying about being a write.
    #
    # It exists because the alternative kept being chosen for the wrong reason. Three
    # times now a read-only verb has been wanted that has no business in an agent's
    # toolbox -- a cache hit rate, a failure tally, a list of matters -- and each time the
    # options were to make it a write verb (false), to skip the verb entirely (losing the
    # API), or to widen the MCP policy allowlist, which lives partly in a Project Themis
    # file that must not be edited from here. An explicit flag is the honest fourth.
    mcp: bool = True
    run: Callable[[dict, "Context"], dict] | None = None

    @property
    def body_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.inputs if not f.in_path)

    @property
    def path_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.inputs if f.in_path)

    @property
    def signature(self) -> tuple[tuple[str, bool], ...]:
        """(name, required) for every input, sorted. What parity is measured on."""
        return tuple(sorted((f.name, f.required) for f in self.inputs))


@dataclass
class Context:
    """What a handler is allowed to reach. Injected, so no surface has a private back door."""
    tenant: str = "unknown"
    actor: str = "unknown"
    # 028. The principal's FIRM role (viewer/lawyer/admin), from the authenticated
    # session. Least privilege by default: a caller that does not say is not an admin.
    role: str = "viewer"
    # 028. The matter the current work is filed to, so a run written for a turn in a
    # matter is readable by that matter's members and not only by whoever asked.
    matter_id: str | None = None
    store: object | None = None
    documents: dict = field(default_factory=dict)
    model_for: Callable | None = None
    clock: Callable[[], str] | None = None
    queue: object | None = None
    # V1. Where a vault's bytes live. None means no vault is configured on this
    # deployment, and the vault verbs refuse by name rather than writing nowhere.
    files: object | None = None
    # 026. The cross-tenant AuthLookup (gateway/store.py), for the two PUBLIC_VERBS --
    # auth.login and invites.accept -- which run before any tenant is known. None for
    # every other verb: they already have a tenant-bound `store` and have no business
    # reaching across one.
    auth: object | None = None
    # 026. A store FACTORY, not a store: `auth.login`/`invites.accept` learn the tenant
    # only partway through the handler (after auth_find_login / invite_find_by_token), so
    # the tenant-scoped backend for the session insert or the accepted actor has to be
    # built THEN, not injected up front. Mirrors app.py's own `backend_for` closure.
    backend_for: Callable | None = None
    # 026. The caller's IP, hashed into login_attempts -- never logged or stored raw.
    client_ip: str = ""
    # 026. sha256 of the SESSION token that authenticated this request, carried from
    # Principal.credential_hash so `auth.logout` can revoke exactly this session and no
    # other. Empty for an API-key principal: nothing today lets a key revoke itself here.
    credential_hash: str = ""
    # Whether a document marked test_data may be treated as a synthetic fixture (exempt from
    # the region rule). Set only by in-process callers -- the gate and the CLI self-test --
    # and never by gateway/app.py or the worker, so no API or UI request can enable it:
    # a request's own `test_data` was the caller's word, and sent real contracts abroad.
    synthetic_fixtures: bool = False
    # The steps the last handler built, kept so the QUEUE path can reuse the very code the
    # request path runs instead of a second implementation of it. `_persist_run` fills it.
    # Without this the durable executor would have its own idea of what a run's steps are,
    # and the two would drift the first time either changed.
    last_steps: list = field(default_factory=list)


# ── the three name derivations, each a pure function of the verb name ────────

def rest_path(verb: Verb) -> str:
    """`runs.get` + a run_id path field -> /v2/runs/{run_id}."""
    head = verb.name.replace(".", "/").replace("_", "-")
    segs = [f"{V2}/{head}"]
    tail = [f.name for f in verb.path_fields]
    if verb.name.endswith(".get") or verb.name.endswith(".trace"):
        # runs.get -> /v2/runs/{run_id}; runs.trace -> /v2/runs/{run_id}/trace
        base = verb.name.split(".")[0]
        segs = [f"{V2}/{base}"] + [f"{{{t}}}" for t in tail]
        if verb.name.endswith(".trace"):
            segs.append("trace")
        return "/".join(segs)
    return segs[0] + "".join(f"/{{{t}}}" for t in tail)


def mcp_name(verb: Verb) -> str:
    return f"{MCP_NAMESPACE}.{verb.name}"


def cli_command(verb: Verb) -> str:
    """`runs.get` -> `runs-get`, so a shell word is one token."""
    return verb.name.replace(".", "-").replace("_", "-")


def cli_flag(f: Field) -> str:
    return "--" + f.name.replace("_", "-")


# ── the handlers ─────────────────────────────────────────────────────────────

def _refuse(code: str, detail: str) -> dict:
    return {"status": "REFUSED", "code": code, "detail": detail}


def _now(ctx: Context) -> str:
    if ctx.clock is not None:
        return str(ctx.clock())
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# The human gate. `runs.approve` and `runs.reject` are the only WRITING verbs besides
# documents.upload, and they are excluded from MCP by `mcp_tools` for exactly that reason --
# a tool surface that can approve a finding is a tool surface that can clear a review.
MIN_REASON_CHARS = 10


def _affirmed(value) -> bool:
    """True only for an explicit yes. `bool("false")` is True, so a string is never truthy
    by being non-empty -- a CLI or form that sends "false" must not record a quote as seen."""
    if value is True:
        return True
    return isinstance(value, str) and value.strip().lower() in ("true", "yes")


def _partial_note(class_reason) -> str:
    """The reader-facing half of a PARTIAL document's class_reason: which pages are missing.
    The classifier's own reasoning before it is an operator's note, not the reader's."""
    tail = str(class_reason or "").partition("PARTIAL: ")[2].strip()
    return (tail[:1].upper() + tail[1:] + ".") if tail else "Some pages could not be read."


def _boolean(value, *, default: bool) -> bool | None:
    """A BOOLEAN field as sent: JSON true/false, or the strings "true"/"false" a CLI or
    form sends. Absent is `default`. Anything else is None -- the caller refuses it,
    because guessing which way an ambiguous value meant is how a control fails open."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


def _today(ctx: Context) -> str:
    if ctx.clock is not None:
        return str(ctx.clock())[:10]
    from datetime import date
    return date.today().isoformat()


# Ask "as of" a past date. OFF by default: rebuilt wording is not yet independently verified
# (CLAUDE.md, Verification status), so it stays off until the Legal Lead has reviewed a
# sample of past-date answers. Off means exactly the old refusal.
ASK_AS_OF_ENV = "PLACEDON_ASK_AS_OF"
AS_OF_OFF = "This conversation reads current law only. Ask without as_of."
AS_OF_TASK_ONLY = ("Past dates apply only to research questions about the Companies Act. "
                   "Ask without as_of for this task.")


def _as_of_enabled() -> bool:
    import os
    return (os.getenv(ASK_AS_OF_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


def _law_date(raw, ctx: Context):
    """(a past `date` | None for current law, refusal | None). One rule for every caller."""
    from datetime import date
    from checker.as_of import COMMENCEMENT
    raw = (raw or "").strip() if isinstance(raw, str) else raw
    if not raw or raw == _today(ctx):
        return None, None
    if not isinstance(raw, str):
        return None, _refuse("BAD_REQUEST", "as_of must be a valid YYYY-MM-DD date")
    try:
        asked = date.fromisoformat(raw)
    except ValueError:
        return None, _refuse("BAD_REQUEST", "as_of must be a valid YYYY-MM-DD date")
    if not _as_of_enabled():
        return None, _refuse("AS_OF_UNSUPPORTED", AS_OF_OFF)
    if asked < COMMENCEMENT:
        return None, _refuse("AS_OF_OUT_OF_RANGE", (
            "Past dates start at 1 April 2014, when most of the Companies Act 2013 came into "
            "force. Before that the Companies Act 1956 applied, and we do not hold it."))
    if asked > date.fromisoformat(_today(ctx)):
        return None, _refuse("AS_OF_OUT_OF_RANGE",
                             "That date is in the future. Pick a date up to today.")
    return asked, None


def _long_date(d) -> str:
    return f"{d.day} {d:%B %Y}"


def _access_args(args: dict, *fields: str) -> tuple[dict | None, dict]:
    """The stripped string fields, plus a refusal if any is missing or reason is short."""
    out = {f: str(args.get(f) or "").strip() for f in fields}
    missing = [f for f in fields if not out[f]]
    if missing:
        return _refuse("BAD_REQUEST", f"{', '.join(missing)} required"), out
    if "reason" in out and len(out["reason"]) < MIN_REASON_CHARS:
        return _refuse("REASON_REQUIRED",
                       f"a reason of at least {MIN_REASON_CHARS} characters is recorded with "
                       f"every access change"), out
    return None, out


def _now_iso(ctx: Context) -> str:
    if ctx.clock is not None:
        return str(ctx.clock())
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
