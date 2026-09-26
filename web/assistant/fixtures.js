window.PLACEDON_ASK_FIXTURES = {
 "answered_small_company": {
  "as_of": "2026-09-15",
  "citations": [
   {
    "cite": "Companies Act 2013, s.2 (Definitions)",
    "defects": [],
    "evidence_state": "CORROBORATED",
    "ref": "ACT:COMPANIES_ACT_2013:S2",
    "retrieved_on": [
     "2026-08-18",
     "2026-08-19"
    ],
    "source_url": "https://www.indiacode.nic.in/SectionPageContent?actid=AC_CEN_22_29_00008_201318_1517807327856&sectionID=185",
    "title": "Definitions",
    "unusable_reason": null,
    "usable_for_answering": true
   }
  ],
  "context": {
   "document_date": null,
   "kind": "general"
  },
  "evidence_pack": {
   "abstain_reason": "",
   "insufficient_evidence": false,
   "missing": [],
   "query_expansions": [],
   "retrieval_query": "s.2(85)",
   "route": "exact",
   "unusable_keys": [],
   "usable_keys": [
    "ACT:COMPANIES_ACT_2013:S2"
   ]
  },
  "facts": {
   "company_class": {
    "provenance": "USER_FACT",
    "value": "private"
   },
   "paid_up_capital_rupees": {
    "provenance": "USER_FACT",
    "value": 120000000
   },
   "turnover_rupees": {
    "provenance": "USER_FACT",
    "value": 800000000
   }
  },
  "figures": [
   {
    "amount": "₹10 crore",
    "effective_from": "2025-12-01",
    "effective_to": null,
    "evidence_state": "CORROBORATED",
    "instrument": "G.S.R. 880(E), Companies (Specification of Definition Details) Amendment Rules, 2025, dated 01-12-2025",
    "key": "small_company.paid_up_capital.prescribed",
    "rupees": 100000000,
    "source_url": "https://egazette.gov.in/WriteReadData/2025/268124.pdf"
   },
   {
    "amount": "₹100 crore",
    "effective_from": "2025-12-01",
    "effective_to": null,
    "evidence_state": "CORROBORATED",
    "instrument": "G.S.R. 880(E), Companies (Specification of Definition Details) Amendment Rules, 2025, dated 01-12-2025",
    "key": "small_company.turnover.prescribed",
    "rupees": 1000000000,
    "source_url": "https://egazette.gov.in/WriteReadData/2025/268124.pdf"
   }
  ],
  "generated_at": "2026-09-15T00:00:00Z",
  "law_version": {
   "basis": "CURRENT_CONSOLIDATION_AS_INGESTED",
   "corpus_fetched": [
    "2026-08-18"
   ],
   "point_in_time_verified": false,
   "statement": "This pack carries the CURRENT CONSOLIDATION of the Companies Act 2013 as India Code rendered it when the corpus was ingested (2026-08-18). It is NOT a point-in-time version of the law and carries no verified commencement or amendment date. The amendment vintage of individual provisions is not uniform and not fully known: SD-002 confirms that some records carry pre-amendment wording while the same publisher's PDF carries later wording. Those provisions are marked unusable in this pack. Point-in-time reconstruction exists in this system but is UNVERIFIED against any external source, so no statement here is a statement about the law as it stood on any past date."
  },
  "question": "Is this company a small company?",
  "rows": [
   {
    "basis": "a limb exceeds its limit, so not a small company",
    "blocked_by": null,
    "cited_spans": [
     {
      "path": "2(85)(i)",
      "resolved": true,
      "sha256": "sha256:8b24937ce6b9f3c3baeff9a2eca6c225f9ffb16c4af98b60ee6fc2816407e294"
     },
     {
      "path": "2(85)(ii)",
      "resolved": true,
      "sha256": "sha256:f7a340b68b234b4e182e2c90688c1ae4c0764468c371cf24fa7dfdeefda11ead"
     }
    ],
    "duty": "Establish whether the company is a small company",
    "missing_facts": [],
    "obligation_id": "CA13-S2-85-SMALL",
    "provision": "Companies Act 2013, s.2(85)",
    "state": "DOES_NOT_APPLY"
   }
  ],
  "schema": "placedon.ask/0",
  "scope": {
   "held": [
    "Companies Act, 2013"
   ],
   "sentence": "1 of 9 in-scope bodies of law are held"
  },
  "state": "answered",
  "turn_id": "t_20ccadb72b4b",
  "uses_model": false,
  "what_it_is_not": "This is not a certificate of compliance and not legal advice. It covers 15 obligations, not the whole Companies Act, against a corpus that holds the Act but almost none of the subordinate rules — so some rows refuse rather than answer, and name the instrument they are waiting on. It generates no resolution, notice, or other operative document. No lawyer has reviewed it. It can say the analysis did not contradict itself; it cannot say nothing is wrong."
 },
 "document_context_2024": {
  "as_of": "2026-09-15",
  "confirmed": [
   {
    "basis": "s.96(1) reaches every company other than an OPC; no AGM dates were supplied",
    "duty": "Hold an annual general meeting, and within the statutory gap",
    "obligation_id": "CA13-S96-AGM",
    "provision": "Companies Act 2013, s.96(1)",
    "state": "APPLIES_UNDETERMINED"
   },
   {
    "basis": "not a one-person company, so s.173 applies in full; no board meeting dates were supplied",
    "duty": "Hold the minimum number of board meetings, correctly spaced",
    "obligation_id": "CA13-S173-BOARD",
    "provision": "Companies Act 2013, s.173(1)",
    "state": "APPLIES_UNDETERMINED"
   },
   {
    "basis": "applies to every company registered under the Act; the number of directors is not on the profile",
    "duty": "Have enough directors, and not more than the maximum",
    "obligation_id": "CA13-S149-BOARD-SIZE",
    "provision": "Companies Act 2013, s.149(1)",
    "state": "APPLIES_UNDETERMINED"
   },
   {
    "basis": "applies to every company registered under the Act; no director's days-in-India were supplied; s.149(3) needs at least one director present 182 days in the year",
    "duty": "Have at least one director resident in India for 182 days",
    "obligation_id": "CA13-S149-3-RESIDENT",
    "provision": "Companies Act 2013, s.149(3)",
    "state": "APPLIES_UNDETERMINED"
   },
   {
    "basis": "applies to every company registered under the Act; the thirty days run from the AGM, and no AGM date was given",
    "duty": "File the financial statements with the Registrar in time",
    "obligation_id": "CA13-S137-AOC4",
    "provision": "Companies Act 2013, s.137(1)",
    "state": "APPLIES_UNDETERMINED"
   },
   {
    "basis": "applies to every company registered under the Act; the sixty days run from the AGM, or from the date one should have been held; neither is established",
    "duty": "File the annual return with the Registrar in time",
    "obligation_id": "CA13-S92-RETURN",
    "provision": "Companies Act 2013, s.92(4)",
    "state": "APPLIES_UNDETERMINED"
   },
   {
    "basis": "no known figure reaches its s.135(1) threshold, but net_worth, net_profit are unknown -- any one could cross, so applicability cannot be ruled out",
    "duty": "Constitute a CSR committee, if the company crosses a CSR threshold",
    "obligation_id": "CA13-S135-CSR",
    "provision": "Companies Act 2013, s.135(1)",
    "state": "CANNOT_DETERMINE"
   },
   {
    "basis": "applies to every company registered under the Act; no loans supplied: give the company's loans, guarantees and securities, with the director/relative graph, to assess s.185",
    "duty": "Ensure no loan/guarantee/security is given to a director or connected person",
    "obligation_id": "CA13-S185-LOANS-DIRECTORS",
    "provision": "Companies Act 2013, s.185",
    "state": "APPLIES_UNDETERMINED"
   },
   {
    "basis": "applies to every company registered under the Act; no loans/investments supplied: give the company's loans, guarantees, securities and acquisitions to test the s.186(2) limit",
    "duty": "Keep loans/investments within the s.186(2) limit, or authorise the excess",
    "obligation_id": "CA13-S186-LOAN-INVESTMENT",
    "provision": "Companies Act 2013, s.186",
    "state": "APPLIES_UNDETERMINED"
   },
   {
    "basis": "applies to every company registered under the Act; no borrowings supplied: give the company's proposed and existing borrowings, with paid-up capital, free reserves and securities premium, to test the s.180(1)(c) limit",
    "duty": "Keep borrowings within the s.180(1)(c) limit, or authorise the excess",
    "obligation_id": "CA13-S180-BORROWING-LIMIT",
    "provision": "Companies Act 2013, s.180(1)(c)",
    "state": "APPLIES_UNDETERMINED"
   },
   {
    "basis": "applies to every company registered under the Act; no director contracts supplied: give the (director, counterparty) pairs for the company's contracts, with the entity graph, to assess s.184(2)",
    "duty": "Ensure an interested director discloses and abstains",
    "obligation_id": "CA13-S184-DIRECTOR-INTEREST",
    "provision": "Companies Act 2013, s.184",
    "state": "APPLIES_UNDETERMINED"
   }
  ],
  "context": {
   "document_date": "2024-06-01",
   "kind": "document"
  },
  "generated_at": "2026-09-15T00:00:00Z",
  "law_version": {
   "basis": "CURRENT_CONSOLIDATION_AS_INGESTED",
   "corpus_fetched": [
    "2026-08-18"
   ],
   "point_in_time_requested": "2024-06-01",
   "point_in_time_verified": false,
   "statement": "This pack carries the CURRENT CONSOLIDATION of the Companies Act 2013 as India Code rendered it when the corpus was ingested (2026-08-18). It is NOT a point-in-time version of the law and carries no verified commencement or amendment date. The amendment vintage of individual provisions is not uniform and not fully known: SD-002 confirms that some records carry pre-amendment wording while the same publisher's PDF carries later wording. Those provisions are marked unusable in this pack. Point-in-time reconstruction exists in this system but is UNVERIFIED against any external source, so no statement here is a statement about the law as it stood on any past date. A point-in-time answer was requested for 2024-06-01. This pack CANNOT supply one. Do not treat any text below as the law as it stood on 2024-06-01."
  },
  "not_confirmed": [
   {
    "already_open_at_document_date": true,
    "detail": "Companies Act 2013 s.188, held verbatim in corpus; the members'-approval threshold is a delegated rule (S-188-RULES) surfaced on the obligation row: S-188-RULES: Rule 15, Companies (Meetings of Board and its Powers) Rules, 2014 — the members'-approval thresholds is STAGED",
    "duty": "Obtain the required approvals for related-party transactions",
    "instrument": "S-188-RULES",
    "kind": "cannot_verify",
    "obligation_id": "CA13-S188-RPT",
    "provision": "Companies Act 2013, s.188",
    "reference": null
   },
   {
    "already_open_at_document_date": true,
    "detail": "Companies Act 2013 s.177, held verbatim; the prescribed class (Rule 6) is a delegated rule (S-177-RULES) surfaced on the obligation row: S-177-RULES: Rule 6, Companies (Meetings of Board and its Powers) Rules, 2014 is HELD_UNREVIEWED",
    "duty": "Constitute an Audit Committee, if required",
    "instrument": "S-177-RULES",
    "kind": "cannot_verify",
    "obligation_id": "CA13-S177-AUDIT-CTTE",
    "provision": "Companies Act 2013, s.177",
    "reference": "S-177-RULES"
   },
   {
    "already_open_at_document_date": true,
    "detail": "Companies Act 2013 s.203, held verbatim; the prescribed KMP class is a delegated rule (S-203-RULES) surfaced on the obligation row: S-203-RULES: G.S.R. 249(E), Companies (Appointment and Remuneration of Managerial Personnel) Rules, 2014 — Rule 8, the prescribed KMP class is CHAIN_TRACED",
    "duty": "Appoint whole-time key managerial personnel, if in the prescribed class",
    "instrument": "S-203-RULES",
    "kind": "cannot_verify",
    "obligation_id": "CA13-S203-KMP",
    "provision": "Companies Act 2013, s.203",
    "reference": "S-203-RULES"
   }
  ],
  "question": "Is the law this document relies on still current?",
  "schema": "placedon.ask/0",
  "scope": {
   "held": [
    "Companies Act, 2013"
   ],
   "sentence": "1 of 9 in-scope bodies of law are held"
  },
  "scope_frame": {
   "as_of": "2026-09-15",
   "checked": [
    "Hold an annual general meeting, and within the statutory gap",
    "Hold the minimum number of board meetings, correctly spaced",
    "Have enough directors, and not more than the maximum",
    "Have at least one director resident in India for 182 days",
    "File the financial statements with the Registrar in time",
    "File the annual return with the Registrar in time",
    "Constitute a CSR committee, if the company crosses a CSR threshold",
    "Ensure no loan/guarantee/security is given to a director or connected person",
    "Keep loans/investments within the s.186(2) limit, or authorise the excess",
    "Keep borrowings within the s.180(1)(c) limit, or authorise the excess",
    "Ensure an interested director discloses and abstains",
    "Establish whether the company is a small company"
   ],
   "checked_count": 12,
   "corpus": "Companies Act 2013",
   "dismissable": false,
   "establishes_compliance": false,
   "sentence": "Checked 12 of 15 against Companies Act 2013, as at 2026-09-15.\nNOT checked (3) — these were not examined at all, and silence about them is not a finding:\n  · Obtain the required approvals for related-party transactions — its governing instrument is not held or not yet reviewed; needs: Rule 15, Companies (Meetings of Board and its Powers) Rules, 2014 — the members'-approval thresholds [STAGED]; (CANNOT_VERIFY)\n  · Constitute an Audit Committee, if required — its governing instrument is not held or not yet reviewed; needs: Rule 6, Companies (Meetings of Board and its Powers) Rules, 2014 [HELD_UNREVIEWED]; (CANNOT_VERIFY)\n  · Appoint whole-time key managerial personnel, if in the prescribed class — its governing instrument is not held or not yet reviewed; needs: G.S.R. 249(E), Companies (Appointment and Remuneration of Managerial Personnel) Rules, 2014 — Rule 8, the prescribed KMP class [CHAIN_TRACED]; (CANNOT_VERIFY)",
   "unchecked": [
    {
     "acquire": "Rule 15, Companies (Meetings of Board and its Powers) Rules, 2014 — the members'-approval thresholds [STAGED]",
     "state": "CANNOT_VERIFY",
     "what": "Obtain the required approvals for related-party transactions",
     "why": "its governing instrument is not held or not yet reviewed"
    },
    {
     "acquire": "Rule 6, Companies (Meetings of Board and its Powers) Rules, 2014 [HELD_UNREVIEWED]",
     "state": "CANNOT_VERIFY",
     "what": "Constitute an Audit Committee, if required",
     "why": "its governing instrument is not held or not yet reviewed"
    },
    {
     "acquire": "G.S.R. 249(E), Companies (Appointment and Remuneration of Managerial Personnel) Rules, 2014 — Rule 8, the prescribed KMP class [CHAIN_TRACED]",
     "state": "CANNOT_VERIFY",
     "what": "Appoint whole-time key managerial personnel, if in the prescribed class",
     "why": "its governing instrument is not held or not yet reviewed"
    }
   ],
   "unchecked_count": 3
  },
  "state": "partial",
  "superseded": [
   {
    "detail": "the prescribed small-company limits, set by delegated rule: G.S.R. 880(E), Companies (Specification of Definition Details) Amendment Rules, 2025, dated 01-12-2025 (CORROBORATED)",
    "duty": "Establish whether the company is a small company",
    "governed_then": "G.S.R. 700(E), Companies (Specification of Definition Details) Amendment Rules, 2022, dated 15-09-2022",
    "governs_now": "G.S.R. 880(E), Companies (Specification of Definition Details) Amendment Rules, 2025, dated 01-12-2025",
    "instrument": "G.S.R. 880(E), Companies (Specification of Definition Details) Amendment Rules, 2025, dated 01-12-2025",
    "is_at_read_date": "CURRENT",
    "obligation_id": "CA13-S2-85-SMALL",
    "provision": "Companies Act 2013, s.2(85)",
    "reference": null,
    "was_at_document_date": "CURRENT"
   }
  ],
  "turn_id": "t_65dde3494c4d",
  "uses_model": false,
  "what_it_is_not": [
   "that the document is valid, correctly drafted, or legally effective",
   "that the obligations named here are the whole of the Act that applies",
   "that a row marked verified is compliant -- only that its legal basis is current"
  ]
 },
 "followup_turnover": {
  "as_of": "2026-09-15",
  "citations": [
   {
    "cite": "Companies Act 2013, s.2 (Definitions)",
    "defects": [],
    "evidence_state": "CORROBORATED",
    "ref": "ACT:COMPANIES_ACT_2013:S2",
    "retrieved_on": [
     "2026-08-18",
     "2026-08-19"
    ],
    "source_url": "https://www.indiacode.nic.in/SectionPageContent?actid=AC_CEN_22_29_00008_201318_1517807327856&sectionID=185",
    "title": "Definitions",
    "unusable_reason": null,
    "usable_for_answering": true
   }
  ],
  "context": {
   "document_date": null,
   "kind": "general"
  },
  "evidence_pack": {
   "abstain_reason": "",
   "insufficient_evidence": false,
   "missing": [],
   "query_expansions": [],
   "retrieval_query": "s.2(85)",
   "route": "exact",
   "unusable_keys": [],
   "usable_keys": [
    "ACT:COMPANIES_ACT_2013:S2"
   ]
  },
  "figures": [
   {
    "amount": "₹100 crore",
    "effective_from": "2025-12-01",
    "effective_to": null,
    "evidence_state": "CORROBORATED",
    "instrument": "G.S.R. 880(E), Companies (Specification of Definition Details) Amendment Rules, 2025, dated 01-12-2025",
    "key": "small_company.turnover.prescribed",
    "rupees": 1000000000,
    "source_url": "https://egazette.gov.in/WriteReadData/2025/268124.pdf"
   }
  ],
  "generated_at": "2026-09-15T00:00:00Z",
  "law_version": {
   "basis": "CURRENT_CONSOLIDATION_AS_INGESTED",
   "corpus_fetched": [
    "2026-08-18"
   ],
   "point_in_time_verified": false,
   "statement": "This pack carries the CURRENT CONSOLIDATION of the Companies Act 2013 as India Code rendered it when the corpus was ingested (2026-08-18). It is NOT a point-in-time version of the law and carries no verified commencement or amendment date. The amendment vintage of individual provisions is not uniform and not fully known: SD-002 confirms that some records carry pre-amendment wording while the same publisher's PDF carries later wording. Those provisions are marked unusable in this pack. Point-in-time reconstruction exists in this system but is UNVERIFIED against any external source, so no statement here is a statement about the law as it stood on any past date."
  },
  "parent_turn_id": "t_20ccadb72b4b",
  "question": "And the turnover limit?",
  "schema": "placedon.ask/0",
  "scope": {
   "held": [
    "Companies Act, 2013"
   ],
   "sentence": "1 of 9 in-scope bodies of law are held"
  },
  "state": "answered",
  "turn_id": "t_35e5e8a47ea0",
  "uses_model": false
 },
 "out_of_scope_fema": {
  "as_of": "2026-09-15",
  "body": {
   "covers": "foreign investment, sectoral caps, reporting (FC-GPR, FC-TRS), downstream investment",
   "key": "FEMA1999",
   "name": "Foreign Exchange Management Act, 1999 and the FDI rules",
   "regulator": "RBI / DPIIT",
   "scope_status": "DECLARED"
  },
  "context": {
   "document_date": null,
   "kind": "general"
  },
  "generated_at": "2026-09-15T00:00:00Z",
  "held": [
   "Companies Act, 2013"
  ],
  "question": "What must we report to RBI for this share allotment to a foreign investor?",
  "reason": "Foreign Exchange Management Act, 1999 and the FDI rules (RBI / DPIIT) is within scope — it covers foreign investment, sectoral caps, reporting (FC-GPR, FC-TRS), downstream investment — but no instrument has been acquired, so nothing here can be decided. Nothing acquired. Sectoral caps change by press note, which is a different acquisition problem from a Gazette rule. This is a statement about what we hold, not a finding that no obligation applies.",
  "schema": "placedon.ask/0",
  "scope": {
   "held": [
    "Companies Act, 2013"
   ],
   "sentence": "1 of 9 in-scope bodies of law are held"
  },
  "state": "out_of_scope",
  "turn_id": "t_53d5771a2f6d",
  "uses_model": false
 },
 "partial_nothing_confirmed": {
  "as_of": "2026-09-15",
  "confirmed": [],
  "context": {
   "document_date": null,
   "kind": "general"
  },
  "evidence_pack": {
   "abstain_reason": "HELD_NOT_ADMITTED",
   "insufficient_evidence": true,
   "missing": [
    "RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R2 (Definitions) was cited and DOES exist, but is not admitted for model use: UNREVIEWED. Its text is unknown to you.",
    "No provision was retrieved at all. This pack is empty."
   ],
   "query_expansions": [],
   "retrieval_query": "rule 2(1)(t)",
   "route": "abstain",
   "unusable_keys": [],
   "usable_keys": []
  },
  "generated_at": "2026-09-15T00:00:00Z",
  "law_version": {
   "basis": "CURRENT_CONSOLIDATION_AS_INGESTED",
   "corpus_fetched": [],
   "point_in_time_verified": false,
   "statement": "This pack carries the CURRENT CONSOLIDATION of the Companies Act 2013 as India Code rendered it when the corpus was ingested (an unrecorded date). It is NOT a point-in-time version of the law and carries no verified commencement or amendment date. The amendment vintage of individual provisions is not uniform and not fully known: SD-002 confirms that some records carry pre-amendment wording while the same publisher's PDF carries later wording. Those provisions are marked unusable in this pack. Point-in-time reconstruction exists in this system but is UNVERIFIED against any external source, so no statement here is a statement about the law as it stood on any past date."
  },
  "not_confirmed": [
   {
    "detail": "RULE:COMPANIES_MEETINGS_BOARD_POWERS_2014:R2 (Definitions) was cited and DOES exist, but is not admitted for model use: UNREVIEWED. Its text is unknown to you.",
    "kind": "pack_missing"
   },
   {
    "detail": "No provision was retrieved at all. This pack is empty.",
    "kind": "pack_missing"
   }
  ],
  "question": "What does rule 2(1)(t) prescribe?",
  "schema": "placedon.ask/0",
  "scope": {
   "held": [
    "Companies Act, 2013"
   ],
   "sentence": "1 of 9 in-scope bodies of law are held"
  },
  "state": "partial",
  "turn_id": "t_6c77ad3b8015",
  "uses_model": false
 },
 "partial_s173_s16": {
  "as_of": "2026-09-15",
  "confirmed": [
   {
    "cite": "Companies Act 2013, s.173 (Meetings of Board)",
    "defects": [],
    "evidence_state": "CORROBORATED",
    "ref": "ACT:COMPANIES_ACT_2013:S173",
    "retrieved_on": [
     "2026-08-18",
     "2026-08-19"
    ],
    "source_url": "https://www.indiacode.nic.in/SectionPageContent?actid=AC_CEN_22_29_00008_201318_1517807327856&sectionID=49099",
    "title": "Meetings of Board",
    "unusable_reason": null,
    "usable_for_answering": true,
    "verbatim": "(1) Every company shall hold the first meeting of the Board of Directors\nwithin thirty days of the date of its incorporation and thereafter hold a minimum number of four meetings\nof its Board of Directors every year in such a manner that not more than one hundred and twenty days\nshall intervene between two consecutive meetings of the Board:\nProvided that the Central Government may, by notification, direct that the provisions of this subsection\nshall not apply in relation to any class or description of companies or shall apply subject to such\nexceptions, modifications or conditions as may be specified in the notification.\n(2) The participation of directors in a meeting of the Board may be either in person or through video\nconferencing or other audio visual means, as may be prescribed, which are capable of recording and\nrecognising the participation of the directors and of recording and storing the proceedings of such\nmeetings along with date and time:\nProvided that the Central Government may, by notification, specify such matters which shall not be\ndealt with in a meeting through video conferencing or other audio visual means.\n<sup>1</sup>[Provided further that where there is quorum in a meeting through physical presence of directors, any\nother director may participate through video conferencing or other audio visual means in such meeting on\nany matter specified under the first proviso.]\n(3) A meeting of the Board shall be called by giving not less than seven days notice in writing to\nevery director at his address registered with the company and such notice shall be sent by hand delivery or\nby post or by electronic means:\nProvided that a meeting of the Board may be called at shorter notice to transact urgent business\nsubject to the condition that at least one independent director, if any, shall be present at the meeting:\nProvided further that in case of absence of independent directors from such a meeting of the Board,\ndecisions taken at such a meeting shall be circulated to all the directors and shall be final only on\nratification thereof by at least one independent director, if any.\n(4) Every officer of the company whose duty is to give notice under this section and who fails to do\nso shall be liable to a penalty of twenty-five thousand rupees.\n(5) A One Person Company, small company and dormant company shall be deemed to have complied\nwith the provisions of this section if at least one meeting of the Board of Directors has been conducted in\neach half of a calendar year and the gap between the two meetings is not less than ninety days:\nProvided that nothing contained in this sub-section and in section 174 shall apply to One Person\nCompany in which there is only one director on its Board of Directors."
   }
  ],
  "context": {
   "document_date": null,
   "kind": "general"
  },
  "demand_signal": {
   "action": "tell_us_blocking"
  },
  "evidence_pack": {
   "abstain_reason": "",
   "insufficient_evidence": false,
   "missing": [
    "ACT:COMPANIES_ACT_2013:S16 exists in state SUSPENDED but is not admitted for model use"
   ],
   "query_expansions": [],
   "retrieval_query": "s.173 and s.16",
   "route": "exact",
   "unusable_keys": [],
   "usable_keys": [
    "ACT:COMPANIES_ACT_2013:S173"
   ]
  },
  "generated_at": "2026-09-15T00:00:00Z",
  "law_version": {
   "basis": "CURRENT_CONSOLIDATION_AS_INGESTED",
   "corpus_fetched": [
    "2026-08-18"
   ],
   "point_in_time_verified": false,
   "statement": "This pack carries the CURRENT CONSOLIDATION of the Companies Act 2013 as India Code rendered it when the corpus was ingested (2026-08-18). It is NOT a point-in-time version of the law and carries no verified commencement or amendment date. The amendment vintage of individual provisions is not uniform and not fully known: SD-002 confirms that some records carry pre-amendment wording while the same publisher's PDF carries later wording. Those provisions are marked unusable in this pack. Point-in-time reconstruction exists in this system but is UNVERIFIED against any external source, so no statement here is a statement about the law as it stood on any past date."
  },
  "not_confirmed": [
   {
    "detail": "ACT:COMPANIES_ACT_2013:S16 exists in state SUSPENDED but is not admitted for model use",
    "kind": "pack_missing"
   }
  ],
  "question": "What does s.173 require, and does s.16 apply here?",
  "schema": "placedon.ask/0",
  "scope": {
   "held": [
    "Companies Act, 2013"
   ],
   "sentence": "1 of 9 in-scope bodies of law are held"
  },
  "state": "partial",
  "turn_id": "t_87e16579523a",
  "uses_model": false
 }
};
