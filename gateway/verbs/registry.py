"""The verb table (VERBS) and the three surfaces generated from it."""
from __future__ import annotations

from gateway.verbs.admin import _jobs_dead, _usage_status
from gateway.verbs.answers import _citation_get
from gateway.verbs.ask import _ask
from gateway.verbs.company import (_calendar_upcoming, _company_facts_extract,
    _company_profile_get, _company_profile_set, _events_assess)
from gateway.verbs.conversation import (_conversation_get, _conversation_list,
    _conversation_send, _intake_classify)
from gateway.verbs.core import (ARRAY, BOOLEAN, Context, Field, OBJECT, STRING, Verb,
    cli_command, cli_flag, mcp_name, rest_path)
from gateway.verbs.documents import _document_check, _document_verify, _documents_upload
from gateway.verbs.drafts import (_draft_create, _draft_diff, _draft_export, _draft_list,
    _draft_revise, _draft_status_verb, _draft_versions)
from gateway.verbs.matters import (_access_reassign, _matters_access_report, _matters_create,
    _matters_grant, _matters_list, _matters_members, _matters_revoke, _vault_share)
from gateway.verbs.people import (_auth_login, _auth_logout, _auth_me, _invites_accept,
    _invites_cancel, _invites_create, _invites_list, _people_list)
from gateway.verbs.research import (_forecast_summary, _research_cases, _research_multi,
    _research_web, _sources_list, _sources_search)
from gateway.verbs.review import _review_contract, _review_document
from gateway.verbs.review_table import (_review_table_cancel, _review_table_create,
    _review_table_export, _review_table_list, _review_table_status)
from gateway.verbs.runs import (_runs_approve, _runs_cancel, _runs_get, _runs_preview,
    _runs_reject, _runs_submit, _runs_trace)
from gateway.verbs.vault import (_vault_compile, _vault_delete, _vault_find, _vault_list,
    _vault_research, _vault_retry, _vault_status, _vault_summarize, _vault_upload,
    _vault_verify)


# ── the table ────────────────────────────────────────────────────────────────

VERBS: tuple[Verb, ...] = (
    Verb("ask", "One grounded research question against the held statute. Cited spans or "
                "a named refusal.",
         (Field("question", STRING, True, describes="the question, in plain English"),
          Field("available", ARRAY, False, describes="provider tuple to route over"),
          Field("company_facts", ARRAY, False,
                describes="company facts you are telling us, e.g. "
                          "[{'field':'listed','value':'yes'}]. Labelled 'you told us', "
                          "shown back, never verified, and they do not steer the answer"),
          Field("critic", STRING, False,
                describes="'true' to run the layer-7 critic over the answer's own "
                          "sentences after the verifier. It may FLAG or REMOVE only, at "
                          "most one removal per run (PLAN_23 §1.4), and never rewrites or "
                          "adds. Every removal is in critic.trace"),
          Field("decompose", STRING, False,
                describes="'true' to split a compound question into at most 4 "
                          "sub-questions (PLAN_23 O5), answer each through the verified "
                          "cascade and join only the parts that came back cited. One "
                          "unanswered part makes the whole PARTIAL and is named"),
          Field("sources", ARRAY, False,
                describes="source ids to search, from sources.list (e.g. ['held']). "
                          "Retrieval searches ONLY these. Default = the held corpus plus "
                          "your vault. An unavailable pick (KEY_MISSING / NOT_ACQUIRED / "
                          "BLOCKED) is named, never silently dropped. Only HELD can VERIFY"),
          Field("as_of", STRING, False,
                describes="YYYY-MM-DD from 2014-04-01 to today: read each section as it "
                          "stood on that date, rebuilt from India Code's amendment notes. "
                          "Off unless PLACEDON_ASK_AS_OF is set (AS_OF_UNSUPPORTED)")),
         "POST", read_only=True, run=_ask),

    Verb("research.multi",
         "A compound question split across bodies of law and States, answered body-by-body: "
         "one section per (body, State) with its own status. The Companies Act parts are "
         "answered and quoted; a body we do not hold, or a State topic with no date, is "
         "named -- never squeezed into a single national answer.",
         (Field("question", STRING, True, describes="the compound question, in plain English"),
          Field("as_of", STRING, False,
                describes="an ISO date (YYYY-MM-DD). A State topic such as stamp duty needs "
                          "one, since State rates change over time; without it that part is "
                          "returned NEED_FACT rather than guessed"),
          Field("sources", ARRAY, False,
                describes="source ids to search, from sources.list. Retrieval searches ONLY "
                          "these; default = the held corpus plus your vault. Held parts need "
                          "the held corpus picked; an unavailable pick is named, not dropped")),
         "POST", read_only=True, run=_research_multi),

    Verb("forecast.summary",
         "A predictive signal: how long Companies Act matters take at a forum, from the open "
         "judgment metadata. A Kaplan-Meier median with its interval and n, counting matters "
         "still pending as censored; it ABSTAINS by name when too few have been decided there. "
         "Labelled predictive_signal -- never a statement of law, never a decision about your "
         "matter.",
         (Field("court", STRING, True, describes="the forum, e.g. 'Bombay High Court'"),
          Field("as_of", STRING, False,
                describes="ISO date (YYYY-MM-DD) to censor pending matters at; defaults to today")),
         "POST", read_only=True, run=_forecast_summary),

    Verb("review_contract",
         "A contract against a company playbook. Every finding is a POTENTIAL_ISSUE "
         "against that standard, never a statement of law.",
         (Field("text", STRING, True, describes="the contract text"),
          Field("name", STRING, False, describes="a label for the document"),
          Field("playbook", STRING, False, describes="repo-relative playbook path"),
          Field("test_data", STRING, False,
                describes="ignored on API requests: only an in-process test may mark a "
                          "document as a synthetic fixture (PLAN_22 D3)")),
         "POST", read_only=True, run=_review_contract),

    Verb("runs.get", "One run's status and result, without its steps.",
         (Field("run_id", STRING, True, in_path=True, describes="the run identifier"),),
         "GET", read_only=True, run=_runs_get),

    Verb("runs.trace", "Every step of one run, in order, as persisted.",
         (Field("run_id", STRING, True, in_path=True, describes="the run identifier"),),
         "GET", read_only=True, run=_runs_trace),

    Verb("review_document",
         "A corporate filing against the SS-1/SS-2 checks. The document type is classified "
         "first, in code, and a check that does not apply to that type makes no claim. No "
         "model is called.",
         (Field("text", STRING, True, describes="the document text"),
          Field("name", STRING, False, describes="a label for the document"),
          Field("meeting_kind", STRING, False,
                describes="board or general. Recorded on the run; no check branches on it "
                          "today"),
          Field("meeting_date", STRING, False,
                describes="YYYY-MM-DD. Absent leaves the 30-day entry check unverifiable "
                          "rather than passed"),
          Field("entry_date", STRING, False,
                describes="YYYY-MM-DD, the date the minutes were entered in the book")),
         "POST", read_only=True, run=_review_document),

    Verb("runs.approve",
         "Accept one finding of a run, with a written reason. Stored as labelled data.",
         (Field("run_id", STRING, True, in_path=True, describes="the run identifier"),
          Field("item_ref", STRING, True,
                describes="which finding, as the run served it: 'ss:T1.2', "
                          "'playbook:NDA-08'"),
          Field("reason", STRING, True,
                describes="why, in the reviewer's own words. At least 10 characters: a "
                          "decision with no reason is not a label"),
          Field("quoted_span", STRING, True,
                describes="the text the reviewer was looking at when they decided"),
          Field("quote_viewed", BOOLEAN, False,
                describes="true when the reviewer was shown the quoted text. Required to "
                          "approve (PLAN_23 §1.8); a rejection records it either way")),
         "POST", read_only=False, run=_runs_approve),

    Verb("runs.reject",
         "Reject one finding of a run, with a written reason. Stored as labelled data.",
         (Field("run_id", STRING, True, in_path=True, describes="the run identifier"),
          Field("item_ref", STRING, True,
                describes="which finding, as the run served it: 'ss:T1.2', "
                          "'playbook:NDA-08'"),
          Field("reason", STRING, True,
                describes="why, in the reviewer's own words. At least 10 characters: a "
                          "decision with no reason is not a label"),
          Field("quoted_span", STRING, True,
                describes="the text the reviewer was looking at when they decided"),
          Field("quote_viewed", BOOLEAN, False,
                describes="true when the reviewer was shown the quoted text. Required to "
                          "approve (PLAN_23 §1.8); a rejection records it either way")),
         "POST", read_only=False, run=_runs_reject),

    Verb("runs.submit",
         "Accept a run and return its id immediately. A worker executes it from the "
         "durable queue; the status moves PLANNED -> RUNNING -> final.",
         (Field("intent", STRING, True,
                describes="which intent to run: review_document, review_contract or "
                          "research_question"),
          Field("args", OBJECT, False,
                describes="the arguments that intent's synchronous verb takes")),
         "POST", read_only=False, run=_runs_submit),

    Verb("runs.cancel",
         "Ask a running run to stop at its next step boundary. What is already done stays "
         "in the trace.",
         (Field("run_id", STRING, True, in_path=True, describes="the run identifier"),),
         "POST", read_only=False, run=_runs_cancel),

    Verb("events.assess",
         "Which bodies of law a corporate event engages, and what can be said about each: "
         "the obligation engine for a held body, current text for a current-only body, and "
         "the named refusal for one this corpus does not hold.",
         (Field("event", STRING, True,
                describes="the event key, e.g. share_allotment, related_party_contract"),
          Field("facts", OBJECT, False,
                describes="foreign_investor, listed, state — facts that add bodies"),
          Field("company_facts", ARRAY, False,
                describes="company facts with their basis: typed by you (USER_FACT) or "
                          "read from an MCA master-data page you uploaded (COMPANY_FACT, "
                          "with the quoted span). ONLY THE CONFIRMED ONES ARE USED")),
         "POST", read_only=True, run=_events_assess),

    Verb("sources.list",
         "Every source, its tier, and whether its own terms and robots.txt permit a fetch "
         "-- with the reason when they do not.",
         (),
         "POST", read_only=True, run=_sources_list),

    Verb("sources.search",
         "Search every source that may be read, returning Evidence rows that each carry "
         "their tier. Only a HELD row may support a legal claim.",
         (Field("query", STRING, True, describes="what to look for"),
          Field("tiers", ARRAY, False,
                describes="restrict to these tiers, e.g. ['HELD']. Absent searches all "
                          "loadable sources"),
          Field("as_of", STRING, False,
                describes="YYYY-MM-DD. REFUSED for HELD: point-in-time reconstruction is "
                          "UNVERIFIED against any external source, so a past date gets a "
                          "named refusal rather than today's text")),
         "POST", read_only=True, run=_sources_search),

    Verb("research.cases",
         "Find case law by a generic query -- a party or case name, optionally a year or "
         "court. Returns LICENSED judgment candidates (supporting authority, NEVER a verified "
         "statutory answer); open one to read its verbatim passage. Search is by party/title, "
         "not legal topic.",
         (Field("query", STRING, True,
                describes="a party or case name, e.g. 'Tata Sons Cyrus Mistry' or "
                          "'a 2021 oppression case'"),),
         "POST", read_only=True, mcp=False, run=_research_cases),

    Verb("research.web",
         "Opt-in public web research with cited sources. Sends only the user-entered query "
         "to the configured provider; it does not search Vault files, verify law, or fetch a live docket.",
         (Field("query", STRING, True, describes="a public question; max 800 characters"),
          Field("mode", STRING, True,
                describes="GENERAL_WEB or CASE_DISCOVERY; not live case status"),
          Field("external_search_consent", BOOLEAN, True,
                describes="true only after the user confirms the query may go to the public provider")),
         "POST", read_only=True, mcp=False, run=_research_web),

    Verb("company_facts.extract",
         "Read an MCA Company Master Data page you downloaded from mca.gov.in and "
         "uploaded. Every field comes back with the span it was read from, unconfirmed. "
         "Director names and DINs are not read, not stored and not returned.",
         (Field("text", STRING, True,
                describes="the page's text. A scan has no text layer and is refused as "
                          "CANNOT_READ, never as an empty set of facts"),
          Field("uploaded_on", STRING, True,
                describes="YYYY-MM-DD, the date you uploaded it. It is part of the "
                          "source label every fact carries")),
         "POST", read_only=True, run=_company_facts_extract),

    # 032. One profile per firm (docs/architecture/COMPANY_PROFILE.md). `ask` and
    # `events.assess` read it when a request carries no company_facts of its own.
    Verb("company_profile.get",
         "Your firm's company profile: each confirmed company fact, with where it came from "
         "and who confirmed it.",
         (),
         "POST", read_only=True, mcp=False, run=_company_profile_get),

    Verb("company_profile.set",
         "Save your firm's company profile. Confirmed facts only; a fact left out is "
         "superseded, never deleted. Recorded with a reason.",
         (Field("facts", ARRAY, True,
                describes="the whole profile, as [{field, value, basis, quoted_span, "
                          "source_label, confirmed: true}] in the company_facts vocabulary, "
                          "plus company_class (private, public or opc)"),
          Field("reason", STRING, True, describes="why, recorded with the change")),
         "POST", read_only=False, run=_company_profile_set),

    Verb("intake.classify",
         "Which of six fixed tasks a request is, with two alternatives and a reason -- or "
         "a one-sentence question when it is genuinely open. Decided by code wherever code "
         "can; a model is asked only when the rules cannot, and its reply must be one of "
         "the six names. This verb never runs the task.",
         (Field("message", STRING, False,
                describes="the user's words. Rendered verbatim, never parsed for meaning "
                          "beyond the fixed signals"),
          Field("files", ARRAY, False,
                describes="the attachments as [{name, type}]. The NAME decides whether a "
                          "file is a contract or a filing, because a .pdf is both"),
          Field("facts", OBJECT, False,
                describes="event facts (foreign_investor, listed, state). Recorded and "
                          "passed through, never used to classify: they describe the "
                          "company, not what is being asked")),
         "POST", read_only=True, run=_intake_classify),

    Verb("conversation.send",
         "One turn of a conversation: classify the request, dispatch it to the verb that "
         "answers it, store the message, and return the answer envelope -- or a run_id at "
         "once when the work belongs on the queue.",
         (Field("conversation_id", STRING, False,
                describes="the thread to append to. Absent starts a new one"),
          Field("text", STRING, False, describes="the user's words, at most 8000 characters"),
          Field("request_id", STRING, False, describes="stable retry ID; reused only with identical input"),
          Field("file_ids", ARRAY, False,
                describes="vault document IDs, or process-local sha256 upload IDs"),
          Field("as_of", STRING, False,
                describes="YYYY-MM-DD, the date to read the law as at. Defaults to today"),
          Field("sources", ARRAY, False,
                describes="source ids to consult, from sources.list. Recorded; only HELD "
                          "and CLIENT are loadable today"),
          Field("task_override", STRING, False,
                describes="name the task yourself instead of letting intake classify it"),
          Field("event", STRING, False,
                describes="the event key, when the task is EVENT_ASSESS"),
          Field("facts", OBJECT, False, describes="event facts"),
          Field("test_data", STRING, False,
                describes="ignored on API requests: only an in-process test may mark a "
                          "contract as a synthetic fixture (PLAN_22 D3)"),
          Field("matter_id", STRING, False,
                describes="file this conversation to a matter. Without one it is not "
                          "filed, and no matter's listing will show it"),
          Field("prose", ARRAY, False,
                describes="connecting sentences for a DRAFT, as [{text, citation_ids}]. "
                          "Each is stored as a MODEL_SUGGESTION and blocks approval; one "
                          "that states something about the law without a citation this "
                          "run holds is DROPPED and reported in dropped_claims")),
         "POST", read_only=False, run=_conversation_send),

    # V1: the vault. Every READ here is mcp=False on principle -- a vault is the client's
    # documents themselves, and no agent task should be able to search one by default.
    Verb("vault.upload",
         "Put a document in the vault and queue it for ingestion. PENDING is not "
         "INGESTED: nothing is searchable until a worker has read it.",
         (Field("name", STRING, True, describes="the document's name"),
          Field("text", STRING, True, describes="its text"),
          Field("matter_id", STRING, False, describes="the matter to file it under")),
         "POST", read_only=False, run=_vault_upload),

    Verb("vault.list",
         "Browse document metadata in one matter, or unfiled workspace documents only. Includes sha256 content ids for review-table selection; document contents and storage paths are never returned.",
         (Field("matter_id", STRING, False, describes="one matter; omit for unfiled only"),
          Field("query", STRING, False, describes="filename text, at most 120 characters"),
          Field("limit", STRING, False, describes="page size, 1–50"),
          Field("offset", STRING, False, describes="page offset, 0–10000")),
         "POST", read_only=True, mcp=False, run=_vault_list),

    Verb("vault.status",
         "One document's state and tags, or the whole vault's counts including how many "
         "documents cannot be searched.",
         (Field("document_id", STRING, False, describes="one document, or omit for all"),),
         "POST", read_only=True, mcp=False, run=_vault_status),

    Verb("vault.find",
         "Search this firm's vault. Contextual BM25 across every matter; the result says "
         "how many documents it could not look at.",
         (Field("query", STRING, True, describes="what to search for"),
          Field("limit", STRING, False, describes="how many passages, up to 50")),
         "POST", read_only=True, mcp=False, run=_vault_find),

    Verb("vault.verify",
         "Do the stored bytes still hash to the key they were stored under?",
         (Field("document_id", STRING, True, describes="the document to re-read"),),
         "POST", read_only=True, mcp=False, run=_vault_verify),

    # move 16 (T4). READ-ONLY: it reserves and releases within the call, so it changes no
    # durable state and a caller may ask as often as they like. mcp=False because
    # `scripts/themis_mcp.py` asserts len(TOOLS) == 31 and must not be edited.
    Verb("runs.preview",
         "What a multi-agent fan-out would do and what it would cost, before anything runs. "
         "A quote, not a hold: nothing is reserved by a preview.",
         (Field("goal", STRING, True,
                describes="what the fan-out is for, in the lawyer's own words"),
          Field("workers", ARRAY, True,
                describes="the proposed workers, each {agent, task}")),
         "POST", read_only=True, mcp=False, run=_runs_preview),
    # move 8 (T3). mcp=False: `scripts/themis_mcp.py` asserts `len(TOOLS) == 31` and is a
    # Themis file this session must not edit, so a new verb stays off MCP. Read-only -- it
    # reads bytes and decides nothing.
    Verb("document.verify",
         "Signature, certificate chain, revocation and byte coverage for one stored "
         "document. One line per check; the official-record checks are NOT_CHECKED until a "
         "permission exists.",
         (Field("document_id", STRING, True,
                describes="the stored document to verify"),),
         "POST", read_only=True, mcp=False, run=_document_verify),

    # move 10 (T3). A WRITE verb -- it records a row in `document_checks` -- so `mcp_tools()`
    # keeps it off MCP on its own. The plan asked for "read-only MCP"; it is not read-only,
    # and `scripts/themis_mcp.py` asserts `len(TOOLS) == 31` and must not be edited, so both
    # reasons point the same way.
    Verb("document.check",
         "Verify a stored document, decide whether it is still in force, and record the "
         "action a lawyer should take. One line per verification check; the action is "
         "NEEDS_LAWYER whenever a check was not run.",
         (Field("document_id", STRING, True,
                describes="the stored document to check"),
          Field("as_of", STRING, False,
                describes="the date to judge validity AT (ISO); today when omitted"),
          Field("renewable", BOOLEAN, False,
                describes="whether a document of this class can be renewed rather than "
                          "replaced"),
          Field("superseded_by", STRING, False,
                describes="the instrument that replaced this one, if the caller knows of "
                          "one. Never inferred"),
          Field("revoked_on", STRING, False,
                describes="the date this document was revoked (ISO), if it was")),
         "POST", read_only=False, mcp=False, run=_document_check),

    Verb("vault.summarize",
         "What is RECORDED about a document: its class, its clauses, and the sentence "
         "each was found in. Not a written summary.",
         (Field("document_id", STRING, True, describes="the document"),),
         "POST", read_only=True, mcp=False, run=_vault_summarize),

    Verb("vault.research",
         "Search the vault and return the passages, each with the document it came from. "
         "No prose is written over them.",
         (Field("query", STRING, True, describes="the question"),
          Field("limit", STRING, False, describes="how many passages")),
         "POST", read_only=True, mcp=False, run=_vault_research),

    Verb("vault.compile",
         "One matter's documents with their classes and clause tags, and the names of any "
         "that could not be read.",
         (Field("matter_id", STRING, True, describes="the matter"),),
         "POST", read_only=True, mcp=False, run=_vault_compile),

    Verb("vault.retry",
         "Read a FAILED document again: back to PENDING with its job requeued. Refused for "
         "any other state, so a retry can never process a document twice.",
         (Field("document_id", STRING, True, describes="the FAILED document to read again"),),
         "POST", read_only=False, run=_vault_retry),

    Verb("vault.delete",
         "Destroy a document's bytes and keep the record that it existed and was deleted.",
         (Field("document_id", STRING, True, describes="the document to destroy"),),
         "POST", read_only=False, run=_vault_delete),

    Verb("calendar.upcoming",
         "What falls due in the next 90 days, and what cannot be dated at all. A missing "
         "fact gives an UNKNOWN entry naming the fact, never a guessed date.",
         (Field("company", OBJECT, True,
                describes="the company PROFILE: company_class and incorporation_date at "
                          "least, plus any of paid_up_capital, turnover, director_count "
                          "and the rest. NOT the `company_facts` vocabulary, which is MCA "
                          "master data and a different thing"),
          Field("anchors", OBJECT, False,
                describes="{anchor_label: YYYY-MM-DD} the dates this company has "
                          "supplied. Nothing is derived from another fact"),
          Field("intervals", OBJECT, False,
                describes="{obligation_id: anchor_label} which supplied date each duty "
                          "runs from"),
          Field("as_of", STRING, False, describes="YYYY-MM-DD, default today"),
          Field("horizon_days", STRING, False, describes="default 90")),
         "POST", read_only=True, mcp=False, run=_calendar_upcoming),

    Verb("jobs.dead",
         "Jobs that stopped trying, newest first, each with the reason it stopped and how "
         "many attempts were spent. DEAD is not FAILED: a FAILED attempt may be retried, a "
         "DEAD job will not be.",
         (Field("limit", STRING, False, describes="how many, up to 500, default 100"),),
         "POST", read_only=True, mcp=False, run=_jobs_dead),

    Verb("usage.status",
         "What this firm and this person have spent against the caps, and what is left. "
         "Identity comes from the authenticated caller, never from an argument, so no "
         "caller can read another firm's spend.",
         (),
         "POST", read_only=True, mcp=False, run=_usage_status),

    Verb("matters.create",
         "Open a matter: one piece of work for one client. Work is filed to it, and "
         "conversations are listed one matter at a time.",
         (Field("name", STRING, True, describes="the matter's name, unique in the firm"),
          Field("client_ref", STRING, False,
                describes="the firm's own reference for the client"),
          Field("matter_id", STRING, False, describes="supply one, or get a new uuid")),
         "POST", read_only=False, run=_matters_create),

    Verb("matters.grant",
         "ADMIN: give one person a role (owner, member, viewer) on one matter, with a "
         "recorded reason. Access is never inferred from being in the firm.",
         (Field("matter_id", STRING, True, describes="the matter"),
          Field("actor_id", STRING, True, describes="the person's account id"),
          Field("role", STRING, True, describes="owner, member, or viewer"),
          Field("reason", STRING, True, describes="why, recorded with the grant")),
         "POST", read_only=False, run=_matters_grant),

    Verb("matters.revoke",
         "ADMIN: end one person's access to one matter, with a recorded reason. Their "
         "queued and running jobs on it stop before publishing.",
         (Field("matter_id", STRING, True, describes="the matter"),
          Field("actor_id", STRING, True, describes="the person's account id"),
          Field("reason", STRING, True, describes="why, recorded with the revocation")),
         "POST", read_only=False, run=_matters_revoke),

    Verb("matters.members",
         "ADMIN: who holds which role on one matter; with include_revoked, every grant "
         "ever made and who made it.",
         (Field("matter_id", STRING, True, describes="the matter"),
          Field("include_revoked", BOOLEAN, False, describes="include ended grants")),
         "POST", read_only=True, mcp=False, run=_matters_members),

    Verb("matters.access_report",
         "ADMIN: matters with no members and unfiled documents with no owner -- what to "
         "grant after per-matter access was switched on. Metadata only.",
         (),
         "POST", read_only=True, mcp=False, run=_matters_access_report),

    Verb("vault.share",
         "Share one of your unfiled documents with the whole firm, or stop (shared=false). "
         "Recorded with a reason.",
         (Field("document_id", STRING, True, describes="the vault document"),
          Field("reason", STRING, True, describes="why, recorded with the change"),
          Field("shared", BOOLEAN, False, describes="false to stop sharing")),
         "POST", read_only=False, run=_vault_share),

    Verb("access.reassign",
         "ADMIN: give one piece of unfiled work (vault_document, draft, review_grid, "
         "conversation) an owner, file it to a matter, or both. Recorded with a reason.",
         (Field("kind", STRING, True, describes="vault_document, draft, review_grid or conversation"),
          Field("id", STRING, True, describes="the item's id"),
          Field("reason", STRING, True, describes="why, recorded with the change"),
          Field("to_actor", STRING, False, describes="the new owner's account id"),
          Field("to_matter", STRING, False, describes="the matter to file it to")),
         "POST", read_only=False, run=_access_reassign),

    Verb("matters.list",
         "Every matter in this firm. Read-only, and NOT exposed as an MCP tool: a client "
         "list names who the firm acts for, and no agent task needs it.",
         (),
         "POST", read_only=True, mcp=False, run=_matters_list),

    Verb("conversation.list",
         "One MATTER's conversations, newest first. There is no 'all matters' listing.",
         (Field("matter_id", STRING, True,
                describes="which matter. REQUIRED (8b: no cross-matter listing)"),
          Field("limit", STRING, False, describes="how many, up to 200")),
         "POST", read_only=True, run=_conversation_list),

    Verb("conversation.get", "One conversation and its messages, in order.",
         (Field("conversation_id", STRING, True, in_path=True,
                describes="the thread"),),
         "GET", read_only=True, run=_conversation_get),

    Verb("citation.get",
         "One citation in full for the source panel, with its quote RE-VERIFIED against "
         "the held corpus rather than trusted from the stored envelope.",
         (Field("citation_id", STRING, True, describes="the citation's id"),
          Field("conversation_id", STRING, True,
                describes="the thread it was cited in, so the tenant's own policy governs "
                          "the read"),
          Field("as_of", STRING, False,
                describes="YYYY-MM-DD: re-verify against the section as it stood then. "
                          "An answer given for a past date always uses its own date")),
         "POST", read_only=True, run=_citation_get),

    Verb("review_table.create",
         "Define a review table -- documents down the side, questions across the top -- "
         "and queue one job per cell. Refuses above the cell cap, and checks the budget "
         "before anything is enqueued.",
         (Field("name", STRING, True, describes="a name for the table"),
          Field("document_ids", ARRAY, True,
                describes="sha256 ids from documents.upload"),
          Field("columns", ARRAY, True,
                describes="[{name, kind, question}]; kind is text|date|amount|yes_no|"
                          "clause, and question is what is asked of each document"),
          Field("grid_id", STRING, False,
                describes="supply one to make creation idempotent")),
         "POST", read_only=False, run=_review_table_create),

    Verb("review_table.status",
         "One review table: per-state counts, every cell, and whether it is complete. "
         "PENDING and COULD NOT RUN are not findings.",
         (Field("grid_id", STRING, True, describes="the table"),),
         "POST", read_only=True, run=_review_table_status),

    Verb("review_table.export",
         "The table as CSV. Every cell carries words rather than a blank, and any value a "
         "spreadsheet would run as a formula is quoted.",
         (Field("grid_id", STRING, True, describes="the table"),),
         "POST", read_only=True, run=_review_table_export),

    Verb("review_table.list",
         "The review tables you may open, newest first: name, when and by whom it was "
         "started, its state, and its document, column and cell counts. No answers.",
         (Field("limit", STRING, False, describes="page size, 1 to 50; default 20"),
          Field("cursor", STRING, False, describes="opaque cursor from the previous page")),
         "POST", read_only=True, mcp=False, run=_review_table_list),

    Verb("draft.create",
         "Start a draft at version 1. A MODEL_SUGGESTION or UNKNOWN slot blocks approval.",
         (Field("title", STRING, True, describes="the document's title"),
          Field("body", STRING, False, describes="the rendered text"),
          Field("slots", ARRAY, False,
                describes="[{name, value, type, source?, working?}]; type is "
                          "SOURCE_QUOTE|USER_FACT|DERIVED_FACT|TEMPLATE_TEXT|"
                          "MODEL_SUGGESTION|UNKNOWN"),
          Field("citations", ARRAY, False, describes="the legal basis, as strings"),
          Field("kind", STRING, False, describes="the template, e.g. agm_notice"),
          Field("draft_id", STRING, False, describes="optional client ID; existing IDs are refused")),
         "POST", read_only=False, run=_draft_create),

    Verb("draft.revise",
         "Save a NEW version of a draft; never edits one. Formal approval is not available "
         "through this verb and must use a separately authenticated review action.",
         (Field("draft_id", STRING, True, describes="the draft"),
          Field("base_version", STRING, True,
                describes="the version this revision was based on. REQUIRED: if it is not "
                          "the latest, the save is refused with CONFLICT naming both "
                          "versions rather than overwriting a colleague's work"),
          Field("title", STRING, False, describes="a new title; absent keeps the last"),
          Field("body", STRING, False, describes="new text; absent keeps the last"),
          Field("slots", ARRAY, False, describes="new slots; absent keeps the last"),
          Field("citations", ARRAY, False, describes="new citations")),
         "POST", read_only=False, run=_draft_revise),

    Verb("draft.status", "One draft: its version count, whether it is approvable, and "
                         "which slots block it.",
         (Field("draft_id", STRING, True, describes="the draft"),),
         "POST", read_only=True, run=_draft_status_verb),

    Verb("draft.list", "List this tenant's drafts by most recently updated. Returns "
                       "metadata only; never returns document body text.",
         (Field("limit", STRING, False, describes="page size, 1 to 50; default 20"),
          Field("cursor", STRING, False, describes="opaque cursor from the previous page")),
         "POST", read_only=True, mcp=False, run=_draft_list),

    Verb("draft.versions", "Every version of a draft, in order, with its provenance.",
         (Field("draft_id", STRING, True, describes="the draft"),),
         "POST", read_only=True, run=_draft_versions),

    Verb("draft.diff",
         "The exact diff between two versions: a unified text diff, and the provenance "
         "changes a text diff cannot show.",
         (Field("draft_id", STRING, True, describes="the draft"),
          Field("from_version", STRING, False, describes="default 1"),
          Field("to_version", STRING, False, describes="default the latest")),
         "POST", read_only=True, run=_draft_diff),

    Verb("draft.export",
         "One version as .docx or text. The .docx is written with the standard library; "
         "an unapprovable draft says so on its own face.",
         (Field("draft_id", STRING, True, describes="the draft"),
          Field("version", STRING, False, describes="default the latest"),
          Field("format", STRING, False, describes="docx (default) or text")),
         "POST", read_only=True, run=_draft_export),

    Verb("review_table.cancel",
         "Stop scheduling a review table's remaining cells. Answered cells are kept; "
         "unrun cells stay PENDING, not failed.",
         (Field("grid_id", STRING, True, describes="the table"),),
         "POST", read_only=False, run=_review_table_cancel),

    Verb("documents.upload",
         "Store a document and return the sha256 that identifies it.",
         (Field("text", STRING, False, describes="the document text"),
          Field("name", STRING, False, describes="a label for the document"),
          Field("cannot_read", STRING, False,
                describes="the reason the text could NOT be extracted, for a scan or a "
                          "photographed page. Recorded so the file panel shows the "
                          "document with CANNOT_READ instead of omitting it")),
         "POST", read_only=False, run=_documents_upload),

    Verb("auth.login",
         "Sign in with an email and a password. PUBLIC: no API key or session needed, "
         "because this is how one is obtained.",
         (Field("email", STRING, True, describes="the account's email"),
          Field("password", STRING, True, describes="the account's password")),
         "POST", read_only=False, mcp=False, run=_auth_login),

    Verb("auth.logout",
         "End the calling session. Refuses for an API key, which is not a session and "
         "has nothing here to revoke.",
         (), "POST", read_only=False, mcp=False, run=_auth_logout),

    Verb("auth.me",
         "Who the caller is: their own actor id, tenant, email and role. There is no "
         "argument that names somebody else's.",
         (), "POST", read_only=True, mcp=False, run=_auth_me),

    Verb("invites.create",
         "Invite someone into this firm by email, at a given role. ADMIN-only. Returns "
         "the raw invite token ONCE, to be shared out of band -- it is never stored.",
         (Field("email", STRING, True, describes="the invitee's email"),
          Field("role", STRING, True, describes="viewer, lawyer, or admin")),
         "POST", read_only=False, run=_invites_create),

    Verb("invites.accept",
         "Accept an invite token and set a password, creating the account it names. "
         "PUBLIC: the unguessable token IS the credential. The role is the invite's, "
         "never a value supplied here.",
         (Field("token", STRING, True, describes="the raw invite token, from the email"),
          Field("password", STRING, True,
                describes="the new account's password, at least 12 characters")),
         "POST", read_only=False, mcp=False, run=_invites_accept),

    Verb("people.list",
         "ADMIN: everyone in this firm who signs in -- name, email, role, when they "
         "joined. No passwords or sessions.",
         (), "POST", read_only=True, mcp=False, run=_people_list),

    Verb("invites.list",
         "ADMIN: invites in this firm not yet accepted, cancelled or expired. Never the "
         "invite token.",
         (), "POST", read_only=True, mcp=False, run=_invites_list),

    Verb("invites.cancel",
         "ADMIN: withdraw an unused invite. It is marked cancelled, not deleted, and can no "
         "longer be accepted.",
         (Field("invite_id", STRING, True, describes="the invite to withdraw"),),
         "POST", read_only=False, mcp=False, run=_invites_cancel),
)


def by_name() -> dict[str, Verb]:
    return {v.name: v for v in VERBS}


# ── the three surfaces, generated ────────────────────────────────────────────

def rest_spec(verbs: tuple[Verb, ...] | None = None) -> dict[str, dict]:
    """{verb name: {method, path, body, path_params}}.

    `verbs` is a parameter so the parity test can generate the surfaces for a HYPOTHETICAL
    table without mutating this module -- a test that rebinds a global to prove something
    leaves the next test reading whatever it left behind.
    """
    return {v.name: {"method": v.method, "path": rest_path(v),
                     "body": tuple(f.name for f in v.body_fields),
                     "required": tuple(f.name for f in v.inputs if f.required),
                     "path_params": tuple(f.name for f in v.path_fields)}
            for v in (VERBS if verbs is None else verbs)}


def mcp_tools(verbs: tuple[Verb, ...] | None = None) -> tuple:
    """The existing Tool type, so these join checker/mcp/ rather than shadow it.

    A verb that is not read_only is REFUSED here rather than quietly exported: the MCP
    policy asserts every known tool is read-only, and widening that is a decision, not a
    side effect of adding a verb.

    `mcp=False` opts a read-only verb out. That is a narrower statement than "this is a
    write": an operator's number -- a hit rate, a failure tally, a list of matters -- is
    read-only and still has no business in an agent's toolbox.
    """
    from checker.mcp.tools import Tool, _obj
    out = []
    for v in (VERBS if verbs is None else verbs):
        if not v.read_only or not v.mcp:
            continue
        props = {f.name: {"type": f.kind, "description": f.describes} for f in v.inputs}
        required = tuple(f.name for f in v.inputs if f.required)
        out.append(Tool(mcp_name(v), v.summary, _obj(props, required),
                        (lambda verb: lambda args: (verb.run or (lambda a, c: {}))(
                            args, Context()))(v)))
    return tuple(out)


def cli_spec(verbs: tuple[Verb, ...] | None = None) -> dict[str, dict]:
    """{verb name: {command, flags: {flag: required}}}."""
    return {v.name: {"command": cli_command(v),
                     "flags": {cli_flag(f): f.required for f in v.inputs},
                     "summary": v.summary}
            for v in (VERBS if verbs is None else verbs)}


def write_verbs(verbs: tuple[Verb, ...] | None = None) -> tuple[str, ...]:
    """Verbs that change state. Named once, so three surfaces cannot disagree about it."""
    return tuple(v.name for v in (VERBS if verbs is None else verbs)
                 if not v.read_only)
