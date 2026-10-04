# Questions for a legal-AI vendor

Written for Spellbook, but they work for Harvey, Legora or anyone else. Every
one is a question a careful buyer should ask before trusting legal software, and
every one also happens to be diagnostic of whether the thing we are building has
a real edge.

Ask them openly, as an evaluating customer. A vendor's answer — including a
refusal to answer — is worth more than an inference drawn from their homepage,
and it comes without anything awkward in your history.

The ones marked **★** are the four that decide whether our differentiation is
real. If Spellbook answers all four the way we hope they cannot, the moat is
smaller than we think and we should know that now rather than later.

---

## Citations and evidence

**★ 1. When Ask gives an answer with a citation, does the citation resolve to an
exact passage, or to a document?**

If a lawyer clicks it, do they land on the sentence the answer rests on, or on a
50-page agreement they now have to search? Ask to see it on a real document.

**2. Is the cited text checked against the answer, or only retrieved alongside
it?**

Different things. Retrieval finds relevant text; verification proves the text
supports the claim. Which one happens?

**3. What happens if the model produces a citation to something that is not in
my documents? Is that detected, or does it reach me?**

---

## When the system does not know

**★ 4. What does the product do when it cannot find the source it needs?**

Three possible answers, and they are not equivalent: it says so and stops; it
answers from the model's general knowledge and flags that; or it answers and
does not distinguish. Ask which, and ask to see it happen.

**5. Can it tell me the difference between "this obligation does not apply to
you" and "I cannot tell whether it applies to you"?**

**6. Is there any category of question the product refuses outright?**

A product that never refuses is either much better than everything else, or is
not tracking the difference.

---

## The law itself, over time

**★ 7. If I ask about a contract signed in 2019, does the product apply the law
as it stood in 2019, or the law as it stands today?**

**8. Does the product hold amendment history for the statutes it covers, and can
it show me which amendment changed a provision and when that amendment
commenced?**

Notification and commencement are different dates in Indian law. A provision can
be notified and not yet in force.

**9. Where subordinate legislation sets an operative threshold, does the product
hold those rules — and what does it do when it does not?**

---

## What checks the model

**★ 10. Is there any check on the model's output that is not itself a model?**

Deterministic rules, arithmetic performed outside the model, a schema that
rejects a malformed answer — or is the reviewer the only check?

**11. Are calculations — dates, thresholds, notice periods, percentages — done
by the model or by code?**

**12. Is there any output the product will not release without human approval?**

---

## Evidence for the claims

**13. Is there a published benchmark? What is in it, who labelled it, and how
many items?**

Ask specifically: were the labels set by practising lawyers, and does the
benchmark contain examples the product gets *wrong*?

**14. What is the measured false-positive rate — cases where it says a document
is fine and it is not?**

For compliance work that direction is the dangerous one, and it is the number
most often not reported.

**15. What are the failure modes you know about and have not solved yet?**

The most informative question on this list. A vendor with a good answer is
worth taking seriously; a vendor with no answer either has not looked or will
not say.

---

## Jurisdiction and data

**16. Does the product cover Indian law, and specifically the Companies Act
2013 and its rules? If so, where does that corpus come from and how often is it
refreshed?**

**17. Is customer data used to train or improve any model, including your own
fine-tuning?**

The security page states zero data retention with the LLM providers. That is a
narrower claim than "we do not train on your data" — worth confirming
separately.

**18. Where is data processed, and is Indian data residency available?**

---

## How to read the answers

Question 15 tells you the most about the vendor. Questions 1, 4, 7 and 10 tell
you the most about us:

- If citations resolve to exact spans, our span-hashing is table stakes rather
  than an edge.
- If they refuse cleanly when a source is missing, our refusal behaviour is not
  a differentiator either.
- If they apply the law as it stood on a past date, point-in-time reconstruction
  is not a moat and we should reconsider the whole thesis.
- If a deterministic layer checks the model, the E3–E6 cascade is not unusual.

**Our current position is that a contract-review product has no reason to solve
7, because a contract has no commencement date, no amending instrument and no
Gazette notification.** If Spellbook answers 7 well, that reasoning is wrong,
and finding out now is worth more than being right about it later.
