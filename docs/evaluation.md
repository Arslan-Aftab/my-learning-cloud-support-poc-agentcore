# R10: evaluate drafts against real MLC replies

This job scores our own `Retrieve` plus `Converse` drafts against the real MLC
reply for the same ticket. It uses one Amazon Bedrock Evaluations RAG job,
retrieve-and-generate type, with bring your own inference responses. See the
"Evaluation (R10)" finding and the Evaluation row in Decisions in `README.md`
for the path we chose and why.

## What the job measures

The job compares, for each held-out ticket: our drafted reply, the retrieved
past tickets we grounded it in, and the real MLC reply. An LLM judge model
scores each pair. The built-in metrics for a retrieve-and-generate job are:

- `Builtin.Correctness`
- `Builtin.Completeness`
- `Builtin.Helpfulness`
- `Builtin.LogicalCoherence`
- `Builtin.Faithfulness` (hallucination against the retrieved tickets)
- `Builtin.Harmfulness`
- `Builtin.Stereotyping`
- `Builtin.Refusal`
- `Builtin.CitationCoverage`
- `Builtin.CitationPrecision`

## Judge model

`anthropic.claude-3-7-sonnet-20250219-v1:0`. It is on the supported evaluator
model list for eu-west-2 and needs no cross-Region inference profile, so
ticket text and the judge's read of it both stay in `eu-west-2` (R9). Claude
3.5 Sonnet v2, Claude Sonnet 4 and Amazon Nova Pro are also supported; rerun
`start` with a different `JUDGE_MODEL` in `tools/evaluate.py` to compare.

## Held-out set

20 tickets from tenants `spf`, `optalis` and `stjudescare` that are:

- not in the 20-ticket sample already ingested (`out/full/*.md`)
- closed (`closed.timestamp` is set)
- have an MLC reply (same `hasMlcReply` logic as `etl/split_tickets.py`)

The prompt is the customer-side text (subject plus customer messages), the
same render as the `customer` variant in `etl/split_tickets.py`. The
reference response is every MLC message, joined. The pipeline never sees the
MLC reply; it only retrieves against the `customer`-variant index.

## Running it

Each step needs the environment loaded first:

```shell
set -a; source .env; set +a
```

1. Build the dataset. No AWS write, only `Retrieve` and `Converse` reads:

   ```shell
   uv run tools/evaluate.py dataset data/super-admin.tickets.json
   ```

   Writes `out/eval/dataset.jsonl`, one line per ticket.

2. Upload the dataset to S3. **Ask before running**, it writes to the bucket:

   ```shell
   uv run tools/evaluate.py upload
   ```

3. Start the job. **Ask before running**, it creates a billed evaluation job.
   Needs `EvaluationRoleArn` from the stack outputs, so the template change in
   this PR must be deployed first:

   ```shell
   uv run tools/evaluate.py start <EvaluationRoleArn>
   ```

4. Poll status and get the results path:

   ```shell
   uv run tools/evaluate.py status <JobArn>
   ```

## Dataset schema

One JSON object per line, matching the retrieve-and-generate,
bring-your-own-inference-responses schema:

```json
{
  "conversationTurns": [{
    "prompt": {"content": [{"text": "the customer-side ticket text"}]},
    "referenceResponses": [{"content": [{"text": "the real MLC reply"}]}],
    "output": {
      "text": "our drafted reply",
      "modelIdentifier": "the generation model ARN",
      "knowledgeBaseIdentifier": "a label for our pipeline, matched by ragSourceIdentifier",
      "retrievedPassages": {"retrievalResults": [
        {"name": "ticketId", "content": {"text": "retrieved ticket text"}, "metadata": {"ticketId": "...", "tenant": "..."}}
      ]}
    }
  }]
}
```

## Cost estimate

Bedrock Evaluations has no per-job fee. Cost is the judge model's on-demand
token price for what it reads (prompt, retrieved passages, our draft, the
reference response) and writes (score plus explanation) per metric, per
ticket. For 20 tickets, 10 metrics, roughly 2,000 input and 150 output tokens
per judge call: about 400,000 input and 30,000 output tokens total. At Claude
3.5/3.7 Sonnet on-demand rates ($3 per million input, $15 per million output
tokens), that is under $2. Confirm the exact rate for the judge model and
region in the Bedrock console before running.

## Doc references

- [Evaluate the performance of RAG sources](https://docs.aws.amazon.com/bedrock/latest/userguide/evaluation-kb.html)
- [Creating a retrieve-and-generate RAG evaluation job](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-evaluation-create-randg.html)
- [Creating a prompt dataset for retrieve-and-generate RAG evaluation jobs](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-evaluation-prompt-retrieve-generate.html)
- [Create a prompt dataset for retrieve-only RAG evaluation jobs](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-evaluation-prompt-retrieve.html)
- [Evaluate model performance using another LLM as a judge](https://docs.aws.amazon.com/bedrock/latest/userguide/evaluation-judge.html) (supported judge models)
- [Service role requirements for knowledge base evaluation jobs](https://docs.aws.amazon.com/bedrock/latest/userguide/rag-eval-service-roles.html) (trust policy)
- [Required service role permissions for creating a model evaluation job that uses a judge model](https://docs.aws.amazon.com/bedrock/latest/userguide/judge-service-roles.html) (S3 and InvokeModel actions)
- [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)

## Left unclear by the docs

The retrieve-and-generate dataset page does not state a minimum dataset
size, only a maximum of 1,000 prompts. Record-count and file-size limits for
a job below any minimum are account quotas, not fixed numbers in the guide;
check the Bedrock service quotas page before sizing a larger run. The docs
also do not say what happens if `knowledgeBaseIdentifier` in the dataset does
not exactly match `ragSourceIdentifier` in the job request; `tools/evaluate.py`
keeps both as the same constant, `RAG_SOURCE`, to avoid finding out.
