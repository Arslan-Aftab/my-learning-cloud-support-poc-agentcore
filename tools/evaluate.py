# /// script
# requires-python = ">=3.12"
# dependencies = ["boto3>=1.43"]
# ///
"""R10: Bedrock Evaluations RAG job, retrieve-and-generate, bring your own inference responses.

Usage:
  uv run tools/evaluate.py dataset <tickets.json>   # build out/eval/dataset.jsonl
  uv run tools/evaluate.py upload                   # put dataset.jsonl to S3
  uv run tools/evaluate.py start <RoleArn>           # create the evaluation job
  uv run tools/evaluate.py status <JobArn>           # print status and results path

Reads KnowledgeBaseId, BucketName and the model ARNs from the environment
(`set -a; source .env; set +a`). See docs/evaluation.md for the held-out set
rule, the metrics and the doc references for the JSONL schema below.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "demo"))
from draft_reply import draft  # noqa: E402

import boto3

TENANTS = ("spf", "optalis", "stjudescare")
HELD_OUT_SIZE = 20
JUDGE_MODEL = "anthropic.claude-3-7-sonnet-20250219-v1:0"
METRICS = [
    "Builtin.Correctness", "Builtin.Completeness", "Builtin.Helpfulness",
    "Builtin.LogicalCoherence", "Builtin.Faithfulness", "Builtin.Harmfulness",
    "Builtin.Stereotyping", "Builtin.Refusal",
    "Builtin.CitationCoverage", "Builtin.CitationPrecision",
]
RAG_SOURCE = "mlc-support-poc-draft-pipeline"
DATASET_PATH = Path("out/eval/dataset.jsonl")


def messages(ticket):
    """Same visible-message extraction as etl/split_tickets.py."""
    out = []
    for key, author in (("thread", "Customer"), ("adminThread", "MLC"), ("parentThread", "Parent tenant")):
        for m in ticket.get(key) or []:
            if m.get("note"):
                continue
            text = m.get("message", "").strip()
            if text:
                out.append((m["timestamp"], author, text))
    return sorted(out, key=lambda m: m[0])


def held_out_candidates(tickets_path, sample_ids):
    """Closed spf/optalis/stjudescare tickets with an MLC reply, not in the 20-ticket sample."""
    tickets = json.loads(Path(tickets_path).read_text())
    for t in tickets:
        if t["tenant"] not in TENANTS or t["ticketId"] in sample_ids:
            continue
        msgs = messages(t)
        has_mlc_reply = any(a == "MLC" for _, a, _ in msgs)
        closed = bool((t.get("closed") or {}).get("timestamp"))
        if has_mlc_reply and closed:
            yield t, msgs


def sample_ticket_ids():
    """The 20 sample ticket IDs already ingested, from the split_tickets output."""
    return {p.stem for p in Path("out/full").glob("*.md")}


def build_dataset(tickets_path):
    n = 0
    for t, msgs in held_out_candidates(tickets_path, sample_ticket_ids()):
        if n == HELD_OUT_SIZE:
            break
        prompt = "\n".join(f"{a}: {text}" for _, a, text in msgs if a == "Customer")
        reference = "\n".join(text for _, a, text in msgs if a == "MLC")
        try:
            result = draft(prompt, tenant=t["tenant"], variant="customer")
        except (KeyError, StopIteration) as e:
            # ponytail: Sonnet's prompted JSON occasionally fails to parse; skip and try the next candidate.
            print(f"skip {t['ticketId']}: {e}", file=sys.stderr)
            continue
        n += 1
        line = {
            "conversationTurns": [{
                "prompt": {"content": [{"text": prompt}]},
                "referenceResponses": [{"content": [{"text": reference}]}],
                "output": {
                    "text": result["draft"],
                    "modelIdentifier": os.environ["SonnetModelArn"],
                    "knowledgeBaseIdentifier": RAG_SOURCE,
                    "retrievedPassages": {"retrievalResults": [
                        {"name": s["ticketId"], "content": {"text": s["text"]},
                         "metadata": {"ticketId": s["ticketId"], "tenant": s["tenant"]}}
                        for s in result["sources"]
                    ]},
                },
            }],
        }
        yield line


def cmd_dataset(tickets_path):
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = list(build_dataset(tickets_path))
    with DATASET_PATH.open("w") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
    print(f"{len(lines)} lines -> {DATASET_PATH}")
    if lines:
        shape = json.loads(json.dumps(lines[0]))  # redact: print field names only
        def names(d):
            return {k: (names(v[0]) if isinstance(v, list) and v and isinstance(v[0], dict)
                        else names(v) if isinstance(v, dict) else "...") for k, v in d.items()}
        print(json.dumps(names(shape), indent=2))


def cmd_upload():
    boto3.client("s3").upload_file(str(DATASET_PATH), os.environ["BucketName"], "eval/dataset.jsonl")
    print(f"s3://{os.environ['BucketName']}/eval/dataset.jsonl")


def cmd_start(role_arn):
    response = boto3.client("bedrock").create_evaluation_job(
        jobName=f"mlc-support-poc-rag-eval-{__import__('datetime').datetime.now():%Y%m%d-%H%M%S}",
        jobDescription="R10: drafts vs real MLC replies, held-out ticket set",
        roleArn=role_arn,
        applicationType="RagEvaluation",
        evaluationConfig={"automated": {
            "datasetMetricConfigs": [{
                "taskType": "General",
                "dataset": {"name": "mlc_draft_dataset",
                            "datasetLocation": {"s3Uri": f"s3://{os.environ['BucketName']}/eval/dataset.jsonl"}},
                "metricNames": METRICS,
            }],
            "evaluatorModelConfig": {"bedrockEvaluatorModels": [{"modelIdentifier": JUDGE_MODEL}]},
        }},
        inferenceConfig={"ragConfigs": [{"precomputedRagSourceConfig": {
            "retrieveAndGenerateSourceConfig": {"ragSourceIdentifier": RAG_SOURCE}}}]},
        outputDataConfig={"s3Uri": f"s3://{os.environ['BucketName']}/eval/output/"},
    )
    print(response["jobArn"])


def cmd_status(job_arn):
    job = boto3.client("bedrock").get_evaluation_job(jobIdentifier=job_arn)
    print(job["status"])
    print(job["outputDataConfig"]["s3Uri"])


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"dataset": cmd_dataset, "upload": cmd_upload, "start": cmd_start, "status": cmd_status}[cmd](*args)
