# Cost model (R22)

An interactive spreadsheet for the customer. They change the parameters on
one sheet. Every total updates, for on-demand and batch, side by side.

Sheet: [MLC Support PoC - Cost model (v2, Price List API)](https://docs.google.com/spreadsheets/d/1coA0X3obxz3E-woCLGM6YsqSg4NHssy53Y5wC_UasHs/edit)

> **Note** The Drive `create_file` tool has no in-place update for content, only
> for title and parent folder, so each regenerate publishes a new file. The
> [first version](https://docs.google.com/spreadsheets/d/1i_Z4ruttKKa0HeBZGHM6ns01GpLnOxYcPn-4FiL9E0M/edit)
> (web-page prices) is superseded by the one above (Price List API prices).

## Regenerate the sheet

```shell
uv run tools/cost_model.py
```

This writes `out/cost-model.xlsx`. The script fetches every verifiable price
live from the read-only AWS Price List API (region `us-east-1`, using the
`AWS_PROFILE` in the environment); a rerun refreshes them. Anything the API
does not carry falls back to a hand-entered value, flagged on the Prices
sheet. If boto3 or AWS credentials are unavailable, every price falls back
and the script still runs. Upload the result to the project Drive folder by
hand, or re-run the upload through the Drive tool if you have MCP access.

## Sheets

| Sheet | Holds |
| --- | --- |
| Inputs | The orange, editable cells: queries per day, tokens per draft, Knowledge Base and Guardrail usage, fixed items. |
| Prices | Every unit price, with its source, the date checked, and a verified/unverified flag. |
| Estimate | One row per cost line, a formula for on-demand and a formula for batch, and a total. |
| Spend to date | The account's real AWS Cost Explorer spend, for comparison against the estimate. |

The Estimate sheet holds live formulas, not numbers. Editing an Inputs cell
recalculates every total.

## Defaults

- 200 support queries a day, 22 working days a month (4,400 queries/month).
- 3,000 average input tokens per draft, 500 average output tokens.
- 1 GB Knowledge Base storage, 1 retrieval per query.
- 2 Guardrail text units per query (input + output).
- 1 GB S3 storage, 1 GB/month CloudWatch Logs.
- Batch price is 50% of on-demand (Amazon Bedrock batch inference discount).

## Default monthly total

At the default inputs (4,400 queries/month, 3,000 input / 500 output tokens),
with the fixed items ($13.82/month: Knowledge Base, Guardrails, S3,
CloudWatch):

| Model | On-demand | Batch |
| --- | --- | --- |
| Claude Sonnet 5 (NOT VERIFIED, see below) | $86.42 | $50.12 |
| Claude Haiku 4.5 (verified) | $38.02 | $25.92 |

## Spend to date

Amazon Cost Explorer, profile `mlc-support-poc`, region `eu-west-2`, grouped
by `SERVICE`, 2026-09-01 to 2026-09-22 (read-only query, no AWS state
changed):

| Service | Cost ($) |
| --- | --- |
| Amazon Simple Storage Service | 0.1586 |
| Amazon Bedrock Managed Knowledge Base | 0.0070 |
| AmazonCloudWatch | 0.0009 |
| Amazon Bedrock | 0.0002 |
| AWS Secrets Manager | 0.00003 |
| AWS Key Management Service | 0.00002 |
| Amazon Simple Queue Service | 0.000002 |
| **Total** | **0.1668** |

The PoC has run for three weeks at trivial cost. The Bedrock charge of
$0.0002 is entirely the Guardrail sensitive information filter
(`EUW2-Guardrail-SensitiveInformationPolicyPaidUnitsConsumed`); no model
inference has been billed yet, since the demo runs are still small.

## Price sources

Prices come from the read-only [AWS Price List API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/using-price-list-query-api.html)
(`aws pricing get-products`, region `us-east-1`), not the pricing web page.
Ten of fourteen prices are fetched live and confirmed against real SKUs in
`eu-west-2`, cross-checked against this account's own Cost Explorer usage
where an equivalent usage type exists:

| Item | Price | API source |
| --- | --- | --- |
| Claude Haiku 4.5, on-demand input | $1.00 / 1M tokens | `AmazonBedrockMarketplace`, `EUW2-MP:EUW2_InputTokenCount_Global-Units` |
| Claude Haiku 4.5, on-demand output | $5.00 / 1M tokens | `AmazonBedrockMarketplace`, `EUW2-MP:EUW2_OutputTokenCount_Global-Units` |
| Claude Haiku 4.5, batch input | $0.50 / 1M tokens | `AmazonBedrockMarketplace`, `EUW2-MP:EUW2_InputTokenCount_Global_Batch-Units` |
| Claude Haiku 4.5, batch output | $2.50 / 1M tokens | `AmazonBedrockMarketplace`, `EUW2-MP:EUW2_OutputTokenCount_Global_Batch-Units` |
| Knowledge Base storage | $5.00 / GB / month | `AmazonKnowledgeBase`, `EUW2-Knowledge-Base:Consumption-based:Storage` |
| Knowledge Base retrieval | $1.00 / 1,000 retrievals | `AmazonKnowledgeBase`, `EUW2-Knowledge-Base:Consumption-based:Retrieval` |
| Guardrail sensitive information filter | $0.10 / 1,000 text units | `AmazonBedrock`, `EUW2-Guardrail-SensitiveInformationPolicyPaidUnitsConsumed`; matches this account's Cost Explorer usage exactly |
| Guardrail contextual grounding | $0.10 / 1,000 text units | `AmazonBedrock`, `EUW2-Guardrail-ContextualGroundingPolicyUnitsConsumed` |
| S3 Standard storage | $0.024 / GB / month | `AmazonS3`, first-tier `TimedStorage-ByteHrs`, `eu-west-2` |
| CloudWatch Logs ingestion | $0.5985 / GB | `AmazonCloudWatch`, `EUW2-DataProcessing-Bytes` |

The `EUW2_..._Global-Units` usage types are the `eu.` cross-region inference
profile this repo uses (README ARN `eu.anthropic.claude-haiku-4-5-...`); the
API also has a non-Global, single-region rate that costs more ($1.10 /
$5.50 per 1M tokens on-demand), not used here.

**Claude Sonnet 5 could not be verified**, on-demand or batch, at any price.
`aws pricing get-attribute-values --service-code AmazonBedrockMarketplace
--attribute-name model` lists every Anthropic model AWS Marketplace prices
in this account, including Claude Haiku 4.5, Claude Sonnet 4/4.5/4.6, and
even this agent's own "Claude Fable 5" -- but no "Claude Sonnet 5". It is
genuinely absent from the Price List API's Marketplace catalog, consistent
with this repo's README note that a new account's first Sonnet 5 call fails
until AWS activates the Marketplace subscription. The sheet keeps the
$3.00 / $15.00 per 1M token fallback from README's R18 finding, with batch
assumed at 50%, both flagged NOT VERIFIED. Recheck the console once Sonnet 5
is confirmed active on this account.

## Template

Searched Google Drive for a Teddington Systems cost model
(`title contains 'Teddington'`) and did not find one. The Teddington folder
holds meeting notes and a zip archive, no spreadsheet. The closest match
(`fullText contains 'cost model'`) was the Lambert Labs <> MediaZoo cost
model, whose layout this sheet follows: an inputs block, a per-line
calculation block, totals, and a price-sources block with URLs.
