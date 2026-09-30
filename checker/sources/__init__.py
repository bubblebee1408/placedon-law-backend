"""Every source behind one interface, and every result carrying the tier that limits it.

S1 of `docs/PLAN_24_INDIAN_SOURCES.md` (H1 of `.claude/loops/DECISION_harvey_parity.md`).
This package is the contract; `terms.py` is what the sources permit; `held.py` and
`client.py` are the only two adapters that exist yet.

## The one rule

**Only HELD can make an answer VERIFIED.** HELD is our own hash-stamped corpus, checked
against India Code and carrying known defects in `docs/SOURCE_DEFECTS.md`. A judgment found
on Indian Kanoon, a circular read off sebi.gov.in this morning, a company's own disclosure
and the client's own contract are all real evidence about the world and none of them is law
we have verified. The tier is set by the connector's code and never by a model (PLAN_24 §2).

SEBI asks for this rule itself: its website policy says its content "should not be construed
as a statement of law or used for any legal purposes".

The rule is enforced in three places on purpose, because one of them is not enough:

    tiers.can_verify()      the predicate
    Evidence.can_verify     per result, so a mixed pack cannot be summarised wrongly
    checker/rings.py        `checker.sources` is Ring 2, so no Ring 0 decider may even
                            IMPORT a connector -- the firewall, not the good intentions

## What a connector must have before it loads

A terms record in `terms.py`, unless its tier is HELD or CLIENT. Those two are exempt
because they are not fetches: HELD is our corpus and CLIENT is the tenant's own upload, and
there is no third party whose terms could govern either. Every other tier reaches someone
else's server, so `load()` refuses without a record — and, after S0, refuses for five of
the seven sources that do have one.

The five rules this package must obey are tested in `contract.py`, as one suite,
because each spans two or three modules.

Run: PYTHONPATH=. python3 checker/sources/contract.py --test
"""
from __future__ import annotations

from checker.sources.tiers import (HELD, OFFICIAL_LIVE, LICENSED, COMPANY_FACT, CLIENT, TIERS,
                    VERIFYING_TIERS, ATTRIBUTION_REQUIRED, can_verify, label_for)
from checker.sources.evidence import Evidence, EvidenceError
from checker.sources.base import Source, SourceError, FetchError, load, check_payload, needs_terms
from checker.sources.terms import NoTermsRecord, record_for, may_fetch, may_cache, attribution_for

__all__ = ["HELD", "OFFICIAL_LIVE", "LICENSED", "COMPANY_FACT", "CLIENT", "TIERS",
           "VERIFYING_TIERS", "ATTRIBUTION_REQUIRED", "can_verify", "label_for",
           "Evidence", "EvidenceError", "Source", "SourceError", "FetchError", "load",
           "check_payload", "needs_terms", "NoTermsRecord", "record_for", "may_fetch",
           "may_cache", "attribution_for"]
