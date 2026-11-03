"""One verb table. Three surfaces generated from it, and a test that they cannot drift.

PLAN_22 D6: "One verb table generates REST API, MCP tools and a CLI, with a parity test,
so the three surfaces cannot drift into three products."

The failure being prevented is specific and ordinary: someone adds an argument to the REST
route, the CLI keeps five flags, and the MCP tool keeps four. Nothing breaks, nobody
notices, and six months later the three surfaces disagree about what the product does.
The parity test does not compare a hand-kept list against another hand-kept list -- it
GENERATES all three from `VERBS` and compares the generated shapes, so a surface can only
drift by someone editing this table, which is the point.

## What a verb is

A name, a summary, and its inputs. Everything a surface needs is derived:

    REST   POST /v2/ask                 dotted name -> a path, path fields interpolated
    MCP    themis.ask                   dotted name -> the existing themis.* namespace
    CLI    placedon ask --question ...  dotted name -> a subcommand, inputs -> flags

`read_only` is not decoration: checker/mcp/policy.py asserts READ_ONLY_TOOLS ==
KNOWN_TOOLS, so a verb that writes must be kept out of the MCP surface until that policy
is deliberately widened, and `mcp_tools()` enforces it rather than trusting the author.

Run: PYTHONPATH=. python3 gateway/verbs/__main__.py   (or: python3 -m gateway.verbs)

## Layout

One module per domain. Each imports what it uses from the others explicitly; this
`__init__` re-exports the public names, `VERBS`, and the private handlers other code
imports, so `from gateway.verbs import X` works as it did when this was one file.

    core          Field, Verb, Context; REST/MCP/CLI name derivations; shared helpers
    model_access  the budget ledger and which provider may serve which task
    run_records   writing a run record, and the law versions it pins
    ask           the research question path and its decomposition (O5)
    ask_layers    the critic (layer 7) and the answer cache (O9)
    research      research.multi (F2), sources, case law, web, forecast (Lane B)
    runs          runs.*, approve/reject, the durable queue (O2)
    review        review.contract, review.document
    company       events.assess, company facts and profile, compliance calendar
    conversation  the conversation layer (C2): intake, routing, send/get/list
    answers       bodies of law, the answer envelope, findings, citations
    documents     documents.upload, summaries, document.verify/check
    vault         the vault (V1)
    matters       matters and matter-access administration (028)
    admin         dead jobs, usage
    review_table  review tables (H4) and the per-cell job
    drafts        drafts (H3) and draft prose
    people        sign-in, sessions, invites (026); people and invites (036)
    registry      the VERBS table and rest_spec / mcp_tools / cli_spec / write_verbs
    selftest      `_test()` (the gate suite) and `_live_smoke()` (--live)

## Patching in tests

Patch a name where it is looked up, not here: a re-export is a second binding. Names that
are patched are always looked up through their owning module, so one patch reaches every
caller: `gateway.verbs.model_access._ledger`, `._served_or_refusal`, `._typed_text_origin`;
`gateway.verbs.ask_layers._critic_for`; `gateway.verbs.documents._resolve_conversation_documents`.
`gateway.verbs.queue_handlers` is the one the worker reads (it imports it from here).
"""
from __future__ import annotations

from gateway.verbs.core import (ARRAY, ASK_AS_OF_ENV, AS_OF_OFF, AS_OF_TASK_ONLY, BOOLEAN,
    Context, Field, KINDS, MCP_NAMESPACE, MIN_REASON_CHARS, OBJECT, STRING, V2, Verb,
    _partial_note, cli_command, cli_flag, mcp_name, rest_path)
from gateway.verbs.model_access import (AZURE_OPT_IN_TASKS, ON_DEVICE_TASKS, TASK_PROVIDERS,
    _ledger, _served_or_refusal, task_providers)
from gateway.verbs.run_records import SS_TEXTS, law_versions_of, nonconformity_for
from gateway.verbs.ask import _ask
from gateway.verbs.ask_layers import _cache_lookup, cache_stats
from gateway.verbs.research import _sources_report
from gateway.verbs.runs import (INTERNAL_INTENTS, QUEUED_INTENTS, STORE_WRITING_INTENTS,
    _runs_submit, queue_handlers)
from gateway.verbs.review import _review_contract
from gateway.verbs.company import PROFILE_SOURCE, _calendar_upcoming
from gateway.verbs.conversation import (CONVERSATION_UNAVAILABLE, DRAFT_SOURCE_TASK,
    MAX_CONVERSATION_CHARS, MAX_CONVERSATION_FILES, TASK_INTENT, TASK_VERB, _conversation_get,
    _conversation_send, _names_own_subject, _reconcile_message, _task_args, _turn_metadata)
from gateway.verbs.answers import (_citation_get, _envelope_for, _provision_citations,
    verify_citation)
from gateway.verbs.documents import (SUMMARY_UNAVAILABLE_WHY, VERIFY_CHECK_NAMES,
    VERIFY_NEEDS_PERMISSION, VERIFY_PERMISSION_NOTE, _document_summary_job,
    _summary_call_failure, _summary_unavailable)
from gateway.verbs.vault import (VERIFY_BYTES_PRESENT, VERIFY_FAIL, VERIFY_HASH_MATCHES,
    VERIFY_NOT_DELETED, VERIFY_NOT_RUN, VERIFY_PASS, _vault_compile, _vault_delete,
    _vault_find, _vault_ingest_job, _vault_list, _vault_retry, _vault_upload, _vault_verify)
from gateway.verbs.matters import MATTER_ID_UNUSABLE, _vault_share
from gateway.verbs.review_table import (MAX_DOCUMENT_NAME, MAX_GRID_CELLS, _cell_answerer,
    _review_grid_cell, _review_table_create, _review_table_list, _review_table_status)
from gateway.verbs.drafts import (DRAFT_KIND_UNKNOWN, _draft_create, _draft_export,
    _draft_history, _draft_prose, _draft_revise, _draft_versions)
from gateway.verbs.registry import VERBS, by_name, cli_spec, mcp_tools, rest_spec, write_verbs

# What this package re-exports (so linters and type checkers see the imports above
# as re-exports, not as unused).
__all__ = ["ARRAY", "ASK_AS_OF_ENV", "AS_OF_OFF", "AS_OF_TASK_ONLY", "AZURE_OPT_IN_TASKS",
    "BOOLEAN", "CONVERSATION_UNAVAILABLE", "Context", "DRAFT_KIND_UNKNOWN",
    "DRAFT_SOURCE_TASK", "Field", "INTERNAL_INTENTS", "KINDS", "MATTER_ID_UNUSABLE",
    "MAX_CONVERSATION_CHARS", "MAX_CONVERSATION_FILES", "MAX_DOCUMENT_NAME", "MAX_GRID_CELLS",
    "MCP_NAMESPACE", "MIN_REASON_CHARS", "OBJECT", "ON_DEVICE_TASKS", "PROFILE_SOURCE",
    "QUEUED_INTENTS", "SS_TEXTS", "STORE_WRITING_INTENTS", "STRING", "SUMMARY_UNAVAILABLE_WHY",
    "TASK_INTENT", "TASK_PROVIDERS", "TASK_VERB", "V2", "VERBS", "VERIFY_BYTES_PRESENT",
    "VERIFY_CHECK_NAMES", "VERIFY_FAIL", "VERIFY_HASH_MATCHES", "VERIFY_NEEDS_PERMISSION",
    "VERIFY_NOT_DELETED", "VERIFY_NOT_RUN", "VERIFY_PASS", "VERIFY_PERMISSION_NOTE", "Verb",
    "_ask", "_cache_lookup", "_calendar_upcoming", "_cell_answerer", "_citation_get",
    "_conversation_get", "_conversation_send", "_document_summary_job", "_draft_create",
    "_draft_export", "_draft_history", "_draft_prose", "_draft_revise", "_draft_versions",
    "_envelope_for", "_ledger", "_names_own_subject", "_partial_note", "_provision_citations",
    "_reconcile_message", "_review_contract", "_review_grid_cell", "_review_table_create",
    "_review_table_list", "_review_table_status", "_runs_submit", "_served_or_refusal",
    "_sources_report", "_summary_call_failure", "_summary_unavailable", "_task_args",
    "_turn_metadata", "_vault_compile", "_vault_delete", "_vault_find", "_vault_ingest_job",
    "_vault_list", "_vault_retry", "_vault_share", "_vault_upload", "_vault_verify", "by_name",
    "cache_stats", "cli_command", "cli_flag", "cli_spec", "law_versions_of", "mcp_name",
    "mcp_tools", "nonconformity_for", "queue_handlers", "rest_path", "rest_spec",
    "task_providers", "verify_citation", "write_verbs"]
