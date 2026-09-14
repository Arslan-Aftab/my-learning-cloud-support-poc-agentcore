# Handoff

Open work only. `README.md` holds the status quo. Delete a line here when it
is done and the README says so.

## Where the PoC stands

Retrieval works. A question returns the right past ticket from a 20 ticket
sample, and a metadata filter narrows the results to one variant. Nothing
drafts a reply yet, so the PoC does not answer its own question.

## Requirements not met

| # | Requirement | What is missing |
| --- | --- | --- |
| R3 | Redact PII in the drafted reply | The Guardrail works on its own. No drafting call attaches it yet. |
| R5 | Draft a reply with citations | `demo/draft_reply.py` is not written. |
| R6 | Classify the ticket | Same script. No prompt written. |
| R7 | Signpost for `tenant-data` tickets | Same script. No prompt written. |
| R10 | Evaluate drafts against real MLC replies | No held-out set and no judge. |
| R1, R2, R4 | Corpus, variants, retrieval | Proven on 20 tickets, not on 6,950. |

## Next steps

1. Load the full corpus. Run the ETL with no `--limit`, sync, ingest, and
   check the job statistics against 13,900 documents.
2. Write `demo/draft_reply.py`: `Retrieve`, build a prompt from the chunks,
   one `Converse` call with `guardrailConfig`. It covers T3, T4 and T5.
3. Pick the T4 questions from the real corpus: one whose matching tickets hold
   a personal name or a phone number, one whose tickets hold none.
4. Re-run every test and update the requirements table.
5. Decide Sonnet against Haiku for drafting, on quality and on cost.

## Open decisions

- No `-ro` profile exists. Every command runs as admin today.
- MLC staff see every tenant's tickets in the index. Customer isolation is
  unresolved, and it matters before anything leaves a demo.
- Chunking is fixed size. One vector per ticket is not guaranteed, and nobody
  has counted the chunks per ticket yet.
