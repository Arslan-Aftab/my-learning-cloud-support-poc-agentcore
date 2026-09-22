# Handoff

Open work only. `README.md` holds the status quo. Delete a line here when it
is done and the README says so.

## Where the PoC stands

Retrieval works. A question returns the right past ticket from a 20 ticket
sample, and a metadata filter narrows the results to one variant.
`demo/draft_reply.py` drafts a labelled reply with citations on that sample.
The Demo scenarios in `README.md` have run on Sonnet 5 across every class and
both variants (2026-09-22, R20). `demo/app.py` has not been tried in a browser.

## Requirements not met

| # | Requirement | What is missing |
| --- | --- | --- |
| R3 | Redact PII in the drafted reply | Sonnet 5 paraphrases sources rather than quoting them, so no sample run has made the Guardrail fire end to end. Needs a question whose draft actually quotes a name, phone number or email. |
| R6 | Classify the ticket | 3 of 4 classes got the right label in only one of two variants; `unclear` never came back as `unclear`. Needs prompt work or more sample questions. |
| R10 | Evaluate drafts against real MLC replies | No held-out set and no judge. |
| R1, R2, R4 | Corpus, variants, retrieval | Proven on 20 tickets, not on 6,950. |

## Next steps

1. Load the full corpus. Run the ETL with no `--limit`, sync, ingest, and
   check the job statistics against 13,900 documents.
2. Re-run the PII demo scenario with a question whose draft is more likely to
   quote PII verbatim, to prove the Guardrail fires on the query-time path.
3. Tighten the classification prompt so `unclear` and the full-thread variant
   classify as reliably as the customer-only variant.
4. Decide Sonnet against Haiku for drafting, on quality and on cost.

## Open decisions

- No `-ro` profile exists. Every command runs as admin today.
- MLC staff see every tenant's tickets in the index. Customer isolation is
  unresolved, and it matters before anything leaves a demo.
- Chunking is fixed size. One vector per ticket is not guaranteed, and nobody
  has counted the chunks per ticket yet.
