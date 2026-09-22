# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1", "boto3>=1.34"]
# ///
"""Write out/cost-model.xlsx: an editable R22 cost estimate for the customer.

Run: uv run tools/cost_model.py
Prices are fetched live from the AWS Price List API (read-only, region
us-east-1) using the AWS_PROFILE in the environment. Anything the API does
not carry falls back to a hand-entered value, flagged on the Prices sheet.
The workbook holds real formulas. Edit the orange cells on Inputs; every
total on Estimate recalculates. See docs/cost-model.md.
"""

import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ORANGE = PatternFill("solid", fgColor="FCE4D6")
GRAY = PatternFill("solid", fgColor="F2F2F2")
HEADER = Font(bold=True)
BOLD = Font(bold=True)
TODAY = "2026-09-22"


def set_col_widths(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _price_dimensions(client, service_code, filters):
    """Every OnDemand price dimension for products matching the filters."""
    resp = client.get_products(
        ServiceCode=service_code,
        Filters=[{"Type": "TERM_MATCH", "Field": k, "Value": v} for k, v in filters.items()],
        MaxResults=100,
    )
    dims = []
    for raw in resp.get("PriceList", []):
        product = json.loads(raw)
        for term in product.get("terms", {}).get("OnDemand", {}).values():
            for dim in term["priceDimensions"].values():
                dims.append(
                    {
                        "price": float(dim["pricePerUnit"]["USD"]),
                        "unit": dim["unit"],
                        "beginRange": dim.get("beginRange"),
                        "sku": product["product"]["sku"],
                        "usagetype": product["product"]["attributes"].get("usagetype"),
                    }
                )
    return dims


def fetch_prices():
    """Look up every verifiable price via the AWS Price List API.

    Returns {key: (price, source_note)}. A key missing from the result
    means the API had nothing for it (fetch failed, or genuinely absent,
    such as Claude Sonnet 5 -- not yet in the Marketplace pricing catalog
    at the time of writing) and the caller's fallback applies.
    """
    out = {}
    try:
        import boto3

        client = boto3.client("pricing", region_name="us-east-1")
    except Exception as exc:  # no boto3, no creds, no network -- fall back for everything
        print(f"fetch_prices: skipping live lookup ({exc})")
        return out

    def haiku(usagetype):
        dims = _price_dimensions(
            client,
            "AmazonBedrockMarketplace",
            {"model": "Claude Haiku 4.5", "regionCode": "eu-west-2", "usagetype": usagetype},
        )
        if dims:
            d = dims[0]  # unit is already "1M tokens"
            out[usagetype] = (
                d["price"],
                f"AWS Price List API, AmazonBedrockMarketplace, {d['sku']}, {TODAY}",
            )

    def bedrock_units(key, usagetype):
        dims = _price_dimensions(client, "AmazonBedrock", {"usagetype": usagetype})
        if dims:
            d = dims[0]
            out[key] = (
                d["price"] * 1000,  # $/unit -> $/1,000 units
                f"AWS Price List API, AmazonBedrock, {d['usagetype']}, {TODAY}",
            )

    try:
        haiku("EUW2-MP:EUW2_InputTokenCount_Global-Units")
        haiku("EUW2-MP:EUW2_OutputTokenCount_Global-Units")
        haiku("EUW2-MP:EUW2_InputTokenCount_Global_Batch-Units")
        haiku("EUW2-MP:EUW2_OutputTokenCount_Global_Batch-Units")

        bedrock_units("guardrail_sensitive", "EUW2-Guardrail-SensitiveInformationPolicyPaidUnitsConsumed")
        bedrock_units("guardrail_grounding", "EUW2-Guardrail-ContextualGroundingPolicyUnitsConsumed")

        kb_storage = _price_dimensions(
            client, "AmazonKnowledgeBase", {"usagetype": "EUW2-Knowledge-Base:Consumption-based:Storage"}
        )
        if kb_storage:
            d = kb_storage[0]
            out["kb_storage"] = (d["price"], f"AWS Price List API, AmazonKnowledgeBase, {d['usagetype']}, {TODAY}")

        kb_retrieval = _price_dimensions(
            client, "AmazonKnowledgeBase", {"usagetype": "EUW2-Knowledge-Base:Consumption-based:Retrieval"}
        )
        if kb_retrieval:
            d = kb_retrieval[0]
            out["kb_retrieval"] = (
                d["price"] * 1000,  # $/query -> $/1,000 queries
                f"AWS Price List API, AmazonKnowledgeBase, {d['usagetype']}, {TODAY}",
            )

        s3 = _price_dimensions(
            client,
            "AmazonS3",
            {"storageClass": "General Purpose", "volumeType": "Standard", "regionCode": "eu-west-2"},
        )
        first_tier = [d for d in s3 if d.get("beginRange") == "0"]
        if first_tier:
            d = first_tier[0]
            out["s3_storage"] = (d["price"], f"AWS Price List API, AmazonS3, {d['sku']}, {TODAY}")

        cw = _price_dimensions(client, "AmazonCloudWatch", {"usagetype": "EUW2-DataProcessing-Bytes"})
        if cw:
            d = cw[0]
            out["cw_logs"] = (d["price"], f"AWS Price List API, AmazonCloudWatch, {d['usagetype']}, {TODAY}")
    except Exception as exc:  # throttled, no permission, network blip -- keep what we have
        print(f"fetch_prices: stopped early ({exc}), remaining items fall back")

    return out


def build():
    wb = Workbook()

    # ---- Inputs ----
    ws = wb.active
    ws.title = "Inputs"
    ws.append(["Adjust the orange cells. Do not edit the gray cells.", "", ""])
    ws["A1"].font = HEADER
    ws.append([])
    ws.append(["Parameter", "Value", "Notes"])
    for c in "ABC":
        ws[f"{c}3"].font = HEADER

    rows = [
        ("Support queries per day", 200, "Default from the requirement."),
        ("Working days per month", 22, ""),
        ("Average input tokens per draft", 3000, "Retrieved chunks + prompt + question."),
        ("Average output tokens per draft", 500, ""),
        ("Knowledge Base storage (GB)", 1, "Ticket corpus, both variants."),
        ("Knowledge Base retrievals per query", 1, "One Retrieve call per draft."),
        ("Guardrail text units per query", 2, "1,000 characters each, input + output."),
        ("S3 storage (GB)", 1, "Ticket export documents."),
        ("CloudWatch Logs ingested (GB/month)", 1, "Ingestion job log group."),
    ]
    start = 4
    for i, (label, value, note) in enumerate(rows):
        r = start + i
        ws.cell(r, 1, label)
        cell = ws.cell(r, 2, value)
        cell.fill = ORANGE
        ws.cell(r, 3, note)
    ws["B13"] = "=B4*B5"
    ws["A13"] = "Queries per month (calculated)"
    ws["A13"].font = BOLD
    ws["B13"].fill = GRAY
    set_col_widths(ws, [34, 12, 46])
    ws.freeze_panes = "A4"

    # ---- Prices ----
    # Sonnet 5 is not in the AWS Price List API's Marketplace pricing catalog
    # at the time of writing (checked eu-west-2 and the eu. cross-region
    # profile; Haiku 4.5 is there, Sonnet 5 is not), so it keeps a
    # hand-entered fallback. Everything else is fetched live; api[key] is
    # missing only if the fetch failed, which also falls back.
    api = fetch_prices()

    def resolved(item, unit, key, fallback_value, fallback_note):
        if key in api:
            value, source = api[key]
            return (item, round(value, 4), unit, source, "VERIFIED, API", "")
        return (
            item, fallback_value, unit,
            "https://aws.amazon.com/bedrock/pricing/", "NOT VERIFIED",
            fallback_note + " (AWS Price List API had no data for this item this run.)",
        )

    wsp = wb.create_sheet("Prices")
    wsp.append(["Item", "Price", "Unit", "Source", "Verified", "Notes"])
    for c in range(1, 7):
        wsp.cell(1, c).font = HEADER
    price_rows = [
        resolved("Claude Sonnet 5, on-demand input", "$ / 1M tokens", "sonnet5_in", 3.00,
                  "Not in the Marketplace pricing catalog this session; carried over from "
                  "this repo's README (R18 finding). Confirm in the console before quoting."),
        resolved("Claude Sonnet 5, on-demand output", "$ / 1M tokens", "sonnet5_out", 15.00,
                  "Same caveat as input."),
        resolved("Claude Sonnet 5, batch input", "$ / 1M tokens", "sonnet5_batch_in", 1.50,
                  "No batch SKU found either; assumed 50% of on-demand (published batch discount)."),
        resolved("Claude Sonnet 5, batch output", "$ / 1M tokens", "sonnet5_batch_out", 7.50,
                  "Same caveat as batch input."),
        resolved("Claude Haiku 4.5, on-demand input", "$ / 1M tokens",
                  "EUW2-MP:EUW2_InputTokenCount_Global-Units", 0, "Not fetched."),
        resolved("Claude Haiku 4.5, on-demand output", "$ / 1M tokens",
                  "EUW2-MP:EUW2_OutputTokenCount_Global-Units", 0, "Not fetched."),
        resolved("Claude Haiku 4.5, batch input", "$ / 1M tokens",
                  "EUW2-MP:EUW2_InputTokenCount_Global_Batch-Units", 0, "Not fetched."),
        resolved("Claude Haiku 4.5, batch output", "$ / 1M tokens",
                  "EUW2-MP:EUW2_OutputTokenCount_Global_Batch-Units", 0, "Not fetched."),
        resolved("Knowledge Base storage", "$ / GB / month", "kb_storage", 5.00, "Not fetched."),
        resolved("Knowledge Base retrieval", "$ / 1,000 retrievals", "kb_retrieval", 1.00, "Not fetched."),
        resolved("Guardrail sensitive information filter", "$ / 1,000 text units",
                  "guardrail_sensitive", 0.10, "Not fetched."),
        resolved("Guardrail contextual grounding", "$ / 1,000 text units",
                  "guardrail_grounding", 0.10, "Not fetched."),
        resolved("S3 Standard storage", "$ / GB / month", "s3_storage", 0.024, "Not fetched."),
        resolved("CloudWatch Logs ingestion", "$ / GB", "cw_logs", 0.5985, "Not fetched."),
    ]
    for row in price_rows:
        wsp.append(row)
    set_col_widths(wsp, [40, 10, 20, 55, 16, 60])
    for r in range(2, 2 + len(price_rows)):
        wsp.cell(r, 6).alignment = Alignment(wrap_text=True, vertical="top")

    # ---- Estimate ----
    we = wb.create_sheet("Estimate")
    we.append(["Line", "On-demand $/month", "Batch $/month", "Notes"])
    for c in range(1, 5):
        we.cell(1, c).font = HEADER

    def price(row):
        return f"Prices!$B${row}"

    # Prices sheet row numbers (row 1 is the header):
    # 2 Sonnet5 in, 3 Sonnet5 out, 4 Sonnet5 batch in, 5 Sonnet5 batch out,
    # 6 Haiku in, 7 Haiku out, 8 Haiku batch in, 9 Haiku batch out,
    # 10 KB storage, 11 KB retrieval, 12 Guardrail sensitive,
    # 13 Guardrail grounding, 14 S3, 15 CloudWatch
    lines = [
        ("Sonnet 5 input tokens",
         f"=Inputs!$B$13*Inputs!$B$6/1000000*{price(2)}",
         f"=Inputs!$B$13*Inputs!$B$6/1000000*{price(4)}",
         "queries/month x input tokens / 1M x price"),
        ("Sonnet 5 output tokens",
         f"=Inputs!$B$13*Inputs!$B$7/1000000*{price(3)}",
         f"=Inputs!$B$13*Inputs!$B$7/1000000*{price(5)}",
         "queries/month x output tokens / 1M x price"),
        ("Haiku 4.5 input tokens",
         f"=Inputs!$B$13*Inputs!$B$6/1000000*{price(6)}",
         f"=Inputs!$B$13*Inputs!$B$6/1000000*{price(8)}",
         ""),
        ("Haiku 4.5 output tokens",
         f"=Inputs!$B$13*Inputs!$B$7/1000000*{price(7)}",
         f"=Inputs!$B$13*Inputs!$B$7/1000000*{price(9)}",
         ""),
        ("Knowledge Base storage",
         f"=Inputs!$B$9*{price(10)}",
         f"=Inputs!$B$9*{price(10)}",
         "Storage cost does not change with on-demand vs batch"),
        ("Knowledge Base retrievals",
         f"=Inputs!$B$13*Inputs!$B$10/1000*{price(11)}",
         f"=Inputs!$B$13*Inputs!$B$10/1000*{price(11)}",
         "Retrieve always runs on-demand, even for the batch draft job"),
        ("Guardrail sensitive information",
         f"=Inputs!$B$13*Inputs!$B$11/1000*{price(12)}",
         f"=Inputs!$B$13*Inputs!$B$11/1000*{price(12)}",
         ""),
        ("Guardrail contextual grounding",
         f"=Inputs!$B$13*Inputs!$B$11/1000*{price(13)}",
         f"=Inputs!$B$13*Inputs!$B$11/1000*{price(13)}",
         ""),
        ("S3 storage",
         f"=Inputs!$B$12*{price(14)}",
         f"=Inputs!$B$12*{price(14)}",
         "Fixed item"),
        ("CloudWatch Logs",
         f"=Inputs!$B$13/1000*{price(15)}",
         f"=Inputs!$B$13/1000*{price(15)}",
         "Fixed item, rough estimate of 1 log line per query"),
    ]
    start_row = 2
    for i, (label, ondemand, batch, note) in enumerate(lines):
        r = start_row + i
        we.cell(r, 1, label)
        we.cell(r, 2, ondemand).number_format = "$#,##0.00"
        we.cell(r, 3, batch).number_format = "$#,##0.00"
        we.cell(r, 4, note)
    total_row = start_row + len(lines)
    we.cell(total_row, 1, "Total").font = BOLD
    we.cell(total_row, 2, f"=SUM(B{start_row}:B{total_row - 1})").number_format = "$#,##0.00"
    we.cell(total_row, 3, f"=SUM(C{start_row}:C{total_row - 1})").number_format = "$#,##0.00"
    we.cell(total_row, 2).font = BOLD
    we.cell(total_row, 3).font = BOLD
    set_col_widths(we, [30, 18, 16, 55])

    # ---- Spend to date ----
    ws2 = wb.create_sheet("Spend to date")
    ws2.append(["Service", "Unblended cost, 2026-09-01 to 2026-09-22 ($)"])
    ws2["A1"].font = HEADER
    ws2["B1"].font = HEADER
    spend = [
        ("Amazon Simple Storage Service", 0.1585988482),
        ("Amazon Bedrock Managed Knowledge Base", 0.0070236996),
        ("AmazonCloudWatch", 0.00090381),
        ("Amazon Bedrock", 0.0002),
        ("AWS Secrets Manager", 0.00003),
        ("AWS Key Management Service", 0.000018),
        ("Amazon Simple Queue Service", 0.0000024),
        ("AWS CloudFormation", 0),
        ("AWS Glue", 0),
        ("Amazon Simple Notification Service", 0),
    ]
    for r, (svc, amt) in enumerate(spend, start=2):
        ws2.cell(r, 1, svc)
        ws2.cell(r, 2, amt).number_format = "$#,##0.0000"
    total_r = 2 + len(spend)
    ws2.cell(total_r, 1, "Total").font = BOLD
    ws2.cell(total_r, 2, f"=SUM(B2:B{total_r - 1})").number_format = "$#,##0.0000"
    ws2.cell(total_r, 2).font = BOLD
    ws2.append([])
    ws2.append(["Source: aws ce get-cost-and-usage, profile mlc-support-poc, "
                "region eu-west-2, run 2026-09-22. Grouped by SERVICE."])
    set_col_widths(ws2, [45, 40])

    out = Path(__file__).resolve().parent.parent / "out"
    out.mkdir(exist_ok=True)
    dest = out / "cost-model.xlsx"
    wb.save(dest)
    print(f"Wrote {dest}")


def demo():
    """Self-check: build the workbook and assert the sheets and a formula exist."""
    build()
    from openpyxl import load_workbook

    dest = Path(__file__).resolve().parent.parent / "out" / "cost-model.xlsx"
    wb = load_workbook(dest)
    assert wb.sheetnames == ["Inputs", "Prices", "Estimate", "Spend to date"]
    assert wb["Estimate"]["B2"].value.startswith("=")
    assert wb["Inputs"]["B13"].value == "=B4*B5"
    print("demo: OK")


if __name__ == "__main__":
    build()
