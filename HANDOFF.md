# Handoff

Open work only. `README.md` holds the status quo. Delete a line here when it
is done and the README says so.

## Where the PoC stands

Retrieval works. A question returns the right past ticket from a 20 ticket
sample, and a metadata filter narrows the results to one variant.
`demo/draft_reply.py` drafts a labelled reply with citations on that sample
(T3 passed with Haiku on 2026-09-22). T4 and T5 are open, and `demo/app.py`
has not been tried in a browser.

## Requirements not met

| # | Requirement | What is missing |
| --- | --- | --- |
| R3 | Redact PII in the drafted reply | Guardrail attached to Converse. No run has surfaced PII yet (T4). |
| R6 | Classify the ticket | Only `howto` seen. Three classes untested (T5). |
| R7 | Signpost for `tenant-data` tickets | Prompt written. Not checked (T5). |
| R10 | Evaluate drafts against real MLC replies | No held-out set and no judge. |
| R1, R2, R4 | Corpus, variants, retrieval | Proven on 20 tickets, not on 6,950. |

## Next steps

1. Open `demo/app.py` in a browser and run T4 and T5 through it (R20).
2. Load the full corpus only after step 1. Run the ETL with no `--limit`,
   sync, ingest, and check the job statistics against 13,900 documents.
3. Pick the T4 questions from the real corpus: one whose matching tickets hold
   a personal name or a phone number, one whose tickets hold none.
4. Re-run every test and update the requirements table.
5. Decide Sonnet against Haiku for drafting, on quality and on cost.

## Open decisions

- Sonnet 5 is blocked by AWS account verification. See the README note under
  Prerequisites. Retry it before the Sonnet against Haiku decision.
- No `-ro` profile exists. Every command runs as admin today.
- MLC staff see every tenant's tickets in the index. Customer isolation is
  unresolved, and it matters before anything leaves a demo.
- Chunking is fixed size. One vector per ticket is not guaranteed, and nobody
  has counted the chunks per ticket yet.
