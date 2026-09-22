# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3>=1.43"]
# ///
"""Draft a reply to a support ticket with AgenticRetrieveStream (R17 spike).

Usage: uv run demo/agentic_reply.py "How do I view completion of a policy?"

Reads KnowledgeBaseId, ModelArn, GuardrailId and GuardrailVersion from the
environment (`set -a; source .env; set +a`). One streamed call plans the
search, retrieves from the managed Knowledge Base, and generates the answer.
Nothing is sent to a customer.

Pin the same boto3 floor as draft_reply.py; agentic_retrieve_stream needs a
recent botocore model, so a stale pin fails with UnknownServiceOperation.
"""

import os
import sys
import time

import boto3


def draft(question, tenant=None, variant="full", model_arn=None):
    env = os.environ
    conditions = [{"equals": {"key": "variant", "value": variant}}]
    if tenant:
        conditions.append({"equals": {"key": "tenant", "value": tenant}})
    filter_ = conditions[0] if len(conditions) == 1 else {"andAll": conditions}

    client = boto3.client("bedrock-agent-runtime")
    start = time.monotonic()
    response = client.agentic_retrieve_stream(
        messages=[{"role": "user", "content": {"text": question}}],
        retrievers=[
            {
                "configuration": {
                    "knowledgeBase": {
                        "knowledgeBaseId": env["KnowledgeBaseId"],
                        "retrievalOverrides": {"filter": filter_, "maxNumberOfResults": 5},
                    }
                }
            }
        ],
        agenticRetrieveConfiguration={
            "foundationModelType": "CUSTOM",
            "foundationModelConfiguration": {
                "type": "BEDROCK_FOUNDATION_MODEL",
                "bedrockFoundationModelConfiguration": {
                    "modelConfiguration": {"modelArn": model_arn or env["ModelArn"]}
                },
            },
            "maxAgentIteration": 3,
        },
        # The R3 Guardrail uses ANONYMIZE for PII, which AgenticRetrieveStream
        # rejects outright ("Guardrail with ANONYMIZE action is not
        # supported"). A BLOCK-only guardrail would attach; ours can't.
    )

    steps = []
    answer = ""
    sources = []
    for event in response["stream"]:
        if "traceEvent" in event:
            attrs = event["traceEvent"]["attributes"]
            steps.append(f"{attrs.get('step')}:{attrs.get('status')}")
        elif "responseEvent" in event:
            answer += event["responseEvent"].get("text", "")
        elif "result" in event:
            for chunk in event["result"].get("results", []):
                sources.append(
                    {
                        "ticketId": chunk.get("metadata", {}).get("ticketId", "?"),
                        "text": chunk.get("content", {}).get("text", "")[:80],
                    }
                )
    elapsed = time.monotonic() - start
    return {"answer": answer.strip(), "sources": sources, "steps": steps, "seconds": elapsed}


if __name__ == "__main__":
    out = draft(" ".join(sys.argv[1:]))
    print(f"{out['answer']}\n\nSources:")
    for s in out["sources"]:
        print(f"{s['ticketId']}  {s['text']}")
    print(f"\nRetrieval steps ({out['seconds']:.1f}s): {' -> '.join(out['steps'])}")
