# MLC support agent PoC

Proof of concept for My Learning Cloud (MLC). The tool reads an escalated
support ticket from the Lumis platform and drafts a reply for a human support
agent to review. Funded by AWS ($15,000, covers build and compute). Lambert
Labs owns the AWS account and hands it to MLC at the end.

Sources: AI Assessment Report (Google Doc `1fxX7kUTe…`), workshop notes
2026-07-20, deep dive 2026-08-11, kick-off 2026-09-07. Ticket export:
`super-admin.tickets.json` in the project Drive folder, 27 MB, one JSON array.

## Decisions

| Area | Decision | Why |
|---|---|---|
| Region | `eu-west-2` London | UK or Ireland data residency. Every service below is available there (verified 2026-09-11). |
| Retrieval | Bedrock **Managed** Knowledge Base, S3 connector | $5 per GB stored per month, $1 per 1,000 retrievals. Embedding model, reranker and hybrid search are included. Nothing to provision. The whole corpus is well under 1 GB. |
| Vector store | None to choose. The managed Knowledge Base owns it. | Removes the OpenSearch Serverless idle cost ($400 to $600 per month) and the S3 Vectors setup. |
| Chunking experiment | Ingest each ticket twice: full thread and customer side only. Tag each file with `variant` metadata. Filter on `variant` at retrieval. | Compares both strategies against one index. Fall back to two Knowledge Bases if the filter is awkward. |
| Query API | `RetrieveAndGenerate` with a Guardrail attached | Least code. Returns the draft and citations in one call. |
| Generation model | Claude Sonnet, `eu.` inference profile | Draft quality. The `eu.` profile keeps inference inside the EU. Try Haiku if cost matters. |
| PII | Bedrock Guardrail, PII set to `ANONYMIZE`. Apply with `ApplyGuardrail` during ETL and again at query time. | Redaction at ingestion keeps PII out of the index. Query-time redaction covers the new ticket. |
| Runtime | Plain Bedrock API calls from a Python script. No AgentCore, no Strands, no Bedrock Agents. | The tool is a fixed pipeline with no tool loop, no session and no external caller. AgentCore adds hosting and identity that nothing needs yet. |
| Output | Text in the console | Kick-off decision. No write-back to Lumis. |
| Corpus scope | Escalated tickets only, including tickets assigned to developers | Kick-off decision. |
| Bad tickets | Keep all. Store `reopened` as metadata. Test with and without a filter. | Scott's "closed twice" heuristic is a signal, not a verdict. |

Add AgentCore only when one of these becomes true: Lumis calls the tool over
HTTP, the agent needs the Lumis API through a Gateway with permissions separate
from a user token, or you want AgentCore Evaluations.

## Findings

- The managed Knowledge Base offers built-in or fixed-size chunking only. There
  is no `NONE` option, so one vector per ticket is not guaranteed. Use a large
  fixed size and check the chunk count after ingestion.
- Managed Knowledge Base metadata filters support `equals`, `in`, `notIn` and
  range operators. `startsWith` and `stringContains` are not supported.
- The S3 connector treats one file as one document. The 27 MB export must be
  split into one file per ticket with a `<file>.metadata.json` sidecar.
- Guardrail PII masking applies to the API response only. Model invocation
  logs, if enabled, hold unmasked text. Keep invocation logging off or encrypt
  the log group.
- Re-ingesting a file that already exists in a Knowledge Base fails. Delete
  the document first. Boomcoms PoC hit this.
- Tickets combine `thread` (customer), `adminThread` (MLC, `note: true` means
  internal), `parentThread` (parent tenant) and sometimes `systemThread`. Sort
  by `timestamp`. Drop notes and system messages. The `howto` / `bug` type
  field was never used.
- The Drive file needs a browser sign-in to download. The password is in the
  Teams chat. Store it at `data/super-admin.tickets.json`. Never commit it.

## Requirements

Status: `implemented` = built and shown to work. `validated` = not built, but
the docs or a spike show it works. `out` = not possible or out of scope.

| # | Requirement | Status | Note |
|---|---|---|---|
| R1 | Split the export into one document per ticket with metadata | validated | S3 connector needs it. ETL is application code. |
| R2 | Ingest full-thread and customer-only variants side by side | validated | Metadata filter on `variant`. Confirm the filter works on managed Knowledge Base at retrieval. |
| R3 | Redact PII before ingestion and at query time | validated | `ApplyGuardrail` and `guardrailConfiguration` on `RetrieveAndGenerate`. |
| R4 | Retrieve similar past tickets for a new ticket | validated | Managed Knowledge Base, hybrid search included. |
| R5 | Draft a reply with citations to source ticket IDs | validated | `RetrieveAndGenerate` returns citations. Ticket ID comes from metadata. |
| R6 | Classify the ticket: `howto`, `tenant-data`, `bug`, `unclear` | validated | Needs a custom prompt on `RetrieveAndGenerate` or a second Converse call. |
| R7 | Signpost for `tenant-data` tickets: name the screen and the data to request | validated | Prompt only. |
| R8 | Human review of every draft | validated | Output is console text. Nothing is sent. |
| R9 | Data stays in UK or EU | validated | `eu-west-2` plus `eu.` inference profile. |
| R10 | Evaluate drafts against real MLC replies on held-out tickets | validated | Manual review first. LLM judge later. |
| R11 | Keep idle infra cost near zero | validated | Managed Knowledge Base bills storage and retrievals only. |
| R12 | Answer questions that need live tenant data from Lumis | out | No Lumis API in scope. Draft asks the customer for the data instead. |
| R13 | Write suggestions back into Lumis | out | Kick-off decision. |
| R14 | Handle customer-specific jargon | out | Revisit after evaluation. Tenant metadata filter is the first idea. |
| R15 | Daily re-sync of new tickets | out | Manual re-run of ETL and sync job in the PoC. |
| R16 | Ground-truth knowledge base or how-to wiki | out | Deferred at deep dive. Agent may suggest themes later. |

## Layout

Target layout, modelled on the Boomcoms Bedrock PoC (`~/work/boom-coms/poc`).

- `CLAUDE.md`: this file. Decisions, findings, requirements.
- `data/`: local ticket export. Git ignores it.
- `etl/`: split, redact and upload the export.
- `demo/`: one script per experiment, for example `query_full_thread.py`.
- `requirements.txt`: `boto3` only.

## AWS

- New isolated PoC account, `eu-west-2`. Not provisioned yet.
- Use only the `-ro` Identity Center profile for reads. Ask before any change.
