"""events.assess, company facts and the company profile, the compliance calendar."""
from __future__ import annotations

from gateway.verbs.core import Context, _access_args, _refuse, _today


def _events_assess(args: dict, ctx: Context) -> dict:
    """Which bodies of law an event engages, and what can be said about each.

    Read-only and model-free: `checker/events.py` is a fixed table and the obligation
    engine is deterministic, so nothing here reaches a network and there is no residency
    question. That is why it may appear on MCP where runs.approve may not.

    No company profile is taken. The held body is reported as engaged with the obligation
    engine not run, which is a MISSING INPUT rather than a finding that nothing applies --
    a profile is company data and this verb answers a question about a transaction type.
    """
    from checker import events

    key = (args.get("event") or "").strip()
    if not key:
        return _refuse("BAD_REQUEST",
                       f"event is required; one of {sorted(events.BY_KEY)}")
    raw_facts = args.get("facts")
    if raw_facts is None:
        raw_facts = {}
    if not isinstance(raw_facts, dict):
        return _refuse("BAD_REQUEST", "facts must be an object")
    unknown = [k for k in raw_facts if k not in events.FACTS]
    if unknown:
        # Refused rather than ignored: a fact this table does not read is a fact the
        # caller believes changed the answer, and silently dropping it would let them
        # think a body was considered when it was not.
        return _refuse("BAD_REQUEST",
                       f"{sorted(unknown)} are not facts this table reads; one of "
                       f"{list(events.FACTS)}. A fact that is silently ignored reads as "
                       f"one that was taken into account.")

    # Company facts (PLAN_26 S2-alt): typed by the user, or read from a master-data page
    # they uploaded. ONLY THE CONFIRMED ONES REACH THE TABLE, and the rest are reported.
    from checker.sources import company_facts as cf
    from_profile = args.get("company_facts") is None
    if from_profile:
        facts, refusal = _profile_facts(ctx), None
        if facts is None:
            # Refused, not assessed without it: a listed firm's assessment would silently
            # lose its SEBI bodies, and nothing in the result would say why.
            return _refuse("STORAGE_UNAVAILABLE",
                           "Your company profile could not be read just now, so this "
                           "assessment was not made without it. Try again, or send the "
                           "facts with the request.")
    else:
        facts, refusal = _company_facts(args.get("company_facts"))
    if refusal:
        return refusal
    used, recorded, pending = cf.for_event_table(facts)
    if from_profile:
        # The request's own `facts` win over the stored profile: a person who says
        # "assume unlisted" for this one question has not changed the company.
        overridden = sorted(set(used) & set(raw_facts))
        used = {k: v for k, v in used.items() if k not in raw_facts}
    clash = sorted(set(used) & set(raw_facts))
    if clash:
        # A contradiction is refused, not resolved by precedence. A silent winner would
        # hide the fact that the caller told us two different things.
        return _refuse("BAD_REQUEST",
                       f"{clash} given both in `facts` and in `company_facts`. Which one "
                       f"is true is not ours to choose by precedence: send one.")

    try:
        result = events.assess(key, {**raw_facts, **used})
    except events.EventError as e:
        return _refuse("BAD_REQUEST", str(e))

    d = result.to_dict()
    if facts:
        d["company_facts"] = {
            "used": [f.to_dict() for f in cf.confirmed(facts)
                     if f.field in cf.EVENT_TABLE_FIELDS and f.field in used],
            "recorded_not_read": [f.to_dict() for f in recorded],
            "pending_confirmation": [f.to_dict() for f in pending],
        }
        if from_profile:
            d["company_facts"]["from"] = PROFILE_SOURCE
            d["company_facts"]["overridden_by_request"] = overridden
    d["note"] = ("The event table says which bodies of law a transaction ENGAGES. It has "
                 "not been reviewed by a lawyer. No section, figure or deadline is stated "
                 "for any body that is not held. A company fact is never VERIFIED: it is "
                 "either what you told us or what your uploaded document says, and an "
                 "unconfirmed one is not used at all.")
    return d


def _company_facts(raw: object) -> tuple[list, dict | None]:
    """(CompanyFact list, a refusal) from the wire form. Never a partial list.

    A malformed fact is refused rather than dropped: the caller believes every fact they
    sent is being taken into account, and the one they typed wrong is exactly the one whose
    silent absence would mislead them.
    """
    from checker.sources import company_facts as cf

    if raw is None:
        return [], None
    if not isinstance(raw, list):
        return [], _refuse("BAD_REQUEST", "company_facts must be a list of objects")
    out = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return [], _refuse("BAD_REQUEST", f"company_facts[{i}] must be an object")
        try:
            if item.get("basis", cf.USER_FACT) == cf.USER_FACT:
                fact = cf.user_fact(item.get("field") or "", item.get("value"))
                if item.get("confirmed"):
                    fact = cf.CompanyFact(**{**fact.__dict__, "confirmed": True})
            else:
                fact = cf.CompanyFact(
                    field=item.get("field") or "", value=str(item.get("value") or ""),
                    basis=item.get("basis") or "",
                    quoted_span=item.get("quoted_span") or "",
                    source_label=item.get("source_label") or "",
                    confirmed=bool(item.get("confirmed")))
        except cf.FactError as e:
            return [], _refuse("BAD_REQUEST", f"company_facts[{i}]: {e}")
        out.append(fact)
    return out, None


PROFILE_SOURCE = "company_profile"


def _profile_facts(ctx: Context) -> list | None:
    """The firm's stored, confirmed company facts, [] when none are stored or the store
    predates 032, and None when the read FAILED -- logged, and never the same as "no
    profile": events.assess refuses on None, ask (which only shows the facts) shows none."""
    if ctx.store is None or not hasattr(ctx.store, "read_company_profile"):
        return []
    from gateway import company_profile as cp
    try:
        return cp.as_company_facts(ctx.store.read_company_profile())
    except Exception as e:                                       # noqa: BLE001
        import logging
        logging.getLogger("gateway.verbs").warning("company profile unreadable: %s", type(e).__name__)
        return None


def _company_profile_get(args: dict, ctx: Context) -> dict:
    """The firm's company profile: each confirmed fact with where it came from."""
    from gateway import company_profile as cp
    if ctx.store is None:
        return _refuse("NO_STORE", "the company profile is durable; it needs a store")
    rows = ctx.store.read_company_profile()
    return {"facts": [cp.public(r) for r in rows], "fields": list(cp.FIELDS),
            "note": ("One profile per firm. Each fact is what a person in your firm "
                     "confirmed, typed by hand or read from an MCA master-data page you "
                     "uploaded. None is VERIFIED against the MCA register.")}


def _company_profile_set(args: dict, ctx: Context) -> dict:
    """Replace the firm's company profile with these confirmed facts.

    A fact left out is superseded (kept, marked replaced); an unchanged fact keeps who
    confirmed it and when. Nothing is deleted.
    """
    from gateway import company_profile as cp
    if ctx.store is None:
        return _refuse("NO_STORE", "the company profile is durable; it needs a store")
    refusal, a = _access_args(args, "reason")
    if refusal:
        return refusal
    rows, err = cp.parse(args.get("facts"))
    if err:
        return _refuse("BAD_REQUEST", err)
    from gateway.store import StoreError
    try:
        stored = ctx.store.set_company_profile(rows, by_actor=ctx.actor, reason=a["reason"])
    except StoreError as e:
        return _refuse("CONFLICT", f"the profile was not saved: {e}")
    return {"status": "SAVED", "facts": [cp.public(r) for r in stored]}


def _company_facts_extract(args: dict, ctx: Context) -> dict:
    """Read an MCA Company Master Data page the USER uploaded. Nothing is used until
    they confirm each field.

    Takes TEXT, not a PDF path. Two reasons, and neither is laziness: a path argument on a
    served verb is a file-read primitive pointed at our own disk, and `checker/pdf_pages`
    is offline tooling whose own test asserts the served path imports no PDF reader. The
    PDF -> text step is `mca_master_data.parse_pdf`, which raises CannotRead on a scan; a
    scan that reaches here as empty text is refused by the same rule one layer up.
    """
    from checker.sources import mca_master_data as mca

    text = args.get("text") or ""
    uploaded_on = (args.get("uploaded_on") or "").strip()
    if not text.strip():
        return _refuse("CANNOT_READ",
                       "no text was supplied. If the upload was a scan or a photograph it "
                       "has no text layer, and we will not return an empty set of facts "
                       "for it: 'we could not read this page' and 'this company has no "
                       "details' must never be the same answer.")
    if not uploaded_on:
        return _refuse("BAD_REQUEST",
                       "uploaded_on (YYYY-MM-DD) is required: a document fact is labelled "
                       "with the date the user uploaded it")
    try:
        parsed = mca.parse_text(text, uploaded_on=uploaded_on)
    except mca.CannotRead as e:
        return _refuse("CANNOT_READ", str(e))
    except mca.PersonalDataLeak as e:                              # pragma: no cover
        return _refuse("PERSONAL_DATA", str(e))

    d = parsed.to_dict()
    d["confirm_required"] = True
    d["tier"] = "CLIENT"
    d["note"] = (d["note"] + " The document is tier CLIENT -- your own upload -- and each "
                 "fact is tier COMPANY_FACT. Neither can make an answer VERIFIED. This "
                 "engine never fetches from mca.gov.in; you downloaded this page yourself.")
    return d


def _calendar_upcoming(args: dict, ctx: Context) -> dict:
    """What falls due in the next 90 days, and what cannot be dated. 8c.

    Read-only, and `mcp=False` -- which here is a LIMITATION and not a principle, so it is
    said plainly: a compliance calendar is a reasonable thing for an agent to read. The
    MCP policy allowlist is partly in a Project Themis file whose tool count is hardcoded
    and which must not be edited from here, so a new MCP tool cannot be added from this
    side of the repository at all. When that is resolved, flip this flag.
    """
    from datetime import date as _date

    from checker import compliance_calendar as cal
    from checker import obligations as ob
    from checker import section_index
    from checker.sarvam_model import html_to_text

    as_of_raw = (args.get("as_of") or "").strip() or _today(ctx)
    try:
        as_of = _date.fromisoformat(as_of_raw[:10])
    except ValueError:
        return _refuse("BAD_REQUEST", f"as_of must be YYYY-MM-DD, got {as_of_raw!r}")
    horizon = args.get("horizon_days")
    try:
        horizon = int(horizon) if horizon else cal.HORIZON_DAYS
    except (TypeError, ValueError):
        return _refuse("BAD_REQUEST", "horizon_days must be a whole number of days")

    # `company`, NOT `company_facts`. They are different vocabularies and conflating them
    # fails for every caller: `company_facts` is the MCA master-data channel
    # (checker/sources/company_facts.py) with a fixed field list -- cin, name, status, roc,
    # address, state, incorporated_on, listed -- and its own personal-data rules. The
    # obligations register wants a CompanyProfile: company_class, paid_up_capital,
    # director_count and the rest. Asking for one and reading the other produced a refusal
    # naming fields the caller never sent.
    raw_company = args.get("company")
    if raw_company is not None and not isinstance(raw_company, dict):
        return _refuse("BAD_REQUEST", "company must be an object of profile fields")
    supplied = {k: v for k, v in (raw_company or {}).items()
                if k in ob.CompanyProfile.__dataclass_fields__ and k != "as_of"}
    unknown_fields = sorted(set(raw_company or {}) - set(supplied) - {"as_of"})
    if unknown_fields:
        return _refuse("BAD_REQUEST",
                       f"{unknown_fields} are not CompanyProfile fields. Refused rather "
                       f"than ignored: a caller who sent one believes it was taken into "
                       f"account")
    # The three the register cannot proceed without. Refused BY NAME rather than
    # defaulted: a calendar built on an assumed company class would date duties that may
    # not attach at all, which is the guessed date this job exists to prevent, one layer up.
    needed = [k for k in ("company_class", "incorporation_date") if not supplied.get(k)]
    if needed:
        return _refuse("BAD_REQUEST",
                       f"a calendar needs {', '.join(needed)} before any duty can be "
                       f"decided. These are not defaulted: an assumed company class would "
                       f"date duties that may not attach at all")
    try:
        supplied["incorporation_date"] = _date.fromisoformat(
            str(supplied["incorporation_date"])[:10])
    except ValueError:
        return _refuse("BAD_REQUEST", "incorporation_date must be YYYY-MM-DD")
    profile = ob.CompanyProfile(as_of=as_of, **supplied)
    rows = ob.build(profile)

    # Anchors come from the CALLER, as dates they have actually supplied. Nothing here
    # derives an anchor from another fact: that is how a guessed date gets in.
    anchors = {}
    for label, raw in (args.get("anchors") or {}).items():
        try:
            anchors[str(label)] = _date.fromisoformat(str(raw)[:10])
        except (TypeError, ValueError):
            return _refuse("BAD_REQUEST",
                           f"anchor {label!r} is not a date: {raw!r}. A calendar never "
                           f"guesses one")

    # The provision's own text, read from the corpus. An obligation whose section is not
    # held has no text, and `upcoming` records NO_INTERVAL rather than assuming a period.
    texts = {}
    for row in rows:
        number = str(row.provision or "").split("s.")[-1].split("(")[0].strip()
        rec = section_index.section_by_number(number) if number else None
        if rec:
            texts[row.obligation_id] = html_to_text(rec.get("content") or "")

    out = cal.upcoming(rows, anchors=anchors, source_texts=texts,
                       intervals=args.get("intervals") or {}, as_of=as_of,
                       horizon_days=horizon).to_dict()
    out["anchors_supplied"] = sorted(anchors)
    return out
