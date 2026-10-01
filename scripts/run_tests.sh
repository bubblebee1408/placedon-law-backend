#!/usr/bin/env bash
# Run every self-testing module.
#
# Exists because these modules import as `checker.x` but are run as files, so a bare
# `python3 checker/as_of.py` dies with ModuleNotFoundError. That looked like a silent pass in an
# ad-hoc loop once -- the suite had not run at all. PYTHONPATH is set here so it cannot recur.
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"

# ── Dependencies first, because a missing one is not a failing test ───────────
# Reported 2026-09-27 from an environment without pypdf: the sweep said
# "checker/sarvam_model.py FAIL" with NO result line, because sarvam_selftest reached an
# optional-dependency path and the SarvamUnavailable refusal propagated out of the suite.
# That reads as a broken suite and sends the reader to the wrong file -- the suite is fine
# and the environment is not. `scripts/check_deps.py` already knows the answer (it reads
# requirements.txt AND requirements-dev.txt); nothing was asking it before the sweep.
#
# BLOCKED is a third status, distinct from GREEN and RED on purpose: no suite ran, so
# reporting `failed=0 status=RED` would claim a measurement nobody took.
if ! missing=$(python3 scripts/check_deps.py 2>&1); then
  cat >&2 <<MSG
==============================================================================
 ENVIRONMENT NOT READY -- no suite was run
==============================================================================
  $missing

  These are pinned in requirements.txt / requirements-dev.txt and are absent here.
  Install them, then re-run:

      python3 -m pip install -r requirements.txt -r requirements-dev.txt
      # or: ./setup.sh   (idempotent; installs both)

  This is NOT a failing test. Nothing about the suite is known yet.
==============================================================================
MSG
  printf 'HARNESS_RESULT suites=0 failed=0 status=BLOCKED\n'
  exit 5
fi

suites=(
  checker/acquisition_log.py
  checker/amendment.py
  checker/as_of.py
  checker/instrument_registry.py
  checker/ontology.py
  checker/observation_store.py
  checker/derivation.py
  checker/prompt_safety.py
  checker/anthropic_model.py
  checker/azure_model.py
  checker/gemini_model.py
  checker/router.py
  checker/voyage_model.py
  checker/public_only.py
  checker/quoted_span.py
  checker/sarvam_model.py
  checker/orchestrator.py
  checker/bundles.py
  checker/reasoning.py
  checker/field_binding.py
  checker/shadow.py
  checker/scope.py
  checker/session.py
  checker/document_extract.py
  checker/pit_bench.py
  checker/event_log.py
  checker/staleness.py
  checker/derived_date.py
  checker/document_date.py
  backend/budget.py
  backend/azure_pricing.py
  checker/claim_schema.py
  checker/legal_ref.py
  checker/admission.py
  checker/review_queue.py
  checker/pdf_text.py
  checker/pdf_pages.py
  checker/rings.py
  checker/operations.py
  checker/operation_store.py
  checker/mcp/policy.py
  checker/mcp/tools.py
  checker/mcp/server.py
  checker/feeds/__init__.py
  checker/feeds/common/__init__.py
  checker/feeds/common/fetch.py
  checker/feeds/common/cache.py
  checker/feeds/common/rate.py
  checker/feeds/ofac_sdn.py
  checker/feeds/egazette.py
  checker/feeds/ibbi.py
  checker/legal_retrieval.py
  checker/text_search.py
  checker/evidence_pack.py
  checker/retrieve.py
  checker/model_adapter.py
  checker/claim_verifier.py
  checker/lawyer_summary.py
  checker/redteam.py
  checker/provenance.py
  checker/section_index.py
  checker/mvp_freeze.py
  checker/ss/defects.py
  applicability.py
  checker/assessment.py
  checker/attribution.py
  checker/agm.py
  checker/timeline.py
  checker/robots.py
  checker/corroborate.py
  checker/asn1.py
  checker/pdf_signature.py
  checker/trust.py
  checker/entail_mine.py
  checker/benchmark_freeze.py
  checker/entail_baseline.py
  checker/entail_paraphrase.py
  checker/commencement.py
  checker/witness_span.py
  checker/s96_slice.py
  checker/eval_taxonomy.py
  checker/entail_binding.py
  checker/entail_role.py
  checker/entail_qualifier.py
  checker/cascade.py
  checker/entailment_gate.py
  checker/company_profile.py
  checker/prescribed_thresholds.py
  checker/classify.py
  checker/clauses.py
  checker/playbook.py
  checker/obligations.py
  checker/obligation_citations.py
  checker/entity_graph.py
  checker/corporate_data.py
  checker/mca_aggregator.py
  checker/mca_snapshot.py
  checker/mca_reconcile.py
  checker/party_resolution.py
  checker/mca_strip.py
  checker/code_transition.py
  checker/buyer_sim.py
  checker/objection_sim.py
  checker/coverage.py
  checker/sweep.py
  eval/temporal/harness.py
  eval/prelabel/compare.py
  eval/goldset/__init__.py
  eval/goldset/split.py
  eval/prelabel/corpus.py
  checker/env.py
  checker/s185.py
  checker/s188.py
  checker/s184.py
  checker/s188_threshold.py
  checker/s186.py
  checker/s180.py
  checker/currency.py
  checker/corpus_currency.py
  checker/lattice.py
  checker/interval.py
  checker/release.py
  checker/licence.py
  checker/calibration_contract.py
  checker/forecast/__init__.py
  checker/forecast/rates.py
  checker/forecast/survival.py
  checker/forecast/conformal.py
  checker/forecast/events.py
  checker/forecast/propagate.py
  checker/forecast/scoring.py
  checker/chunk_fusion.py
  checker/fusion.py
  checker/reranker.py
  checker/ablation.py
  checker/dense_index.py
  checker/ollama_runner.py
  checker/backtest.py
  checker/annotation.py
  checker/extraction_schema.py
  checker/structural_chunk.py
  checker/structural_index.py
  checker/structural_retrieve.py
  checker/ground_span.py
  checker/lexical_rank.py
  checker/retrieval_eval.py
  checker/chunk_retrieval.py
  checker/corpus_retrieval.py
  checker/cross_section_eval.py
  checker/api.py
  checker/ask.py
  checker/ask_scope.py
  checker/matrix_view.py
  checker/diligence_pack.py
  checker/review_table.py
  checker/review_record.py
  checker/resubmission.py
  checker/promotion_preview.py
  checker/scoped_retraction.py
  checker/metric_policy.py
  checker/s173_slice.py
  checker/grounding_policy.py
  checker/entail_pairs_v2.py
  checker/reviews.py
  checker/fixture_rebuild.py
  checker/benchmark_v2_freeze.py
  checker/benchmark_versions.py
  checker/release_record.py
  checker/paraphrase_negatives.py
  checker/revocation.py
  checker/doc_verification.py
  checker/provenance_slots.py
  checker/drafting.py
  checker/matter.py
)

# Test-only injection point. scripts/harness_regression.sh sets this to a suite that
# is KNOWN to fail, to prove this runner actually turns RED. It can only ADD a suite,
# never remove or silence one, so it cannot itself become a masking vector. Unset in
# all normal use.
if [ -n "${HARNESS_EXTRA_SUITE:-}" ]; then
  suites+=("$HARNESS_EXTRA_SUITE")
fi

# --test flag rather than a bare run: this one takes a PDF argument in normal use.
extra=("scripts/acquire_rules.py --test" "scripts/register_gsr700e.py --test" "scripts/register_gsr880e.py --test" "scripts/register_kmp_rules.py --test" "scripts/register_sebi_lodr.py --test" "scripts/register_pas_rules.py --test" "scripts/sweep_folder.py --test" "scripts/holdings.py --test" "scripts/provenance_census.py --test" "eval/realrun/run.py --test" "eval/realrun/text_field_probe.py --test" "eval/realrun/azure_model.py" "scripts/text_layer_census.py --test" "scripts/assistant_contract.py --test" "scripts/register_s188_rule15.py --test" "scripts/benchmark_refreeze_request.py --test" "scripts/parse_board_rules.py --test" "scripts/baseline_eval.py --test" "scripts/review.py --test" "scripts/review_brief.py --check" "scripts/slice_s96.py --test" "scripts/slice_s173.py --test" "scripts/serve_matrix.py --test" "scripts/serve_api.py --test" "scripts/record_interview.py --test" "scripts/verify_document.py --test" "scripts/ingest_act.py --test" "scripts/ingest_companies_act.py --test" "scripts/verify_section_index.py --test" "scripts/resolve_missing_sections.py --test" "scripts/prove_temporal.py --test" "scripts/batch1_omissions.py --test" "scripts/batch1_review.py --test" "scripts/find_commencement.py --test" "scripts/watch_gazette.py --test" "scripts/watch_ofac.py --test" "scripts/gazette_digest.py --test" "scripts/themis_slice.py --test" "scripts/themis_mcp.py --test" "scripts/bakeoff_retrieval.py --test" "scripts/bakeoff_models.py --test" "scripts/acquire_cuad.py --test" "scripts/bakeoff_indic.py --test" "scripts/smoke_adapters.py --test" "eval/prelabel/run_prelabel.py --test" "eval/goldset/run.py --test" "scripts/check_doc_refs.py --test" "scripts/cascade_report.py --test" "gateway/audit.py" "gateway/auth.py" "gateway/schema.py" "checker/model_cascade.py" "checker/events.py" "checker/claim_bodies.py" "gateway/store.py" "gateway/jobs.py" "gateway/worker.py" "gateway/app.py" "gateway/verbs.py" "gateway/cli.py --test" "agents/state.py" "agents/plans.py" "agents/runtime.py" "agents/research_question.py" "agents/review_contract.py" "agents/review_document.py" "agents/intake.py --test" "gateway/envelope.py --test")
# The generated repo map. `--test` is the self-test; `--check` fails the gate when a
# module has been added without regenerating docs/REPO_MAP.md, which is the whole
# reason the map is generated rather than hand-kept. Both print a count line, because
# rule (a) below marks a suite without one as FAILED.
extra+=("scripts/repo_map.py --test" "scripts/repo_map.py --check")

# The Ask demo server (D2): 127.0.0.1 only, serves web/assistant, forwards POST /v1/ask.
extra+=("scripts/serve_ask.py --test")

# Defines _test() but runs it only under --test; invoked bare it printed a report and
# exited 0. Its sixteen checks had never run. Found by the no-count rule below.
extra+=("checker/span_inventory.py --test")
# The harness's own reproduction of the 2026-09-30 incident.
extra+=("scripts/harness_selftest.py --test")
extra+=("scripts/suite_floors.py --test")
# H4 (review grids). The core rules: a FOUND cell cannot exist without a quote that
# byte-matches its document, and no exported cell is ever empty.
extra+=("checker/review_grid.py --test")
# H3: draft history. Every save is a version; the diff names a sentence whose words are
# unchanged and whose support is gone, which a text diff cannot show.
extra+=("checker/draft_versions.py --test")
# Job 3: the two draft templates. The rule it exists for: a statement of law comes from a
# verified citation in the source run or it does not appear, and a model sentence that
# asserts law with no citation is DROPPED, not labelled.
extra+=("checker/draft_templates.py --test")
# Job 3c: the model that writes a draft's joining sentences. It is shown the run's findings
# and never the user's message, and whatever it writes goes through the same admit/drop rule.
extra+=("checker/draft_prose.py --test")
# O9: the answer cache. Its rule is not "have we seen this" but "is the stored answer
# still true", which is settled by re-reading the corpus.
extra+=("checker/answer_cache.py --test")
extra+=("scripts/cache_report.py --test")

# H4's runner: one queue job per cell, exactly once, resumable, cancel as a saga.
extra+=("agents/review_grid.py --test")
# H4's measurement on CUAD. Evaluation only: the suite also asserts no served or
# feature module IMPORTS it, so no figure from it can reach a user.
extra+=("scripts/review_table_eval.py --test")
extra+=("scripts/retrieval_recall.py --test")
extra+=("scripts/retrieval_bakeoff.py --test")
# The source register (PLAN_24 S0). Nothing is fetched on an unread term, so the register
# is a test subject: it asserts which sources are closed, and a later edit that quietly
# opens one has to break a check to do it.
extra+=("checker/sources/terms.py --test")
# The source framework (PLAN_24 S1). contract.py holds the five cross-module rules -- only
# HELD can verify, every Evidence is hash-stamped and timed, a soft-404 raises rather than
# reading as "no results" -- and is listed because a rule spanning three modules would
# otherwise pass three times while the composition failed.
extra+=("checker/sources/tiers.py --test" "checker/sources/evidence.py --test"
        "checker/sources/base.py --test" "checker/sources/held.py --test"
        "checker/sources/client.py --test" "checker/sources/contract.py --test")
# Company facts without data.gov.in (PLAN_26 S2-alt). The fixture suite writes a PDF by
# hand and reads it back through checker/pdf_pages, so it also proves the scanned-page case
# the parser must call "cannot read" rather than "no facts".
extra+=("checker/sources/company_facts.py --test"
        "checker/sources/mca_fixture.py --test"
        "checker/sources/mca_master_data.py --test")

# A module that prints "9/10 passed" has failed, whatever its exit code says.
# Eight modules once defined _test() without `raise SystemExit(1)`, so their
# failures never reached the exit code and the sweep printed "all suites green"
# over four failing checks. Comparing the counts is defence in depth: the next
# module to forget the raise cannot hide behind a zero exit.
count_mismatch() {            # $1 = "N/M passed" (may be empty)
  case "$1" in
    *" passed") n=${1%%/*}; m=${1#*/}; m=${m%% *}
                [ "$n" = "$m" ] && return 1 || return 0 ;;
    *) return 1 ;;            # no count line: the CALLER refuses it. See `-z "$res"`.
  esac
}

fails=0
nocount=0
# Each green suite's passed count, for the floor ratchet below.
counts_file=$(mktemp)
trap 'rm -f "$counts_file"' EXIT
for s in "${suites[@]}"; do
  [ -f "$s" ] || { printf '%-28s %s\n' "$s" "MISSING"; fails=$((fails+1)); continue; }
  out=$(python3 "$s" 2>&1); rc=$?
  res=$(printf '%s' "$out" | grep -oE '[0-9]+/[0-9]+ passed' | tail -1)
  if [ $rc -ne 0 ]; then
    printf '%-28s FAIL  %s\n' "$s" "${res:-no result line}"
    printf '%s\n' "$out" | grep -E '^\[FAIL\]|Error|Traceback' | head -4 | sed 's/^/      /'
    fails=$((fails+1))
  elif count_mismatch "$res"; then
    printf '%-28s FAIL  %s  (exit 0 but checks failed)\n' "$s" "$res"
    printf '%s\n' "$out" | grep -E '^\s*\[FAIL\]' | head -4 | sed 's/^/      /'
    fails=$((fails+1))
  elif [ -z "$res" ]; then
    # A suite that exits 0 and prints no count has not been SEEN to run. On 2026-09-30
    # gateway/schema.py was overwritten with the live row-level-security harness, which
    # prints a banner and exits 0 unless given --run; the gate reported it `ok (no count)`
    # and stayed green over a file that was not the suite at all. Exit 0 is not evidence;
    # a count is. (That harness is deliberately not named here: schema.py asserts this
    # file does not mention it, so that a server-dependent suite cannot creep into the
    # gate and read as passing when it is skipped.)
    printf '%-28s FAIL  no count line (exit 0 but no "N/M passed" -- did this suite run?)\n' "$s"
    printf '%s\n' "$out" | tail -3 | sed 's/^/      /'
    fails=$((fails+1)); nocount=$((nocount+1))
  else
    printf '%-28s ok    %s\n' "$s" "$res"
    printf '%s\t%s\n' "$s" "${res%%/*}" >> "$counts_file"
  fi
done

for e in "${extra[@]}"; do
  out=$(python3 $e 2>&1); rc=$?
  res=$(printf '%s' "$out" | grep -oE '[0-9]+/[0-9]+ passed' | tail -1)
  if [ $rc -ne 0 ]; then printf '%-28s FAIL  %s\n' "${e%% *}" "$res"; fails=$((fails+1))
  elif count_mismatch "$res"; then
    printf '%-28s FAIL  %s  (exit 0 but checks failed)\n' "${e%% *}" "$res"; fails=$((fails+1))
  elif [ -z "$res" ]; then
    printf '%-28s FAIL  no count line (exit 0 but no "N/M passed" -- did this suite run?)\n' "${e%% *}"
    printf '%s\n' "$out" | tail -3 | sed 's/^/      /'
    fails=$((fails+1)); nocount=$((nocount+1))
  else
    printf '%-28s ok    %s\n' "${e%% *}" "$res"
    printf '%s\t%s\n' "${e%% *}" "${res%%/*}" >> "$counts_file"
  fi
done

# ── the floor ratchet: a suite may gain checks, never quietly lose them ──────
# Run even when something else failed, because a regression and a breach are different
# defects and a reader fixing one should be told about the other in the same pass.
echo
breaches=0
if ! python3 scripts/suite_floors.py --gate "$counts_file"; then breaches=1; fi
fails=$((fails+breaches))

echo
[ $fails -eq 0 ] && echo "all suites green" || echo "$fails suite(s) failing"

# ONE machine-parseable line, and it is the only thing anything downstream may read.
# Both false greens in this repo came from prose being eyeballed instead of a status
# being parsed: once a trailing `tail` made the pipeline's status the tail's, once an
# `&` detached the run so the wrapping shell returned 0 while tests were still going.
# Neither was a bug in this file. Both were bugs at the CALL SITE, which is why the
# fix is a parseable contract plus scripts/verify_green.sh as the single oracle.
total=$(( ${#suites[@]} + ${#extra[@]} ))
if [ "$fails" -eq 0 ]; then harness_status=GREEN; else harness_status=RED; fi
printf 'HARNESS_RESULT suites=%d failed=%d nocount=%d floor_breach=%d status=%s\n' \
  "$total" "$fails" "$nocount" "$breaches" "$harness_status"

exit $fails
