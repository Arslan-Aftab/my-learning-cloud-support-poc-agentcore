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
new ticket ──► demo/draft_reply.py ──► RetrieveAndGenerate + Guardrail ──► console
```

| Area | Decision | Why |
| --- | --- | --- |
| Region | `eu-west-2` London | UK or Ireland data residency. Every service below is available there (verified 2026-09-11). |
| Retrieval | Bedrock **Managed** Knowledge Base, S3 connector | $5 per GB stored per month, $1 per 1,000 retrievals. Embedding model, reranker and hybrid search are included. Nothing to provision. The corpus is well under 1 GB. |
| Chunking experiment | Ingest each ticket twice: full thread and customer side only. Tag each file with `variant` metadata. Filter on `variant` at retrieval. | Compares both strategies against one index. Fall back to two Knowledge Bases if the filter is awkward. |
| Query API | `RetrieveAndGenerate` with a Guardrail attached | Least code. Returns the draft and citations in one call. |
| Generation model | Claude Sonnet, `eu.` inference profile | Draft quality. The `eu.` profile keeps inference inside the EU. Try Haiku if cost matters. |
| PII | Bedrock Guardrail, PII set to `ANONYMIZE`. Apply with `ApplyGuardrail` during ETL and again at query time. | Redaction at ingestion keeps PII out of the index. Query-time redaction covers the new ticket. |
| Runtime | Plain Bedrock API calls from Python. No AgentCore, no Strands, no Bedrock Agents. | The tool is a fixed pipeline with no tool loop, no session and no external caller. |
| Infrastructure | One CloudFormation template, `infrastructure/template.yaml` | Five resources. `AWS::Bedrock::KnowledgeBase` supports `ManagedKnowledgeBaseConfiguration`. |
| Output | Text in the console. No write-back to Lumis. | Kick-off decision. |
| Corpus scope | Escalated tickets only, including tickets assigned to developers | Kick-off decision. |
| Bad tickets | Keep all. Store `reopened` as metadata. Test with and without a filter. | Scott's "closed twice" heuristic is a signal, not a verdict. |

Add AgentCore only when Lumis calls the tool over HTTP, when the agent needs the
Lumis API through a Gateway with permissions separate from a user token, or when
you want AgentCore Evaluations.

## Findings

- The managed Knowledge Base offers built-in or fixed-size chunking only. One
  vector per ticket is not guaranteed. Use a large fixed size and check the chunk
  count after ingestion.
- Managed Knowledge Base metadata filters support `equals`, `in`, `notIn` and
  range operators. `startsWith` and `stringContains` are not supported.
- The S3 connector treats one file as one document. The 27 MB export must be
  split into one file per ticket with a `<file>.metadata.json` sidecar.
- Guardrail PII masking applies to the API response only. Model invocation logs,
  if enabled, hold unmasked text. Keep invocation logging off or encrypt the log
  group.
- Re-ingesting a file that already exists in a Knowledge Base fails. Delete the
  document first. The Boomcoms PoC hit this.
- Tickets combine `thread` (customer), `adminThread` (MLC, `note: true` means
  internal), `parentThread` (parent tenant) and sometimes `systemThread`. Sort by
  `timestamp`. Drop notes and system messages. The `howto` / `bug` type field was
  never used.

## Requirements

`implemented` = built and shown to work. `validated` = not built, but the docs or
a spike show it works. `out` = not possible or out of scope.

| # | Requirement | Status | Note |
| --- | --- | --- | --- |
| R1 | Split the export into one document per ticket with metadata | implemented | `etl/split_tickets.py`. 6,950 tickets, 13,900 documents, 11 MB. |
| R2 | Ingest full-thread and customer-only variants side by side | validated | Metadata filter on `variant`. Confirm at retrieval. |
| R3 | Redact PII before ingestion and at query time | validated | `ApplyGuardrail` and `guardrailConfiguration` on `RetrieveAndGenerate`. |
| R4 | Retrieve similar past tickets for a new ticket | validated | Managed Knowledge Base, hybrid search included. |
| R5 | Draft a reply with citations to source ticket IDs | validated | `RetrieveAndGenerate` returns citations. Ticket ID comes from metadata. |
| R6 | Classify the ticket: `howto`, `tenant-data`, `bug`, `unclear` | validated | Custom prompt on `RetrieveAndGenerate` or a second Converse call. |
| R7 | Signpost for `tenant-data` tickets: name the screen and the data to request | validated | Prompt only. |
| R8 | Human review of every draft | validated | Output is console text. Nothing is sent. |
| R9 | Data stays in UK or EU | validated | `eu-west-2` plus `eu.` inference profile. |
| R10 | Evaluate drafts against real MLC replies on held-out tickets | validated | Manual review first. LLM judge later. |
| R11 | Keep idle infra cost near zero | validated | Managed Knowledge Base bills storage and retrievals only. |
| R12 | Answer questions that need live tenant data from Lumis | out | No Lumis API in scope. The draft asks the customer for the data. |
| R13 | Write suggestions back into Lumis | out | Kick-off decision. |
| R14 | Handle customer-specific jargon | out | Revisit after evaluation. Tenant metadata filter is the first idea. |
| R15 | Daily re-sync of new tickets | out | Manual re-run of ETL and sync job in the PoC. |
| R16 | Ground-truth knowledge base or how-to wiki | out | Deferred at the deep dive. |

## Repo layout

| Path | What |
| --- | --- |
| `etl/split_tickets.py` | Splits the export into per-ticket documents and metadata sidecars |
| `tests/` | Self-check for the ETL, with one fixture ticket |
| `infrastructure/template.yaml` | CloudFormation: bucket, Knowledge Base role, Knowledge Base, data source, Guardrail. |
| `demo/` | One script per experiment. Not written yet. |
| `data/` | Local ticket export. Git ignores it. |
| `out/` | ETL output. Git ignores it. |

## Prerequisites

Once per machine.

- Python 3.12 or later. The ETL uses the standard library only.
- [uv](https://docs.astral.sh/uv/) for tools: `uv tool install cfn-lint`.
- AWS CLI v2.
- Access to the PoC account `938733851942` in the Lambert Labs organisation
  through the `ll-aws-main` SSO session. Add the profile to `~/.aws/config`.
  No `-ro` profile exists yet.

  ```ini
  [profile mlc-support-poc]
  sso_session = ll-aws-main
  sso_account_id = 938733851942
  sso_role_name = AdministratorAccess
  region = eu-west-2
  ```

- The ticket export. Download `super-admin.tickets.json` from the project
  Drive folder to `data/`. The password is in the Teams chat. Never commit it.

Every command below assumes `export AWS_PROFILE=mlc-support-poc` and a
current `aws sso login`.

## Deploying

The template creates the ticket bucket, the Knowledge Base role, the managed
Knowledge Base, the S3 data source and the PII Guardrail. Nothing else is
needed.

```shell
cfn-lint --regions eu-west-2 -t infrastructure/template.yaml
aws cloudformation deploy --stack-name mlc-support-poc \
  --template-file infrastructure/template.yaml \
  --capabilities CAPABILITY_NAMED_IAM
aws cloudformation describe-stacks --stack-name mlc-support-poc \
  --query 'Stacks[0].Outputs' --output table
```

The outputs `BucketName`, `KnowledgeBaseId`, `DataSourceId`, `GuardrailId`
and `GuardrailVersion` are used below.

## Loading tickets

Repeat when the export changes.

```shell
python3 etl/split_tickets.py data/super-admin.tickets.json out/
aws s3 sync out/ s3://<BucketName>/tickets/ --delete
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id <KnowledgeBaseId> --data-source-id <DataSourceId>
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id <KnowledgeBaseId> --data-source-id <DataSourceId> \
  --query 'ingestionJobSummaries[0].[status,statistics]'
```

Wait until the status is `COMPLETE`. `--delete` removes files that are no
longer in `out/`, which avoids the re-ingest failure noted in Findings.

## Testing

Each test maps to a requirement. Record the result in the requirements table.

**T1 Retrieve and generate (R4, R5).** Find the `eu.` Sonnet inference
profile, then ask a how-to question. Expect a reply plus citations whose
`metadata.ticketId` values are real ticket IDs.

```shell
aws bedrock list-inference-profiles \
  --query "inferenceProfileSummaries[?starts_with(inferenceProfileId,'eu.anthropic.claude-sonnet')].inferenceProfileArn"
aws bedrock-agent-runtime retrieve-and-generate \
  --input '{"text":"How do I view completion of a policy that is not mandatory?"}' \
  --retrieve-and-generate-configuration '{"type":"KNOWLEDGE_BASE","knowledgeBaseConfiguration":{"knowledgeBaseId":"<KnowledgeBaseId>","modelArn":"<ModelArn>"}}'
```

**T2 Variant filter (R2).** Repeat T1 with a filter and confirm every
citation has the same `variant`.

```shell
--retrieve-and-generate-configuration '{"type":"KNOWLEDGE_BASE","knowledgeBaseConfiguration":{"knowledgeBaseId":"<KnowledgeBaseId>","modelArn":"<ModelArn>","retrievalConfiguration":{"vectorSearchConfiguration":{"filter":{"equals":{"key":"variant","value":"customer"}}}}}}'
```

**T3 PII redaction (R3).** Expect `action` = `GUARDRAIL_INTERVENED` and the
name, phone and email replaced with `{NAME}`, `{PHONE}` and `{EMAIL}`.

```shell
aws bedrock-runtime apply-guardrail \
  --guardrail-identifier <GuardrailId> --guardrail-version <GuardrailVersion> \
  --source INPUT \
  --content '[{"text":{"text":"Please call Jane Smith on 07700 900123 or email jane@example.com"}}]'
```

**T4 PII redaction at query time (R3).** Repeat T1 with
`"guardrailConfiguration":{"guardrailId":"<GuardrailId>","guardrailVersion":"<GuardrailVersion>"}`
inside `knowledgeBaseConfiguration` and a question that names a person.
Expect no personal name in the reply.
