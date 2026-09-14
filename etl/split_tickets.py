"""Split the Lumis ticket export into one Knowledge Base document per ticket.

Usage: python3 etl/split_tickets.py data/super-admin.tickets.json out/ [--limit N]

Writes out/<variant>/<ticketId>.md and a .metadata.json sidecar for each,
where variant is "full" (whole conversation) or "customer" (subject and
customer messages only). Upload with `aws s3 sync out/ s3://<bucket>/tickets/`.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ESCALATION_BOILERPLATE = (
    "This ticket was submitted by an administrator and was therefore "
    "automatically escalated to My Learning Cloud"
)
SYSTEM_MESSAGES = {"Ticket escalated to My Learning Cloud", "Ticket closed"}
AUTHORS = {"thread": "Customer", "adminThread": "MLC", "parentThread": "Parent tenant"}


def messages(ticket):
    """Visible messages across all threads, oldest first."""
    out = []
    for key, author in AUTHORS.items():
        for m in ticket.get(key) or []:
            if m.get("note"):
                continue
            text = m.get("message", "").replace(ESCALATION_BOILERPLATE, "").strip()
            if text and text not in SYSTEM_MESSAGES:
                out.append((m["timestamp"], author, text))
    return sorted(out, key=lambda m: m[0])


def render(ticket, msgs):
    day = lambda ts: datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
    lines = [f"# {ticket['subject'].strip()}", ""]
    lines += [f"**{author}** ({day(ts)}):\n{text}\n" for ts, author, text in msgs]
    return "\n".join(lines)


def typed(value):
    """Managed Knowledge Base metadata values carry an explicit type."""
    if isinstance(value, bool):
        # The managed S3 connector rejects BOOLEAN; store "true"/"false".
        return {"value": {"type": "STRING", "stringValue": str(value).lower()}}
    if isinstance(value, int):
        return {"value": {"type": "NUMBER", "numberValue": value}}
    return {"value": {"type": "STRING", "stringValue": value}}


def metadata(ticket, variant, msgs):
    notes = [m.get("message", "") for m in ticket.get("adminThread") or [] if m.get("note")]
    attributes = {
        "ticketId": ticket["ticketId"],
        "tenant": ticket["tenant"],
        "variant": variant,
        "priority": ticket.get("priority", ""),
        "supportCategory": ticket.get("supportCategory", ""),
        "created": (ticket.get("created") or {}).get("timestamp") or msgs[0][0],
        "closed": (ticket.get("closed") or {}).get("timestamp", 0),
        "reopened": sum("Ticket closed" in n for n in notes) > 1,
        "hasMlcReply": any(a == "MLC" for _, a, _ in msgs),
    }
    return {"metadataAttributes": {k: typed(v) for k, v in attributes.items()}}


def split(tickets, out_dir):
    for ticket in tickets:
        msgs = messages(ticket)
        variants = {"full": msgs, "customer": [m for m in msgs if m[1] == "Customer"]}
        for variant, subset in variants.items():
            path = Path(out_dir, variant, f"{ticket['ticketId']}.md")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render(ticket, subset))
            path.with_suffix(".md.metadata.json").write_text(
                json.dumps(metadata(ticket, variant, msgs), indent=2)
            )


if __name__ == "__main__":
    src, out = sys.argv[1], sys.argv[2]
    tickets = json.loads(Path(src).read_text())
    if "--limit" in sys.argv:
        tickets = tickets[: int(sys.argv[sys.argv.index("--limit") + 1])]
    split(tickets, out)
    print(f"{len(tickets)} tickets -> {out}")
