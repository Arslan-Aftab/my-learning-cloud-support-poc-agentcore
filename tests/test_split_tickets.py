# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_split_sample_ticket():
    out = Path(tempfile.mkdtemp())
    subprocess.run(
        [sys.executable, ROOT / "etl/split_tickets.py", ROOT / "tests/fixtures/ticket_HQGNC.json", out],
        check=True,
    )
    full = (out / "full/HQGNC.md").read_text()
    customer = (out / "customer/HQGNC.md").read_text()
    raw = json.loads((out / "full/HQGNC.md.metadata.json").read_text())["metadataAttributes"]
    meta = {k: next(iter(v["value"].values().__reversed__())) for k, v in raw.items()}

    assert full.startswith("# unable to add training course\n")
    assert "**MLC**" in full and "**MLC**" not in customer
    assert "Assignment changed" not in full, "internal notes must be dropped"
    assert "automatically escalated" not in full, "boilerplate must be stripped"
    assert full.index("not showing error") < full.index("**MLC**") < full.index("give this a go")
    assert meta["reopened"] == "true" and meta["hasMlcReply"] == "true"
    assert meta["variant"] == "full" and meta["tenant"] == "bb-luton"
    assert raw["created"]["value"]["type"] == "NUMBER" and raw["reopened"]["value"]["type"] == "STRING"


if __name__ == "__main__":
    test_split_sample_ticket()
    print("ok")
