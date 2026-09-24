# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3>=1.43"]
# ///
"""Self-check for demo/draft_reply.py. Fakes both Bedrock clients.

Usage: uv run tests/test_draft_reply.py
"""

import json
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

    def apply_guardrail(self, **kw):
        calls["apply_guardrail"] = kw
        return {"outputs": [{"text": c["text"]["text"].replace("old", "{NAME}")} for c in kw["content"]]}

    def converse(self, **kw):
        calls["converse"] = kw
        return {"stopReason": "end_turn", "output": {"message": {"content": [{"reasoningContent": {}}, {"text": '{"label": "howto", "notes": "Used [T1 Password reset email].", "reply": "Do this."}'}]}},
                "trace": {"guardrail": {"outputAssessments": {"g": [{"contextualGroundingPolicy": {"filters": [
                    {"type": "GROUNDING", "score": 0.9, "threshold": 0.5, "action": "NONE"}]}}]}}}}


draft_reply.boto3.client = lambda name: Fake()
os.environ.update(KnowledgeBaseId="kb", SonnetModelArn="m", HaikuModelArn="h", GuardrailId="g", GuardrailVersion="1")

out = draft_reply.draft("q")
assert calls["retrieve"]["retrievalConfiguration"]["managedSearchConfiguration"] == {
    "numberOfResults": 5, "filter": {"equals": {"key": "variant", "value": "full"}}}
assert out == {"label": "howto", "notes": "Used [T1 Password reset email].", "draft": "Do this.", "blocked": False,
               "grounding": {"GROUNDING": {"score": 0.9, "threshold": 0.5, "action": "NONE"}},
               "sources": [{"ticketId": "T1", "subject": "Password reset email", "tenant": "acme",
                            "variant": "full", "score": 0.7, "text": "# Password reset email\n\n{NAME} thread"}]}
assert calls["converse"]["guardrailConfig"] == {"guardrailIdentifier": "g", "guardrailVersion": "1", "trace": "enabled"}
# PII is masked before the model: sources and question go through ApplyGuardrail, the model sees the masked text.
assert calls["apply_guardrail"]["source"] == "OUTPUT" and len(calls["apply_guardrail"]["content"]) == 2

# A blocked draft is plain text, not JSON: it comes back whole with the scores that caused it.
blocked = {"stopReason": "guardrail_intervened", "output": {"message": {"content": [{"text": "The response was blocked."}]}},
           "trace": {"guardrail": {"outputAssessments": {"g": [{"contextualGroundingPolicy": {"filters": [
               {"type": "GROUNDING", "score": 0.2, "threshold": 0.5, "action": "BLOCKED"}]}}]}}}}
draft_reply.boto3.client = lambda name: type("F", (), {"converse": lambda self, **kw: blocked})()
assert draft_reply.generate("q", []) == {"label": "unclear", "notes": "", "draft": "The response was blocked.", "blocked": True,
                                         "grounding": {"GROUNDING": {"score": 0.2, "threshold": 0.5, "action": "BLOCKED"}}}
draft_reply.boto3.client = lambda name: Fake()
# Sonnet has no structured output on Bedrock: schema goes in the prompt, and a non-JSON reply comes back whole.
assert "outputConfig" not in calls["converse"] and '"enum"' in calls["converse"]["system"][0]["text"]
prose = {"stopReason": "end_turn", "output": {"message": {"content": [{"text": "Hi,\nDo this."}]}}}
draft_reply.boto3.client = lambda name: type("F", (), {"converse": lambda self, **kw: prose})()
assert draft_reply.generate("q", [])["draft"] == "Hi,\nDo this."
# JSON with missing keys, or not an object, falls back too.
for text, want in [('{"reply": "Do this."}', "Do this."), ('{"answer": "x"}', '{"answer": "x"}'), ("42", "42")]:
    prose["output"]["message"]["content"][0]["text"] = text
    got = draft_reply.generate("q", [])
    assert got["draft"] == want and got["label"] == "unclear" and got["notes"] == "", got
draft_reply.boto3.client = lambda name: Fake()
content = calls["converse"]["messages"][0]["content"]
grounding = content[0]["guardContent"]["text"]
query = content[1]["guardContent"]["text"]
assert grounding["qualifiers"] == ["grounding_source"]
assert "### Ticket T1 Password reset email (full, score 0.70)\n# Password reset email\n\n{NAME} thread" in grounding["text"]
assert query == {"text": "## New ticket\n\nq", "qualifiers": ["query"]}

# Metadata title wins over the "# subject" line in the document text.
def retrieve_with_title(self, **kw):
    calls["retrieve"] = kw
    return {"retrievalResults": [{"content": {"text": "# Wrong subject\n\nbody"}, "score": 0.5,
                                  "metadata": {"ticketId": "T2", "tenant": "acme", "variant": "full", "title": "Real subject"}}]}


draft_reply.boto3.client = lambda name: type("F", (), {"retrieve": retrieve_with_title, "converse": Fake().converse,
                                                      "apply_guardrail": Fake().apply_guardrail})()
out2 = draft_reply.draft("q")
assert out2["sources"][0]["subject"] == "Real subject"

draft_reply.boto3.client = lambda name: Fake()
draft_reply.draft("q", tenant="acme", variant="customer", n=2, model="Haiku")
assert calls["retrieve"]["retrievalConfiguration"]["managedSearchConfiguration"]["filter"] == {"andAll": [
    {"equals": {"key": "variant", "value": "customer"}}, {"equals": {"key": "tenant", "value": "acme"}}]}
assert calls["converse"]["modelId"] == "h"
schema = json.loads(calls["converse"]["outputConfig"]["textFormat"]["structure"]["jsonSchema"]["schema"])
assert set(schema["required"]) == {"label", "notes", "reply"} and schema["additionalProperties"] is False

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
