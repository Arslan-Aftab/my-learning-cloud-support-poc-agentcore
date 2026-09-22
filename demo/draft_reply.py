# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3>=1.43"]
# ///
"""Draft a reply to a support ticket from similar past tickets.

Usage: uv run demo/draft_reply.py "How do I view completion of a policy?"

Reads KnowledgeBaseId, ModelArn, GuardrailId and GuardrailVersion from the
environment (`set -a; source .env; set +a`). Retrieves similar tickets from the
managed Knowledge Base, then asks the model for a labelled draft with the PII
Guardrail on the output. Nothing is sent to a customer.
"""

import os
import sys

import boto3

SYSTEM = """You are a support agent for My Learning Cloud (MLC). Draft a reply to
the new ticket for a human agent to review. Use only the past tickets given.
Start with one line `Label: <howto|tenant-data|bug|unclear>`. For tenant-data,
name the screen to check and the data to request from the customer. Cite each
past ticket you used as [ticketId subject], copying the ID and subject exactly
as given in its heading, for example [K2QNN Password reset email]."""


def subject_of(text, metadata):
    """The ticket subject: the KB `title` metadata, or the doc's `# <subject>` first line."""
    title = metadata.get("title")
    if title:
        return title
    first_line = text.split("\n", 1)[0]
    return first_line.removeprefix("# ").strip() if first_line.startswith("# ") else ""


def draft(question, tenant=None, variant="full", n=5, model_arn=None):
    env = os.environ
    conditions = [{"equals": {"key": "variant", "value": variant}}]
    if tenant:
        conditions.append({"equals": {"key": "tenant", "value": tenant}})
    search = {"numberOfResults": n, "filter": conditions[0] if len(conditions) == 1 else {"andAll": conditions}}
    results = boto3.client("bedrock-agent-runtime").retrieve(
        knowledgeBaseId=env["KnowledgeBaseId"],
        retrievalQuery={"text": question},
        retrievalConfiguration={"managedSearchConfiguration": search},
    )["retrievalResults"]
    sources = [
        {
            "ticketId": r["metadata"].get("ticketId", "?"),
            "subject": subject_of(r["content"]["text"], r["metadata"]),
            "tenant": r["metadata"].get("tenant", "?"),
            "variant": r["metadata"].get("variant", variant),
            "score": r.get("score", 0.0),
            "text": r["content"]["text"],
        }
        for r in results
    ]
    context = "\n\n".join(
        f"### Ticket {s['ticketId']} {s['subject']} ({s['variant']}, score {s['score']:.2f})\n{s['text']}"
        for s in sources
    )
    content = boto3.client("bedrock-runtime").converse(
        modelId=model_arn or env["ModelArn"],
        system=[{"text": SYSTEM}],
        messages=[{"role": "user", "content": [
            {"guardContent": {"text": {"text": f"## Past tickets\n\n{context}", "qualifiers": ["grounding_source"]}}},
            {"guardContent": {"text": {"text": f"## New ticket\n\n{question}", "qualifiers": ["query"]}}},
        ]}],
        guardrailConfig={
            "guardrailIdentifier": env["GuardrailId"],
            "guardrailVersion": env["GuardrailVersion"],
            "trace": "disabled",
        },
    )["output"]["message"]["content"]
    # Sonnet 5 emits a reasoningContent block before the text.
    reply = next(b["text"] for b in content if "text" in b).strip()
    first, _, rest = reply.partition("\n")
    label = first.removeprefix("Label:").strip().lower() if first.startswith("Label:") else "unclear"
    return {"label": label, "draft": rest.strip() if first.startswith("Label:") else reply, "sources": sources}


if __name__ == "__main__":
    out = draft(" ".join(sys.argv[1:]))
    print(f"Label: {out['label']}\n\n{out['draft']}\n\nSources:")
    for s in out["sources"]:
        print(f"{s['ticketId']}  {s['subject']}  {s['tenant']}  {s['score']:.2f}")
