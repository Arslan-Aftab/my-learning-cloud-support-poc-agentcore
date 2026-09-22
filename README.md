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

| Area | Decision | Why |
| --- | --- | --- |
| Region | `eu-west-2` London | UK or Ireland data residency. Every service below is available there. |
| Retrieval | Bedrock **Managed** Knowledge Base, S3 connector | $5 per GB stored per month, $1 per 1,000 retrievals. Embedding model, reranker and hybrid search are included. Nothing to provision. The corpus is well under 1 GB. |
| Document variants | Ingest each ticket twice: full thread and customer side only. Tag each file with `variant` metadata. Filter on `variant` at retrieval. | The customer text matches how a new ticket is phrased. The full thread adds the MLC answers, which may help or may add noise. One index compares both. |
| Query API | `Retrieve` with `managedSearchConfiguration`, then one `Converse` call with the Guardrail attached | `RetrieveAndGenerate` is not supported for managed Knowledge Bases. Two calls, and the prompt is ours to control. `AgenticRetrieveStream` is the multi-step alternative, see R17. |
| Generation model | Claude Sonnet, `eu.` inference profile | Draft quality. The `eu.` profile keeps inference inside the EU. Try Haiku if cost matters. |
| PII | Bedrock Guardrail, PII set to `ANONYMIZE` on model output only. The index holds the tickets as written. | The Knowledge Base stays faithful to the source. The draft reply is what leaves the tool, so redaction sits there. |
| Runtime | Plain Bedrock API calls from Python. No AgentCore, no Strands, no Bedrock Agents. | The tool is a fixed pipeline with no tool loop, no session and no external caller. |
| Infrastructure | One CloudFormation template, `infrastructure/template.yaml` | Five resources. `AWS::Bedrock::KnowledgeBase` supports `ManagedKnowledgeBaseConfiguration`. |
| Output | Text in the console. No write-back to Lumis. | Kick-off decision. |
| Corpus scope | Escalated tickets only, including tickets assigned to developers. Up to 200 tickets from three tenants in the PoC, not all 6,950. | Kick-off decision on escalation. Thousands of tickets add index bloat that no test refers to. |
| Document format | One Markdown file per ticket. Structured fields go in the `.metadata.json` sidecar. | The S3 connector accepts `.txt`, `.md`, `.html`, `.docx`, `.csv`, `.xlsx` and `.pdf`. It does not accept `.json` as a document. Markdown gives the embedding model prose without keys and braces. |
| Bad tickets | Keep all. Store `reopened` as metadata. Test with and without a filter. | Scott's "closed twice" heuristic is a signal, not a verdict. |
| Evaluation | Bedrock Evaluations, retrieve-and-generate RAG job, **bring your own inference responses**. Reference response is the real MLC reply from the `full` variant. The pipeline sees only the `customer` variant. | A first-party job, not a hand-written harness. MLC can rerun it after the PoC to test a new prompt or a new Knowledge Base setup. |

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

## Repo layout

| Path | What |
| --- | --- |
| `etl/split_tickets.py` | Splits the export into per-ticket documents and metadata sidecars |
| `tests/` | Self-check for the ETL, with one fixture ticket |
| `infrastructure/template.yaml` | CloudFormation: bucket, Knowledge Base role, Knowledge Base, data source, Guardrail. |
| `demo/draft_reply.py` | Retrieve, Converse with the Guardrail, print the draft and the sources. |
| `demo/app.py` | Local Streamlit page around the same pipeline. Paste a ticket, set tenant and variant, read the draft and the sources. |
| `data/` | Local ticket export. Git ignores it. |
| `out/` | ETL output. Git ignores it. |
| `HANDOFF.md` | Open work and next steps. This file holds the status quo. |

Every script carries a [PEP 723](https://peps.python.org/pep-0723/) header that
names its own dependencies. `uv run <script>` is enough on a clean machine.
There is no `requirements.txt` and no shared virtual environment.

## Prerequisites

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

Sign in before each session: `aws sso login --profile mlc-support-poc`.

> **Note** A new AWS account cannot call Claude Sonnet 5 until AWS has
> verified it, which takes a few hours. The call fails with
> `AccessDeniedException: Your account is currently being verified`. Until it
> clears, put `ModelArn=eu.anthropic.claude-haiku-4-5-20251001-v1:0` in
> `.env`.

## Deploying

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

3. Write the profile, the region, the stack outputs and the model ARN to
   `.env`, which git ignores:

   ```shell
   { echo "AWS_PROFILE=mlc-support-poc"
     echo "AWS_REGION=eu-west-2"
     echo "ModelArn=arn:aws:bedrock:eu-west-2:938733851942:inference-profile/eu.anthropic.claude-sonnet-5"
     aws cloudformation describe-stacks --stack-name mlc-support-poc \
       --profile mlc-support-poc --region eu-west-2 \
       --query 'Stacks[0].Outputs[].join(`=`,[OutputKey,OutputValue])' \
       --output text | tr '\t' '\n'
   } > .env
   ```

## Loading tickets

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

## Testing

Each test has one meaning. The table below is the only place that maps tests
to requirements. When a test passes, record the date and the evidence in the
[requirements](#requirements) table at the end of this file.

In each new shell:

```shell
set -a; source .env; set +a
```

| Test | Meaning | Requirements |
|---|---|---|
| T1 | Retrieve past tickets for a question | R4 |
| T2 | Retrieve with a metadata filter | R2 |
| T3 | Ask a question, get a drafted reply with citations | R5, R8 |
| T4 | Ask a question whose sources hold PII, get a redacted draft | R3 |
| T5 | Classify and signpost | R6, R7 |
| T6 | Compare a draft with the real MLC reply on a held-out ticket | R10 |
| T7 | Confirm region and idle cost | R9, R11 |

### T1 Retrieve

Ask a how-to question. Expect chunks whose `metadata.ticketId` values are real
ticket IDs and a sensible top result.

```shell
aws bedrock-agent-runtime retrieve --knowledge-base-id $KnowledgeBaseId \
  --retrieval-query '{"text":"How do I view completion of a policy that is not mandatory?"}' \
  --retrieval-configuration '{"managedSearchConfiguration":{"numberOfResults":3}}' \
  --query 'retrievalResults[].[score,metadata.ticketId,metadata.variant]'
```

### T2 Retrieve with a filter

Repeat T1 with a filter. Expect every result to have `variant` = `customer`.

```shell
  --retrieval-configuration '{"managedSearchConfiguration":{"numberOfResults":3,"filter":{"equals":{"key":"variant","value":"customer"}}}}'
```

### T3 Ask a question

`demo/draft_reply.py` runs T1, builds a prompt from the chunks and calls
`Converse` with the Guardrail attached. Type any support question. Expect a
draft that cites the ticket IDs it used and nothing sent anywhere.

```shell
uv run demo/draft_reply.py "How do I view completion of a policy that is not mandatory?"
```

The same pipeline runs in a local browser page. Paste a ticket, set the
tenant filter, the variant and the result count in the sidebar, and read the
draft with one expander per source. Nothing is hosted.

```shell
uv run demo/app.py
```

### T4 Ask a question that surfaces PII

Run T3 twice. First with a question whose matching tickets name a person or
give a phone number. Expect `{NAME}`, `{PHONE}` or `{EMAIL}` in the draft.
Then with a question whose tickets hold no PII. Expect an unchanged draft.
Pick both questions from the sample once the corpus is loaded.

The unit check below proves the Guardrail alone. Expect `action` =
`GUARDRAIL_INTERVENED`. The source must be `OUTPUT`; input is not redacted by
design.

```shell
aws bedrock-runtime apply-guardrail \
  --guardrail-identifier $GuardrailId --guardrail-version $GuardrailVersion \
  --source OUTPUT \
  --content '[{"text":{"text":"Please call Jane Smith on 07700 900123 or email jane@example.com"}}]'
```

### T5 Classify and signpost

Run T3 with one question per class: `howto`, `tenant-data`, `bug`, `unclear`.
Expect the right label on each. For `tenant-data`, expect the draft to name
the screen and the data to request from the customer.

### T6 Compare with the real reply

Hold out a closed ticket with an MLC reply. Run T3 on its customer-only text.
Compare the draft with the real reply by hand. Design the judge later.

### T7 Region and cost

Confirm the Knowledge Base ARN and the model ARN in `.env` are `eu-west-2`
and `eu.`. Read the bill after a quiet week and expect storage and retrieval
charges only.

## Requirements

`implemented` = built and shown to work. `partial` = part of the path is
proven. `validated` = not built, but the docs or a spike show it works. `out` =
not possible or out of scope. `open` = agreed as a goal or a spike, not started.
The Note column holds the evidence and the test that produced it.

| # | Requirement | Status | Note |
| --- | --- | --- | --- |
| R1 | Split the export into one document per ticket with metadata | implemented | `etl/split_tickets.py`. 6,950 tickets, 13,900 documents, 11 MB. |
| R2 | Ingest full-thread and customer-only variants side by side | implemented | `equals` filter on `variant` returned customer chunks only (T2, 2026-09-14). |
| R3 | Redact PII in the drafted reply | partial | The Guardrail unit check anonymised name, phone and email (T4, 2026-09-14). `demo/draft_reply.py` attaches it to Converse, but no run has surfaced PII yet. |
| R4 | Retrieve similar past tickets for a new ticket | implemented | `Retrieve` ranked the matching ticket first at score 0.75 (T1, 2026-09-14). |
| R5 | Draft a reply with citations to source ticket IDs | implemented | `demo/draft_reply.py` with Haiku drafted a reply that cited `[K2QNN]` and `[LR232]`, both in the five retrieved chunks (T3, 2026-09-22). |
| R6 | Classify the ticket: `howto`, `tenant-data`, `bug`, `unclear` | partial | The same Converse call labelled a how-to question `howto` (T3, 2026-09-22). The other three classes are untested (T5). |
| R7 | Signpost for `tenant-data` tickets: name the screen and the data to request | validated | Prompt only. |
| R8 | Human review of every draft | validated | Output is console text. Nothing is sent. |
| R9 | Data stays in UK or EU | validated | `eu-west-2` plus `eu.` inference profile. |
| R10 | Evaluate drafts against real MLC replies on held-out tickets | partial | Path chosen: Bedrock Evaluations, retrieve-and-generate RAG job, bring your own inference responses (see Findings). Not built. |
| R11 | Keep idle infra cost near zero | validated | Managed Knowledge Base bills storage and retrievals only. |
| R12 | Answer questions that need live tenant data from Lumis | out | No Lumis API in scope. The draft asks the customer for the data. |
| R13 | Write suggestions back into Lumis | out | Kick-off decision. |
| R14 | Handle customer-specific jargon | out | Revisit after evaluation. Tenant metadata filter is the first idea. |
| R15 | Daily re-sync of new tickets | out | Manual re-run of ETL and sync job in the PoC. |
| R16 | Ground-truth knowledge base or how-to wiki | out | Deferred at the deep dive. |
| R17 | Agentic retrieval: plan the search, query again with new filters or terms until the sources are useful | open | Spike on `AgenticRetrieveStream`. It is built into managed Knowledge Bases, takes metadata filters per retriever, and streams a cited answer, so it may replace `Retrieve` plus `Converse`. Its Guardrail supports `BLOCK` only, not `MASK`, so R3 needs a separate `ApplyGuardrail` call on the answer. Compare draft quality and cost against the one-shot path. |
| R18 | Batch processing to cut cost | open | Research. Bedrock batch inference is priced below on-demand. Fits a nightly run over new tickets, not the interactive front end. |
| R19 | Ground every draft in the retrieved tickets and minimise hallucination | open | Research. First candidate: the Guardrail contextual grounding check, which scores grounding and relevance against the source chunks. Second: the LLM judge from R10. |
| R20 | Detailed testing on the 20 ticket sample before the full corpus is loaded | open | Run T3 to T5 across every class and both variants on the sample first. The full load waits for that. |
