# Support agent PoC: architecture

Decided 2026-09-11. Sources: AI Assessment Report, deep-dive notes (11 Aug 2026),
kick-off notes (7 Sep 2026).

## Goal

Draft a reply and a triage label for each escalated Lumis support ticket.
A support agent reviews the draft. The tool never contacts a customer.
Quality and cost matter more than latency.

## Constraints from the meetings

- Human in the loop for every output. Cite the source tickets.
- Redact PII on input and output.
- UK or Ireland data residency.
- No write-back to the Lumis API in the PoC. Output is text in a console.
- New isolated AWS account, owned by Lambert Labs, handed to MLC at the end.
- Budget covers build and compute. Keep infra cost near zero when idle.

## Components

| Concern | Choice | Reason |
|---|---|---|
| Region | `eu-west-2` (London) | Data residency. AgentCore, Knowledge Bases, Guardrails and S3 Vectors are all available there (verified 2026-09-11). |
| Corpus store | S3 bucket, one Markdown file per ticket plus a `.metadata.json` sidecar | Knowledge Base S3 data source needs a sidecar for metadata filters. |
| Retrieval | Bedrock Knowledge Base, Titan Embeddings V2, S3 Vectors as the vector store | S3 Vectors has no idle cost and suits infrequent queries. About 50 tickets per day is infrequent. OpenSearch Serverless costs about $350 per month idle. |
| Redaction | Bedrock Guardrail with PII set to `ANONYMIZE`. Apply it once with `ApplyGuardrail` during ingestion, and again at inference through `guardrailConfig`. | Redaction at ingestion keeps PII out of the vector store and out of retrieval logs. Inference-time redaction covers the new ticket text. |
| Agent | Strands agent on AgentCore Runtime, Python, CodeZip build | AWS-native, least plumbing, `agentcore` CLI already installed (v0.26.0). |
| Model | Claude Sonnet through the `eu.` cross-region inference profile | Sonnet for draft quality. The `eu.` profile keeps inference inside the EU boundary. Downgrade to Haiku for the triage step if cost matters. |
| Invocation | `agentcore invoke` from the terminal with the ticket JSON as the prompt | Matches the "text in a console" decision. |

Not used: Bedrock Agents (legacy), AgentCore Memory, AgentCore Gateway, Lumis
API integration. Add Gateway only when write-back is in scope.

## Data flow

1. `etl.py` reads the Lumis JSON export.
2. For each ticket it merges `thread`, `adminThread` and `parentThread`, sorts by
   timestamp, drops `note: true` messages and system messages, and labels each
   message `Customer`, `MLC` or `Parent tenant`.
3. It calls `ApplyGuardrail` on the merged text and writes `tickets/<ticketId>.md`
   and `tickets/<ticketId>.md.metadata.json` to S3.
4. The Knowledge Base ingestion job embeds the files.
5. At inference the agent receives a new ticket, redacts it, retrieves the top
   matching tickets, and returns a triage label, a draft reply and the source
   ticket IDs.

Metadata per ticket: `tenant`, `ticketId`, `created`, `closed`, `priority`,
`supportCategory`, `reopened` (true when `Ticket closed` appears more than once
in `adminThread`), `hasMlcReply`.

## Ticket scope: feedback on the "how to" focus

Agree with the focus for the draft reply. Do not filter the corpus to reach it.

- Keep every escalated ticket in the Knowledge Base. A tenant-specific ticket
  still shows which admin screen or report resolved the problem. That is the
  signposting the assessment report asks for.
- Let the agent classify each incoming ticket: `howto`, `tenant-data`,
  `bug`, `unclear`. For `howto` it drafts a full reply. For `tenant-data` it
  drafts a reply that names the screen to check and the data to request from
  the customer. For `bug` it summarises and routes to development.
- Store `reopened` as metadata, not as an exclusion. Test retrieval with and
  without the filter before you exclude anything. Scott's "closed twice"
  heuristic is a signal, not a verdict.
- Skip the unused `howto` / `bug` type field.

## Evaluation

Hold out the newest 50 closed tickets with an MLC reply. Run the agent on the
customer text only. Compare the draft with the real MLC reply. Start with
manual review by MLC support. Add an LLM judge only if manual review is too slow.

## Cost estimate (idle plus 50 tickets per day)

- S3 and S3 Vectors: under $5 per month.
- Embeddings: one-off for about 6,500 tickets, under $2.
- Sonnet inference: about 8k input and 1k output tokens per ticket, roughly
  $2 per day.
- AgentCore Runtime: billed per second of active compute, negligible at this
  volume.

Verify against the Bedrock pricing page before the cost model goes to MLC.

## Known gaps

- Guardrail PII masking applies to the API response only. Bedrock model
  invocation logs, if enabled, hold the unmasked text. Keep invocation logging
  off, or encrypt the log group with KMS and restrict access.
- Customer jargon varies per tenant. Retrieval on raw text will miss some
  matches. Add a tenant metadata filter as a first retrieval pass if this shows
  in evaluation.
- The ticket export is a snapshot. Re-run `etl.py` and the ingestion job for
  new data. No scheduling in the PoC.
