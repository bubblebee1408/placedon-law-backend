"""Writing a run record (_persist_run) and the law versions it pins."""
from __future__ import annotations

from gateway.verbs.core import Context


def law_versions_of(paths) -> dict[str, str]:
    """{repo-relative path: git blob id} of the held text a run READ. PLAN_23 layer 10.

    A law version is the hash of the text applied, in the form `public_only.Origin.blob`
    already uses, so O7 recall and the O9 cache compare one identity. Computed from the
    bytes on disk (git's own blob formula), not from HEAD: it records what was read.
    A path that cannot be read raises -- a missing version is not an empty one.
    """
    # DELEGATED to checker/law_versions, which is where the formula now lives once -- Ring 0
    # may not import Ring 2, so this is the legal direction. It used to be a second copy of
    # git's blob formula, and move 6 was about to add a THIRD under a different name.
    from checker.law_versions import blob_ids
    return blob_ids(paths)


# What review_document applies. The checks are CODE (checker/ss/defects.py) and that is a
# behaviour version, not a law version; the standards they encode are these two texts. Both
# are recorded whatever the meeting kind: an over-broad recall is a re-review, an under-broad
# one is a stale approval nobody is told about.
SS_TEXTS = ("corpus/reference/SS-1.txt", "corpus/reference/SS-2.txt")


def _persist_run(ctx: Context, *, intent: str, status: str, steps: list,
                 propositions: list, refusal_code=None,
                 law_versions: dict | None = None,
                 entailed=None, traced: int = 0, sentences: int = 0,
                 escalations: int = 0) -> str | None:
    """Write one run as runs + ordered steps + propositions. Returns the run id, or None.

    R-016's DERIVATION model, actually used: without this a verb answers and leaves no
    trace, and `runs.trace` has nothing to serve. A store that is absent is not an error
    here -- the verb still answered -- but the caller is told the id is None rather than
    handed one that resolves to nothing.
    """
    ctx.last_steps = list(steps)
    if ctx.store is None:
        return None
    import uuid
    run_id = str(uuid.uuid4())
    score, why = nonconformity_for(entailed=entailed, traced=traced, total=sentences,
                                   escalations=escalations)
    ctx.store.write({"id": run_id, "intent": intent, "status": status,
                     "actor_id": ctx.actor, "matter_id": ctx.matter_id,
                     "refusal_code": refusal_code, "law_versions": law_versions,
                     "steps": steps, "propositions": propositions,
                     "nonconformity": score, "nonconformity_note": why})
    return run_id


def nonconformity_for(*, entailed, traced, total, escalations: int = 0) -> tuple:
    """(score, note) for a run, from `checker/calibration.nonconformity`. CAL-1.

    `entailed` is the count of sentences that passed ENTAILMENT, and it is deliberately a
    separate argument from `traced`. A sentence can quote a real span at real offsets and
    still assert something the span does not say -- `checker/lawyer_summary.py` says
    exactly that, and declares its ENTAILED verdict reserved and never returned.

    So when `entailed` is None the score is NOT computed and the note says why. Scoring
    from `traced` alone would be a different measurement under the same name, and it is
    the one every threshold would later be computed from.
    """
    from checker.calibration import nonconformity
    if not total:
        return None, None                 # nothing ran; NULL, with nothing to explain
    if entailed is None:
        return None, (
            f"not computed: {traced} of {total} sentence(s) byte-matched, but this path "
            f"produces no entailment verdict (checker/lawyer_summary.py declares ENTAILED "
            f"reserved and never returned), and the score needs both. Scoring from the "
            f"byte match alone would be a different measurement under the same name.")
    return nonconformity(verified=int(entailed), total=int(total),
                         escalations=int(escalations))
