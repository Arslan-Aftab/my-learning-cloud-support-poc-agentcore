# /// script
# requires-python = ">=3.11"
# dependencies = ["openpyxl>=3.1"]
# ///
"""Write out/cost-model.xlsx: an editable R22 cost estimate for the customer.

Run: uv run tools/cost_model.py
The workbook holds real formulas. Edit the orange cells on Inputs; every
total on Estimate recalculates. See docs/cost-model.md.
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ORANGE = PatternFill("solid", fgColor="FCE4D6")
GRAY = PatternFill("solid", fgColor="F2F2F2")
HEADER = Font(bold=True)
BOLD = Font(bold=True)


def set_col_widths(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


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
    wsp = wb.create_sheet("Prices")
    wsp.append(["Item", "Price", "Unit", "Source URL", "Verified", "Notes"])
    for c in range(1, 7):
        wsp.cell(1, c).font = HEADER
    today = "2026-09-22"
    price_rows = [
        ("Claude Sonnet 5, on-demand input", 3.00, "$ / 1M tokens",
         "https://aws.amazon.com/bedrock/pricing/", today,
         "Anthropic on-demand table; the pricing page is a JS tab widget and did "
         "not render a London-specific row this session. Confirm in the console "
         "for the eu. cross-region profile before quoting."),
        ("Claude Sonnet 5, on-demand output", 15.00, "$ / 1M tokens",
         "https://aws.amazon.com/bedrock/pricing/", today, "Same caveat as above."),
        ("Claude Haiku 4.5, on-demand input", 0, "$ / 1M tokens",
         "https://aws.amazon.com/bedrock/pricing/", "NOT VERIFIED",
         "Could not retrieve a Haiku 4.5 figure this session. Fill in from the "
         "console (Bedrock > Model catalog > Haiku 4.5 > pricing) before use."),
        ("Claude Haiku 4.5, on-demand output", 0, "$ / 1M tokens",
         "https://aws.amazon.com/bedrock/pricing/", "NOT VERIFIED", "Same caveat."),
        ("Batch discount", 0.5, "multiplier of on-demand",
         "https://aws.amazon.com/bedrock/pricing/", today,
         "\"Batch mode costs 50 percent less than On-Demand\" (public sector blog, "
         "cross-checked against README R18 finding)."),
        ("Knowledge Base storage", 5.00, "$ / GB / month",
         "https://aws.amazon.com/bedrock/pricing/", "NOT INDEPENDENTLY VERIFIED",
         "Carried over from this repo's README Decisions table. Not "
         "re-confirmed against the pricing page this session."),
        ("Knowledge Base retrieval", 1.00, "$ / 1,000 retrievals",
         "https://aws.amazon.com/bedrock/pricing/", "NOT INDEPENDENTLY VERIFIED",
         "Same as above."),
        ("Guardrail sensitive information filter", 0.10, "$ / 1,000 text units",
         "https://aws.amazon.com/blogs/machine-learning/safeguard-a-generative-ai-travel-agent-with-prompt-engineering-and-amazon-bedrock-guardrails/",
         today,
         "2024 US-East blog figure. Cross-checked against this account's own "
         "Cost Explorer usage (EUW2-Guardrail-SensitiveInformationPolicyPaidUnitsConsumed: "
         "$0.0002 for 2 text units = $0.0001/unit = $0.10/1,000), which matches."),
        ("Guardrail contextual grounding", 0, "$ / 1,000 text units",
         "https://aws.amazon.com/bedrock/pricing/", "NOT VERIFIED",
         "No published per-unit figure found this session. Fill in from the console."),
        ("S3 Standard storage", 0.023, "$ / GB / month",
         "https://docs.aws.amazon.com/solutions/latest/live-streaming-on-aws-with-amazon-s3/cost-example-1.html",
         "NOT REGION-SPECIFIC",
         "US East rate. London (eu-west-2) is typically similar; check "
         "aws.amazon.com/s3/pricing for the exact eu-west-2 figure."),
        ("CloudWatch Logs ingestion", 0.50, "$ / GB",
         "https://aws.amazon.com/blogs/compute/aws-lambda-introduces-tiered-pricing-for-amazon-cloudwatch-logs-and-additional-logging-destinations/",
         "NOT REGION-SPECIFIC",
         "US East first-tier rate. Check aws.amazon.com/cloudwatch/pricing for eu-west-2."),
    ]
    for row in price_rows:
        wsp.append(row)
    set_col_widths(wsp, [38, 10, 20, 55, 24, 60])
    for r in range(2, 2 + len(price_rows)):
        wsp.cell(r, 6).alignment = Alignment(wrap_text=True, vertical="top")

    # ---- Estimate ----
    we = wb.create_sheet("Estimate")
    we.append(["Line", "On-demand $/month", "Batch $/month", "Notes"])
    for c in range(1, 5):
        we.cell(1, c).font = HEADER

    def price(row):
        return f"Prices!$B${row}"

    lines = [
        ("Sonnet 5 input tokens",
         f"=Inputs!$B$13*Inputs!$B$6/1000000*{price(2)}",
         f"=Inputs!$B$13*Inputs!$B$6/1000000*{price(2)}*{price(6)}",
         "queries/month x input tokens / 1M x price"),
        ("Sonnet 5 output tokens",
         f"=Inputs!$B$13*Inputs!$B$7/1000000*{price(3)}",
         f"=Inputs!$B$13*Inputs!$B$7/1000000*{price(3)}*{price(6)}",
         "queries/month x output tokens / 1M x price"),
        ("Haiku 4.5 input tokens",
         f"=Inputs!$B$13*Inputs!$B$6/1000000*{price(4)}",
         f"=Inputs!$B$13*Inputs!$B$6/1000000*{price(4)}*{price(6)}",
         "Haiku prices are NOT VERIFIED, see Prices sheet"),
        ("Haiku 4.5 output tokens",
         f"=Inputs!$B$13*Inputs!$B$7/1000000*{price(5)}",
         f"=Inputs!$B$13*Inputs!$B$7/1000000*{price(5)}*{price(6)}",
         "Haiku prices are NOT VERIFIED, see Prices sheet"),
        ("Knowledge Base storage",
         f"=Inputs!$B$9*{price(7)}",
         f"=Inputs!$B$9*{price(7)}",
         "Storage cost does not change with on-demand vs batch"),
        ("Knowledge Base retrievals",
         f"=Inputs!$B$13*Inputs!$B$10/1000*{price(8)}",
         f"=Inputs!$B$13*Inputs!$B$10/1000*{price(8)}",
         "Retrieve always runs on-demand, even for the batch draft job"),
        ("Guardrail sensitive information",
         f"=Inputs!$B$13*Inputs!$B$11/1000*{price(9)}",
         f"=Inputs!$B$13*Inputs!$B$11/1000*{price(9)}",
         ""),
        ("Guardrail contextual grounding",
         f"=Inputs!$B$13*Inputs!$B$11/1000*{price(10)}",
         f"=Inputs!$B$13*Inputs!$B$11/1000*{price(10)}",
         "Price NOT VERIFIED, see Prices sheet"),
        ("S3 storage",
         f"=Inputs!$B$12*{price(11)}",
         f"=Inputs!$B$12*{price(11)}",
         "Fixed item"),
        ("CloudWatch Logs",
         f"=Inputs!$B$13/1000*{price(12)}",
         f"=Inputs!$B$13/1000*{price(12)}",
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
