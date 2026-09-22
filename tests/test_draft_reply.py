# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3>=1.43"]
# ///
"""Self-check for demo/draft_reply.py. Fakes both Bedrock clients.

Usage: uv run tests/test_draft_reply.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))
import draft_reply  # noqa: E402

calls = {}


class Fake:
    def retrieve(self, **kw):
        calls["retrieve"] = kw
        return {"retrievalResults": [{"content": {"text": "old thread"}, "score": 0.7,
                                      "metadata": {"ticketId": "T1", "tenant": "acme", "variant": "full"}}]}

    def converse(self, **kw):
        calls["converse"] = kw
        return {"output": {"message": {"content": [{"text": "Label: howto\nDo this [T1]."}]}}}


draft_reply.boto3.client = lambda name: Fake()
os.environ.update(KnowledgeBaseId="kb", ModelArn="m", GuardrailId="g", GuardrailVersion="1")

out = draft_reply.draft("q")
assert calls["retrieve"]["retrievalConfiguration"]["managedSearchConfiguration"] == {
    "numberOfResults": 5, "filter": {"equals": {"key": "variant", "value": "full"}}}
assert out == {"label": "howto", "draft": "Do this [T1].",
               "sources": [{"ticketId": "T1", "tenant": "acme", "variant": "full", "score": 0.7, "text": "old thread"}]}
assert calls["converse"]["guardrailConfig"] == {"guardrailIdentifier": "g", "guardrailVersion": "1", "trace": "disabled"}
assert "### Ticket T1 (full, score 0.70)\nold thread" in calls["converse"]["messages"][0]["content"][0]["text"]

draft_reply.draft("q", tenant="acme", variant="customer", n=2, model_arn="other")
assert calls["retrieve"]["retrievalConfiguration"]["managedSearchConfiguration"]["filter"] == {"andAll": [
    {"equals": {"key": "variant", "value": "customer"}}, {"equals": {"key": "tenant", "value": "acme"}}]}
assert calls["converse"]["modelId"] == "other"
print("ok")
