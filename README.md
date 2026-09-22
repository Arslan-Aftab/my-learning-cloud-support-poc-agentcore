# my-learning-cloud-support-poc-agentcore

Proof of concept for My Learning Cloud (MLC). The tool reads an escalated support
ticket from the Lumis platform, finds similar past tickets, and drafts a reply for
a human support agent to review. Nothing is sent to a customer.

Funded by AWS ($15,000, covers build and compute). Lambert Labs creates a
separate AWS account, gives MLC admin users in it, and hands the account to MLC
at the end. Sources: AI Assessment Report, workshop notes 2026-07-20, deep dive
2026-08-11, kick-off 2026-09-07. All are in the project Google Drive folder.

## Architecture

```
super-admin.tickets.json ──► etl/split_tickets.py ──► out/{full,customer}/<ticketId>.md
                                                       + .metadata.json sidecars
                                                              │  aws s3 sync
                                                              ▼
                                                     S3 bucket ──► Managed Knowledge Base
                                                                    (S3 connector)
new ticket ──► demo/draft_reply.py ──► Retrieve ──► Converse + Guardrail ──► console
           └─► demo/app.py (Streamlit, same pipeline) ──────────────────────► browser
```

## Setup

### Prerequisites

Once per machine.

- [uv](https://docs.astral.sh/uv/). It fetches Python and every dependency,
  so there is nothing to install first. Run each script with `uv run`.
- `cfn-lint`: `uv tool install cfn-lint`.
- AWS CLI 2.36 or later: `brew install awscli`. Older builds reject
  `managedSearchConfiguration`.
- Access to the PoC account `938733851942` in the Lambert Labs organisation
  through the `ll-aws-main` SSO session. Add the profile to `~/.aws/config`.

  ```ini
  [profile mlc-support-poc]
  sso_session = ll-aws-main
  sso_account_id = 938733851942
  sso_role_name = AdministratorAccess
  region = eu-west-2
  ```

- The ticket export. Download `super-admin.tickets.json` from the project
  Drive folder to `data/`. The password is in the Teams chat. Never commit it.
- Model access. The first Bedrock call to Claude Sonnet 5 from a new account
  fails with `AccessDeniedException: Your account is currently being
  verified`. No action is needed. AWS verifies the account and emails when
  the Marketplace subscription is active, within a few hours. Until then,
  pick Haiku in the page, or pass `model="Haiku"` to `draft()`.

Sign in before each session: `aws sso login --profile mlc-support-poc`.

### Deploying

The template creates the ticket bucket, the Knowledge Base role, the managed
Knowledge Base, the S3 data source, the ingestion log group and the PII
Guardrail. Nothing else is needed.

1. Lint:

   ```shell
   cfn-lint --regions eu-west-2 -t infrastructure/template.yaml
   ```

2. Deploy. Repeat after every template change:

   ```shell
   aws cloudformation deploy --stack-name mlc-support-poc \
     --profile mlc-support-poc --region eu-west-2 \
     --template-file infrastructure/template.yaml \
     --capabilities CAPABILITY_NAMED_IAM
   ```

3. Write the profile, the region, the stack outputs and the two model ARNs to
   `.env`, which git ignores:

   ```shell
   { echo "AWS_PROFILE=mlc-support-poc"
     echo "AWS_REGION=eu-west-2"
     echo "SonnetModelArn=arn:aws:bedrock:eu-west-2:938733851942:inference-profile/eu.anthropic.claude-sonnet-5"
     echo "HaikuModelArn=arn:aws:bedrock:eu-west-2:938733851942:inference-profile/eu.anthropic.claude-haiku-4-5-20251001-v1:0"
     aws cloudformation describe-stacks --stack-name mlc-support-poc \
       --profile mlc-support-poc --region eu-west-2 \
       --query 'Stacks[0].Outputs[].join(`=`,[OutputKey,OutputValue])' \
       --output text | tr '\t' '\n'
   } > .env
   ```

### Loading tickets

Repeat when the export changes. Load a small sample first, check the
ingestion result and one retrieval, then load the three tenants.

In each new shell:

```shell
set -a; source .env; set +a
```

1. Split the export:

   ```shell
   uv run etl/split_tickets.py data/super-admin.tickets.json out/ --limit 20
   ```

   For the three tenant corpus, filter by tenant. `--limit` caps the total:

   ```shell
   uv run etl/split_tickets.py data/super-admin.tickets.json out/ \
     --tenants spf,optalis,stjudescare --limit 200
   ```

2. Upload. `--delete` removes files that are no longer in `out/`, which
   avoids the re-ingest failure noted in Findings:

   ```shell
   aws s3 sync out/ s3://$BucketName/tickets/ --delete
   ```

3. Start the ingestion job:

   ```shell
   aws bedrock-agent start-ingestion-job \
     --knowledge-base-id $KnowledgeBaseId --data-source-id $DataSourceId
   ```

4. Poll until the status is `COMPLETE` and `numberOfNewDocumentsIndexed` is
   not zero:

   ```shell
   aws bedrock-agent list-ingestion-jobs \
     --knowledge-base-id $KnowledgeBaseId --data-source-id $DataSourceId \
     --query 'ingestionJobSummaries[0].[status,statistics]'
   ```

5. If documents failed, read the reasons:

   ```shell
   aws logs filter-log-events --log-group-name $IngestionLogGroup \
     --filter-pattern '{ $.event.error_message = * }' \
     --query 'events[].message' --output text | head
   ```

## Demo

Run this once the tickets are loaded (see Loading tickets above).

```shell
set -a; source .env; set +a
```

```shell
uv run demo/app.py
```

The page opens in a browser. The sidebar holds three settings: **Model**
(Sonnet or Haiku), **Ticket contents** (full thread or customer only), and
**Tenant** (empty searches all tenants). Paste a question in the box and
click **Draft reply**.

> **Note** The same pipeline runs from the command line, with no browser:
> `uv run demo/draft_reply.py "<question>"`.

### Draft a how-to reply with cited sources

Paste this question:

```
How do I view completion of a policy that is not mandatory?
```

Leave the sidebar at its defaults. The page shows a labelled draft. Each
cited ticket ID appears in the "Past tickets used" list below the draft, for
example `[K2QNN Password reset email]`.

**Proves:** R4, R5, R8.

### Ask for data the customer must supply, see the screen named

Ask a `tenant-data` style question, for example one about a compliance or
completion report for a named tenant. Set **Ticket contents** to customer
only. The draft is labelled `tenant-data`, names the screen (for example
`Compliance Matrix Report`), and lists the fields to request, such as roles,
locations, tenant name and browser.

**Proves:** R6, R7.

> **Note** The `tenant-data` label was correct in the customer-only variant
> but not in the full-thread variant. Pick the customer-only variant for a
> reliable demo.

### Paste a ticket that holds a name and a phone number, see them masked or paraphrased away

Ask about the ticket that names a person and gives a phone number (ticket
`LN2Z5` in the 20-ticket sample). The draft paraphrases and cites the source
without quoting the name or the number, so no PII reaches the screen.

**Proves:** R3, partly. The Guardrail's `ANONYMIZE` action masks PII when it
reaches model output, confirmed by a unit call, but no sample run has made
the Guardrail fire on this query-time path, because Sonnet 5 paraphrases
rather than quotes its sources.

### Ask something the tickets cannot answer, see an unclear label or a refused draft

Ask a question with no match in the loaded sample. Today the label is
unreliable: an `unclear` question came back labelled `tenant-data`, not
`unclear`, in both variants.

**Proves:** R6, partly. R19 is not yet deployed; once the contextual
grounding Guardrail is live, a question the sources cannot support should
instead return a blocked or flagged draft.

### Filter to one tenant, see the sources change

Set **Tenant** to one tenant name, then repeat the how-to question. The "Past
tickets used" list shows only that tenant's tickets.

**Proves:** R2, R9.

## Requirements

`implemented` = built and shown to work. `partial` = part of the path is
proven. `validated` = not built, but the docs or a spike show it works. `out` =
not possible or out of scope. `open` = agreed as a goal or a spike, not started.
The Note column names the demo scenario and the date that proved it.

| # | Requirement | Status | Note |
| --- | --- | --- | --- |
| R1 | Split the export into one document per ticket with metadata | implemented | `etl/split_tickets.py`. 6,950 tickets, 13,900 documents, 11 MB. |
| R2 | Ingest full-thread and customer-only variants side by side | implemented | "Filter to one tenant" scenario, 2026-09-14: a `variant` filter returned customer chunks only. |
| R3 | Redact PII in the drafted reply | partial | "Paste a ticket that holds a name and a phone number" scenario, 20-ticket sample (2026-09-22): the question's top source (`LN2Z5`) names a person and gives a phone number, both variants. Sonnet 5 paraphrased and cited the source without quoting the name or the number, so the Guardrail did not fire in either run. A separate unit call still confirms `ANONYMIZE` masks PII once it reaches output (2026-09-14). The query-time path stays unproven until a draft actually quotes PII. |
| R4 | Retrieve similar past tickets for a new ticket | implemented | "Draft a how-to reply" scenario, 2026-09-14: `Retrieve` ranked the matching ticket first at score 0.75. |
| R5 | Draft a reply with citations to source ticket IDs | implemented | "Draft a how-to reply" scenario, 2026-09-22: Haiku cited `[K2QNN]` and `[LR232]`, both in the five retrieved chunks. Sonnet 5 first cited the subject alone; after a prompt fix it cited `[K2QNN Password reset email]`, confirmed across 12 runs, every cited ID present in that run's sources. |
| R6 | Classify the ticket: `howto`, `tenant-data`, `bug`, `unclear` | partial | "Ask for data the customer must supply" and "Ask something the tickets cannot answer" scenarios, Sonnet 5, one question per class, both variants (2026-09-22): `howto` correct in both variants; `tenant-data` correct in the customer variant, mislabelled `bug` in the full variant; `bug` correct in the full variant, mislabelled `howto` in the customer variant; the `unclear` question was labelled `tenant-data` in both variants, never `unclear`. 3 of 4 classes got the right label in at least one variant. |
| R7 | Signpost for `tenant-data` tickets: name the screen and the data to request | implemented | "Ask for data the customer must supply" scenario, Sonnet 5, customer variant (2026-09-22): draft named the screen (`Compliance Matrix Report`) and listed the roles, locations, tenant name and browser to request. |
| R8 | Human review of every draft | validated | Output is console or page text. Nothing is sent. |
| R9 | Data stays in UK or EU | validated | `eu-west-2` plus `eu.` inference profile. |
| R10 | Evaluate drafts against real MLC replies on held-out tickets | partial | Path chosen: Bedrock Evaluations, retrieve-and-generate RAG job, bring your own inference responses (see Findings). Not built. |
| R11 | Keep idle infra cost near zero | validated | Managed Knowledge Base bills storage and retrievals only. |
| R12 | Answer questions that need live tenant data from Lumis | out | No Lumis API in scope. The draft asks the customer for the data. |
| R13 | Write suggestions back into Lumis | out | Kick-off decision. |
| R14 | Handle customer-specific jargon | out | Revisit after evaluation. Tenant metadata filter is the first idea. |
| R15 | Daily re-sync of new tickets | out | Manual re-run of ETL and sync job in the PoC. |
| R16 | Ground-truth knowledge base or how-to wiki | out | Deferred at the deep dive. |
| R17 | Agentic retrieval: plan the search, query again with new filters or terms until the sources are useful | open | Spike on `AgenticRetrieveStream`. It is built into managed Knowledge Bases, takes metadata filters per retriever, and streams a cited answer, so it may replace `Retrieve` plus `Converse`. Its Guardrail supports `BLOCK` only, not `MASK`, so R3 needs a separate `ApplyGuardrail` call on the answer. Compare draft quality and cost against the one-shot path. |
| R18 | Batch processing to cut cost | partial | Design settled: on-demand front end, nightly batch job for new tickets. AgentCore Runtime has no batch mode. No batch job has run yet with our model ID, and the batch model table lists Sonnet 4.5, not Sonnet 5. See Findings. |
| R19 | Ground every draft in the retrieved tickets and minimise hallucination | partial | The Guardrail contextual grounding policy is in `infrastructure/template.yaml` (GROUNDING and RELEVANCE, threshold 0.5) and `demo/draft_reply.py` passes the retrieved chunks and the question as `guardContent` with `grounding_source` and `query` qualifiers. `cfn-lint` passes. Deploy and a live run are pending; see "Ask something the tickets cannot answer" in Demo. |
| R20 | Detailed testing on the 20 ticket sample before the full corpus is loaded | implemented | The Demo scenarios ran on Sonnet 5 across all four classes and both variants on the 20 ticket sample (2026-09-22). See R3, R6, R7 for the findings. The full load can proceed. |

## Decisions

| Area | Decision | Why |
| --- | --- | --- |
| Region | `eu-west-2` London | UK or Ireland data residency. Every service below is available there. |
| Retrieval | Bedrock **Managed** Knowledge Base, S3 connector | $5 per GB stored per month, $1 per 1,000 retrievals. Embedding model, reranker and hybrid search are included. Nothing to provision. The corpus is well under 1 GB. |
| Document variants | Ingest each ticket twice: full thread and customer side only. Tag each file with `variant` metadata. Filter on `variant` at retrieval. | The customer text matches how a new ticket is phrased. The full thread adds the MLC answers, which may help or may add noise. One index compares both. |
| Query API | `Retrieve` with `managedSearchConfiguration`, then one `Converse` call with the Guardrail attached | `RetrieveAndGenerate` is not supported for managed Knowledge Bases. Two calls, and the prompt is ours to control. `AgenticRetrieveStream` was spiked as the multi-step alternative and rejected for now, see R17. |
| Generation model | Claude Sonnet, `eu.` inference profile | Draft quality. The `eu.` profile keeps inference inside the EU. Try Haiku if cost matters. |
| PII | Bedrock Guardrail, PII set to `ANONYMIZE` on model output only. The index holds the tickets as written. | The Knowledge Base stays faithful to the source. The draft reply is what leaves the tool, so redaction sits there. |
| Runtime | Plain Bedrock API calls from Python. No AgentCore, no Strands, no Bedrock Agents. | The tool is a fixed pipeline with no tool loop, no session and no external caller. |
| Infrastructure | One CloudFormation template, `infrastructure/template.yaml` | Five resources. `AWS::Bedrock::KnowledgeBase` supports `ManagedKnowledgeBaseConfiguration`. |
| Output | Text in the console. No write-back to Lumis. | Kick-off decision. |
| Corpus scope | Escalated tickets only, including tickets assigned to developers. Up to 200 tickets from three tenants in the PoC, not all 6,950. | Kick-off decision on escalation. Thousands of tickets add index bloat that no test refers to. |
| Document format | One Markdown file per ticket. Structured fields go in the `.metadata.json` sidecar. | The S3 connector accepts `.txt`, `.md`, `.html`, `.docx`, `.csv`, `.xlsx` and `.pdf`. It does not accept `.json` as a document. Markdown gives the embedding model prose without keys and braces. |
| Bad tickets | Keep all. Store `reopened` as metadata. Test with and without a filter. | Scott's "closed twice" heuristic is a signal, not a verdict. |
| Evaluation | Bedrock Evaluations, retrieve-and-generate RAG job, **bring your own inference responses**. Reference response is the real MLC reply from the `full` variant. The pipeline sees only the `customer` variant. | A first-party job, not a hand-written harness. MLC can rerun it after the PoC to test a new prompt or a new Knowledge Base setup. |
| Batch processing | Keep the interactive front end on on-demand `Converse`. Add a nightly Lambda or Step Functions job later: `Retrieve` per new ticket, then one Bedrock batch inference job for the drafts. | AgentCore Runtime has no batch-invoke operation, only synchronous invoke, streaming and one long-running async session. Batch inference halves the on-demand token price. See R18. |
| Grounding | Bedrock Guardrail contextual grounding, `GROUNDING` and `RELEVANCE` filters, threshold 0.5 on both, action `BLOCK` | A human reviews every draft before it reaches a customer (R8), so the filter is a last-resort catch for a reply that ignores the retrieved tickets, not a strict gate. 0.5 is the AWS console default and blocks only responses AWS scores below even odds of being grounded or relevant. A threshold near 0.99 would block most drafts, including correct ones; a threshold near 0 would let hallucination through. |

Add AgentCore only when Lumis calls the tool over HTTP, when the agent needs the
Lumis API through a Gateway with permissions separate from a user token, when
you want AgentCore Evaluations, or for the retrieval loop in R17.

## Findings

- The managed Knowledge Base offers built-in or fixed-size chunking only. One
  vector per ticket is not guaranteed. Use a large fixed size and check the chunk
  count after ingestion.
- A managed Knowledge Base supports `Retrieve` only, not `RetrieveAndGenerate`.
  `Retrieve` takes `managedSearchConfiguration`, not `vectorSearchConfiguration`,
  and needs AWS CLI 2.36 or boto3 1.43 or later.
- Managed Knowledge Base metadata sidecars use typed values:
  `{"key": {"value": {"type": "STRING", "stringValue": "x"}}}`. Types are
  `STRING`, `NUMBER` and `STRING_LIST`. `BOOLEAN` is rejected, so booleans are
  `"true"` and `"false"` strings. The flat format is ignored.
- Managed Knowledge Base metadata filters support `equals`, `in`, `notIn` and
  range operators. `startsWith` and `stringContains` are not supported.
- The ingestion job statistics do not explain a failed document. Per-document
  reasons are in the ingestion log group that the stack creates.
- A managed Knowledge Base rejects the plain `S3` data source type. Use
  `MANAGED_KNOWLEDGE_BASE_CONNECTOR` with `connectorParameters.type: S3`.
  Data source creation is asynchronous; wait for `AVAILABLE` before ingesting.
- The S3 connector treats one file as one document. The 27 MB export must be
  split into one file per ticket with a `<file>.metadata.json` sidecar.
- `Action: ANONYMIZE` anonymises model output only. `ApplyGuardrail` with
  `source INPUT` returns `NONE`.
- Guardrail PII masking applies to the API response only. Model invocation logs,
  if enabled, hold unmasked text. Keep invocation logging off or encrypt the log
  group.
- Re-ingesting a file that already exists in a Knowledge Base fails. Delete
  the document first.
- Tickets combine `thread` (customer), `adminThread` (MLC, `note: true` means
  internal), `parentThread` (parent tenant) and sometimes `systemThread`. Sort by
  `timestamp`. Drop notes and system messages. The `howto` / `bug` type field was
  never used.
- `AgenticRetrieveStream` (R17 spike, `demo/agentic_reply.py`) is a no-go. It
  rejects a Guardrail with an `ANONYMIZE` action, so R3 cannot attach. It has
  no system prompt, so it cannot emit the `Label:` line. Retrieval quality and
  latency matched `Retrieve` plus `Converse` on three questions.

### Evaluation (R10)

Amazon Bedrock Evaluations runs RAG evaluation jobs against a Knowledge Base:
[Evaluate the performance of RAG sources](https://docs.aws.amazon.com/bedrock/latest/userguide/evaluation-kb.html).
There are two job types. A **retrieve-only** job scores the chunks a Knowledge
Base returns. A **retrieve-and-generate** job scores the chunks and the
generated answer together, with LLM-as-a-judge metrics: correctness,
completeness, faithfulness (hallucination), citation precision, citation
coverage and harmfulness
([Evaluate model performance using another LLM as a judge](https://docs.aws.amazon.com/bedrock/latest/userguide/evaluation-judge.html)).

A **managed** Knowledge Base is a valid inference source for a RAG evaluation
job: the same `KnowledgeBaseIdentifier` used for `Retrieve` calls works here
([Creating a retrieve-and-generate RAG evaluation job](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-evaluation-create-randg.html)).
But the tool does not call `RetrieveAndGenerate` on a managed Knowledge Base
(see Findings above), so the job cannot invoke the Knowledge Base for us end
to end. The **bring your own inference responses** option covers this: pick
"Bring your own inference responses" as the inference source, and Bedrock
skips its own retrieve-and-generate step and grades the output we supply
([Inference source for Knowledge Base evaluation](https://docs.aws.amazon.com/help-panel/bedrock/latest/console/hp-kb-evaluation-inference.html)).
Evaluator (judge) models listed for eu-west-2 include Anthropic Claude 3.5
Sonnet v2, Claude 3.7 Sonnet, Claude Sonnet 4 and Amazon Nova Pro
([Supported evaluator models](https://docs.aws.amazon.com/bedrock/latest/userguide/evaluation-judge.html)).

The dataset is a JSONL prompt file in S3. For a bring-your-own-responses job,
each line holds a `conversationTurns` array with `prompt` (the ticket query),
`referenceResponses` (the real MLC reply), and an `output` block that carries
our own `knowledgeBaseIdentifier` and `retrievedResults`. `referenceContexts`
is optional and only feeds custom metrics, not the built-in ones
([Create a prompt dataset for retrieve-only RAG evaluation jobs](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-evaluation-prompt-retrieve.html)).

Bedrock Evaluations has no per-job fee. Cost is the judge model's on-demand
token price for the input it reads (prompt, retrieved context, generated
answer) and the output it writes (score and explanation), billed the same way
as any other model invocation
([Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)). For a few
hundred held-out tickets this is a few dollars, not a line item to plan
around.

Nothing in Bedrock evaluates a prompt or a Guardrail directly. Prompt
management lets you version prompt variants and run one manually in the
console's prompt builder, and Guardrails has a console test panel, but
neither compares an output against a reference response or produces a metric
([Construct and store reusable prompts with Prompt management](https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-management.html)).
Both are for trying a change by hand, not for scoring it against held-out
tickets, so R10 still needs the RAG evaluation job above.

**Recommended path**: one retrieve-and-generate RAG evaluation job, bring
your own inference responses. A small Python script still has to: split each
held-out ticket's `full` variant into prompt (customer side) and reference
response (MLC's reply); run one `Retrieve` plus `Converse` call per ticket
against the `customer`-only index, the same pipeline the tool uses at query
time; write one JSONL line per ticket with `prompt`, `referenceResponses` and
our `output.retrievedResults`; upload the file to S3; and call
`CreateEvaluationJob` (or the console) with that S3 URI. Bedrock does the
judging. If a managed Knowledge Base or our two-call output shape ever stops
being accepted by the bring-your-own path, the fallback is the hand-written
Python harness the requirement first proposed: same held-out set, same LLM
judge prompt, called directly instead of through a Bedrock evaluation job.

### R18: batch processing

**AgentCore Runtime cannot run in batch.** It offers only synchronous invoke,
streaming, and one long-running async session per request
([Handle asynchronous and long running agents](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-long-run.html)).

| | Invocation batch | Agentic |
| --- | --- | --- |
| Steps | Fixed: `Retrieve` per ticket, then one Bedrock batch inference job for all the drafts | The model plans its own retrieval steps per ticket, on AgentCore Runtime or Lambda |
| Model call | Bedrock batch inference, `InvokeModel` or `Converse` body per JSONL record ([Format and upload your batch inference data](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference-data.html)) | On-demand `Converse`, no batch mode |
| Price | 50% of on-demand, both generation models by cross-Region inference profile in `eu-west-2`: `anthropic.claude-sonnet-4-5-20250929-v1:0` and `anthropic.claude-haiku-4-5-20251001-v1:0` ([batch inference support table](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference-supported.html), [pricing](https://aws.amazon.com/bedrock/pricing/)) | Full on-demand price |
| Latency | Hours. No fixed SLA; a job carries an optional `timeoutDurationInHours` ([Create a batch inference job](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference-create.html)). Fits a nightly run | Minutes |

An agentic loop can be unrolled into N batch jobs (plan job, on-demand
`Retrieve`, draft job), but every ticket then takes the same fixed steps, so
it loses the per-ticket adaptivity that makes it agentic.

Batch inference is not supported for provisioned models, and it does not
support tool calling or structured output
([Process multiple prompts with batch inference](https://docs.aws.amazon.com/bedrock/latest/userguide/batch-inference.html)).
Record-count and file-size minimums and maximums are account quotas, not
fixed numbers in the guide; check
[Amazon Bedrock service quotas](https://docs.aws.amazon.com/general/latest/gr/bedrock.html#limits_bedrock)
before sizing a job.

Fit for this PoC: the interactive front end (`demo/app.py`) needs an answer
per click, so it stays agentic on-demand. A nightly job over the day's new
tickets can use invocation batch, since nobody waits on it. Rough cost for
200 tickets a day, at roughly 3,000 input and 500 output tokens per draft:
about $1.80/day on-demand against about $0.90/day on batch, at published
Claude Sonnet rates of $3 per million input tokens and $15 per million output
tokens. Confirm the exact rate for the model ID and region in use in the
console; the ratio holds regardless.

The customer can run both approaches on the same held-out set through the
R10 evaluation job and compare price against quality.

## Repo layout

| Path | What |
| --- | --- |
| `etl/split_tickets.py` | Splits the export into per-ticket documents and metadata sidecars |
| `tests/` | Self-check for the ETL, with one fixture ticket |
| `infrastructure/template.yaml` | CloudFormation: bucket, Knowledge Base role, Knowledge Base, data source, Guardrail. |
| `demo/draft_reply.py` | Retrieve, Converse with the Guardrail, print the draft and the sources. |
| `demo/agentic_reply.py` | R17 spike of `AgenticRetrieveStream`. No-go, kept as evidence. |
| `demo/app.py` | Local Streamlit page around the same pipeline. See Demo above. |
| `data/` | Local ticket export. Git ignores it. |
| `out/` | ETL output. Git ignores it. |
| `HANDOFF.md` | Open work and next steps. This file holds the status quo. |

Every script carries a [PEP 723](https://peps.python.org/pep-0723/) header that
names its own dependencies. `uv run <script>` is enough on a clean machine.
There is no `requirements.txt` and no shared virtual environment.
