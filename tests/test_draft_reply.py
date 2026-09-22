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
        return {"retrievalResults": [{"content": {"text": "# Password reset email\n\nold thread"}, "score": 0.7,
                                      "metadata": {"ticketId": "T1", "tenant": "acme", "variant": "full"}}]}

    def converse(self, **kw):
        calls["converse"] = kw
        return {"output": {"message": {"content": [{"reasoningContent": {}}, {"text": "Label: howto\nDo this [T1 Password reset email]."}]}}}


draft_reply.boto3.client = lambda name: Fake()
os.environ.update(KnowledgeBaseId="kb", ModelArn="m", GuardrailId="g", GuardrailVersion="1")

out = draft_reply.draft("q")
assert calls["retrieve"]["retrievalConfiguration"]["managedSearchConfiguration"] == {
    "numberOfResults": 5, "filter": {"equals": {"key": "variant", "value": "full"}}}
assert out == {"label": "howto", "draft": "Do this [T1 Password reset email].",
               "sources": [{"ticketId": "T1", "subject": "Password reset email", "tenant": "acme",
                            "variant": "full", "score": 0.7, "text": "# Password reset email\n\nold thread"}]}
assert calls["converse"]["guardrailConfig"] == {"guardrailIdentifier": "g", "guardrailVersion": "1", "trace": "disabled"}
content = calls["converse"]["messages"][0]["content"]
grounding = content[0]["guardContent"]["text"]
query = content[1]["guardContent"]["text"]
assert grounding["qualifiers"] == ["grounding_source"]
assert "### Ticket T1 Password reset email (full, score 0.70)\n# Password reset email\n\nold thread" in grounding["text"]
assert query == {"text": "## New ticket\n\nq", "qualifiers": ["query"]}

# Metadata title wins over the "# subject" line in the document text.
def retrieve_with_title(self, **kw):
    calls["retrieve"] = kw
    return {"retrievalResults": [{"content": {"text": "# Wrong subject\n\nbody"}, "score": 0.5,
                                  "metadata": {"ticketId": "T2", "tenant": "acme", "variant": "full", "title": "Real subject"}}]}


draft_reply.boto3.client = lambda name: type("F", (), {"retrieve": retrieve_with_title, "converse": Fake().converse})()
out2 = draft_reply.draft("q")
assert out2["sources"][0]["subject"] == "Real subject"

draft_reply.boto3.client = lambda name: Fake()
draft_reply.draft("q", tenant="acme", variant="customer", n=2, model_arn="other")
assert calls["retrieve"]["retrievalConfiguration"]["managedSearchConfiguration"]["filter"] == {"andAll": [
    {"equals": {"key": "variant", "value": "customer"}}, {"equals": {"key": "tenant", "value": "acme"}}]}
assert calls["converse"]["modelId"] == "other"
print("ok")
