# Cost model (R22)

An interactive spreadsheet for the customer. They change the parameters on
one sheet. Every total updates, for on-demand and batch, side by side.

Sheet: [MLC Support PoC - Cost model](https://docs.google.com/spreadsheets/d/1i_Z4ruttKKa0HeBZGHM6ns01GpLnOxYcPn-4FiL9E0M/edit)

## Regenerate the sheet

```shell
uv run tools/cost_model.py
```

This writes `out/cost-model.xlsx`. Upload it to the project Drive folder by
hand, or re-run the upload through the Drive tool if you have MCP access.

## Sheets

| Sheet | Holds |
| --- | --- |
| Inputs | The orange, editable cells: queries per day, tokens per draft, Knowledge Base and Guardrail usage, fixed items. |
| Prices | Every unit price, with its source URL, the date checked, and a verified/unverified flag. |
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

Every price on the Prices sheet carries its own URL. Two prices could not be
verified this session and are flagged in the sheet:

- **Claude Sonnet 5 and Claude Haiku 4.5, on-demand and batch, eu-west-2.**
  The [Amazon Bedrock pricing page](https://aws.amazon.com/bedrock/pricing/)
  renders its model tables through a JavaScript tab widget. The page fetch
  this session returned the "Models with extended access" table (legacy
  Claude 3.5 Sonnet) but not the current Sonnet 5 / Haiku 4.5 rows, and no
  region split. The Sonnet figures on the sheet ($3.00 input / $15.00 output
  per 1M tokens) are the published cross-region on-demand rate, carried over
  from this repo's own README findings (R18). Confirm both models' eu-west-2
  rate in the Bedrock console before quoting a customer. The Haiku cells are
  left at $0 and flagged, since no figure could be sourced at all.
- **Guardrail contextual grounding**, per 1,000 text units: no published
  figure found. Flagged $0 on the sheet.
- **Knowledge Base storage and retrieval price**: carried over from this
  repo's README Decisions table ($5/GB/month, $1/1,000 retrievals), not
  independently re-confirmed against the pricing page this session.
- **S3 Standard storage and CloudWatch Logs ingestion**: US East rates
  ($0.023/GB/month and $0.50/GB) used as a stand-in; eu-west-2 is usually
  close but not identical. Check `aws.amazon.com/s3/pricing` and
  `aws.amazon.com/cloudwatch/pricing`.

The **Guardrail sensitive information filter** price ($0.10 per 1,000 text
units) is verified: it matches this account's own Cost Explorer usage
(`EUW2-Guardrail-SensitiveInformationPolicyPaidUnitsConsumed`, $0.0002 for 2
units).

## Template

Searched Google Drive for a Teddington Systems cost model
(`title contains 'Teddington'`) and did not find one. The Teddington folder
holds meeting notes and a zip archive, no spreadsheet. The closest match
(`fullText contains 'cost model'`) was the Lambert Labs <> MediaZoo cost
model, whose layout this sheet follows: an inputs block, a per-line
calculation block, totals, and a price-sources block with URLs.
