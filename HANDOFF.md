# Handoff

Open work only. `README.md` holds the status quo. Delete a line here when it
is done and the README says so.

## Where the PoC stands

Retrieval, drafting and the Streamlit app work on a 20 ticket sample from
three tenants (spf, optalis, stjudescare). Sonnet 5 drafts a labelled reply
with `[ID Subject]` citations. PII in the question and the retrieved tickets
is masked with `ApplyGuardrail` before the model, and again on the output.
The Guardrail on `main` scores grounding and relevance and denies off-topic
questions, but that version is not deployed: the live stack still runs the
older Guardrail. `demo/app.py` has a model, variant and tenant drop-down, a
grounding threshold slider and an editable draft with a copy button.

Open PRs, all into `main`, no code overlap:

| PR | Content | Blocked on |
| --- | --- | --- |
| #13 | R21 to R24 rows from the customer documents on Drive | Review |
| #14 | R22 cost model: `tools/cost_model.py` writes an xlsx with live Price List prices and adjustable parameters; `docs/cost-model.md` | Review. Sonnet 5 has no Price List entry for this account, so its price is a flagged fallback |
| #15 | R10 Bedrock Evaluations RAG job: `tools/evaluate.py`, `EvaluationRole` in the stack, `docs/evaluation.md`, 20 line dataset in `out/eval/` (local only) | Review, then deploy, upload and start (see Next steps) |

## Requirements not met

| # | Requirement | What is missing |
| --- | --- | --- |
| R3 | No PII in or out | The two-sided mask is coded but has not run live. No sample run has yet made the output Guardrail fire. |
| R6 | Classify the ticket | Labels unstable across variants; `unclear` never returned. Also 4 of 24 Sonnet 5 drafts in the eval dataset did not parse as JSON, so they fell back to `unclear` with the raw text as the reply. |
| R10 | Evaluate against real MLC replies | Job built in #15, not run. |
| R18 | Batch inference | Design and research done. No batch job has run. Sonnet 5 is not in the batch model table. |
| R19, R21 | Grounding scores, off-topic denial | In the template, not deployed. |
| R1, R2, R4 | Corpus | Proven on 20 tickets. The agreed load is all 227 tickets of the three tenants, not the full 6,950. |

## Next steps

Each step below that changes AWS state needs a yes from the user first.

1. Merge #13, #14, #15.
2. Deploy the stack. This ships the grounding scores, the off-topic topic and
   `EvaluationRole` in one deploy. Update `.env` from the outputs.
3. Run `uv run tools/evaluate.py upload`, then `start <EvaluationRoleArn>`.
   Estimated job cost under $2. Record the results in the R10 row.
4. Load the corpus: ETL with `--tenants spf,optalis,stjudescare` and no
   `--limit` (227 tickets), sync, ingest, check the job statistics, update the
   R1 row.
5. Start a `fix-classification` chat from a brief: make the Sonnet 5 JSON
   output parse every time, get `unclear` to return, stabilise labels across
   variants (R6), and find a question that makes the PII Guardrail fire (R3).
6. Run the Demo scenarios live on the deployed Guardrail to close R19 and R21.
7. Record the demo video once R3, R6 and R10 have evidence.

## Open decisions

- No `-ro` profile exists. Every command runs as admin today.
- MLC staff see every tenant's tickets in the index. Customer isolation is
  unresolved, and it matters before anything leaves a demo.
- Chunking is fixed size. Nobody has counted the chunks per ticket yet.
- Jira has no project key for this work, so nothing is tracked there.
- The global `Chat Roles` rule: the user has not yet agreed to the tighter
  wording (sub-agents on `haiku` or `sonnet`, no fixes from the PM chat).
- The first cost sheet on Drive is superseded by the second and not deleted.
