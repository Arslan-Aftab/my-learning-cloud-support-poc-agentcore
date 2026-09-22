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
os.environ.update(KnowledgeBaseId="kb", SonnetModelArn="m", HaikuModelArn="h", GuardrailId="g", GuardrailVersion="1")

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
draft_reply.draft("q", tenant="acme", variant="customer", n=2, model="Haiku")
assert calls["retrieve"]["retrievalConfiguration"]["managedSearchConfiguration"]["filter"] == {"andAll": [
    {"equals": {"key": "variant", "value": "customer"}}, {"equals": {"key": "tenant", "value": "acme"}}]}
assert calls["converse"]["modelId"] == "h"

# Chunks of one ticket are grouped into one source, first (best) score kept.
def retrieve_chunks(self, **kw):
    return {"retrievalResults": [
        {"content": {"text": "# S\n\npart 1"}, "score": 0.9, "metadata": {"ticketId": "T3", "tenant": "a", "variant": "full"}},
        {"content": {"text": "other"}, "score": 0.8, "metadata": {"ticketId": "T4", "tenant": "a", "variant": "full"}},
        {"content": {"text": "part 2"}, "score": 0.6, "metadata": {"ticketId": "T3", "tenant": "a", "variant": "full"}},
    ]}


draft_reply.boto3.client = lambda name: type("F", (), {"retrieve": retrieve_chunks})()
grouped = draft_reply.retrieve("q")
assert [s["ticketId"] for s in grouped] == ["T3", "T4"]
assert grouped[0]["text"] == "# S\n\npart 1\n\npart 2" and grouped[0]["score"] == 0.9
print("ok")
