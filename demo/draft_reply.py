# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3>=1.43"]
# ///
"""Draft a reply to a support ticket from similar past tickets.

Usage: uv run demo/draft_reply.py "How do I view completion of a policy?"

Reads KnowledgeBaseId, SonnetModelArn, HaikuModelArn, GuardrailId and
GuardrailVersion from the environment (`set -a; source .env; set +a`). Retrieves similar tickets from the
managed Knowledge Base, then asks the model for a labelled draft with the PII
Guardrail on the output. Nothing is sent to a customer.
"""

import os
import re
import sys

import boto3

SYSTEM = """You are a support agent for My Learning Cloud (MLC). Draft a reply to
the new ticket for a human agent to review. Use only the past tickets given.
Answer in exactly this format, with these three headings and nothing else:

Label: <howto|tenant-data|bug|unclear>
Notes: <one short paragraph for the agent. Cite each past ticket you used as
[ticketId subject], copying the ID and subject exactly as given in its heading,
for example [K2QNN Password reset email]. For tenant-data, name the screen to
check and the data to request from the customer.>
Reply:
<the reply to the customer only, no label, no notes, no citations>"""


def subject_of(text, metadata):
    """The ticket subject: the KB `title` metadata, or the doc's `# <subject>` first line."""
    title = metadata.get("title")
    if title:
        return title
    first_line = text.split("\n", 1)[0]
    return first_line.removeprefix("# ").strip() if first_line.startswith("# ") else ""


def retrieve(question, tenant=None, variant="full", n=5):
    """Similar past tickets, one entry per ticket, best score first. Chunks of one ticket are joined."""
    conditions = [{"equals": {"key": "variant", "value": variant}}]
    if tenant:
        conditions.append({"equals": {"key": "tenant", "value": tenant}})
    search = {"numberOfResults": n, "filter": conditions[0] if len(conditions) == 1 else {"andAll": conditions}}
    results = boto3.client("bedrock-agent-runtime").retrieve(
        knowledgeBaseId=os.environ["KnowledgeBaseId"],
        retrievalQuery={"text": question},
        retrievalConfiguration={"managedSearchConfiguration": search},
    )["retrievalResults"]
    by_ticket = {}
    for r in results:
        ticket_id = r["metadata"].get("ticketId", "?")
        text = r["content"]["text"]
        if ticket_id in by_ticket:
            by_ticket[ticket_id]["text"] += "\n\n" + text
            continue
        by_ticket[ticket_id] = {
            "ticketId": ticket_id,
            "subject": subject_of(text, r["metadata"]),
            "tenant": r["metadata"].get("tenant", "?"),
            "variant": r["metadata"].get("variant", variant),
            "score": r.get("score", 0.0),
            "text": text,
        }
    return list(by_ticket.values())


def generate(question, sources, model="Sonnet"):
    """Ask the model for a labelled draft. `model` is Sonnet or Haiku, ARN from `<model>ModelArn`."""
    env = os.environ
    context = "\n\n".join(
        f"### Ticket {s['ticketId']} {s['subject']} ({s['variant']}, score {s['score']:.2f})\n{s['text']}"
        for s in sources
    )
    content = boto3.client("bedrock-runtime").converse(
        modelId=env[f"{model}ModelArn"],
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
    text = next(b["text"] for b in content if "text" in b)
    label = re.search(r"^Label:\s*(.+)$", text, re.M)
    notes = re.search(r"^Notes:\s*(.*?)(?=^Reply:|\Z)", text, re.M | re.S)
    reply = text.partition("Reply:")[2] if "Reply:" in text else text
    return {
        "label": label.group(1).strip().lower() if label else "unclear",
        "notes": notes.group(1).strip() if notes else "",
        "draft": reply.strip(),
    }

def draft(question, tenant=None, variant="full", n=5, model="Sonnet"):
    sources = retrieve(question, tenant, variant, n)
    return {**generate(question, sources, model), "sources": sources}


if __name__ == "__main__":
    out = draft(" ".join(sys.argv[1:]))
    print(f"Label: {out['label']}\nNotes: {out['notes']}\n\n{out['draft']}\n\nSources:")
    for s in out["sources"]:
        print(f"{s['ticketId']}  {s['subject']}  {s['tenant']}  {s['score']:.2f}")
