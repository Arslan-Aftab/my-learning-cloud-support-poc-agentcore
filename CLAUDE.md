# my-learning-cloud-support-poc-agentcore

Proof of concept: a support agent that drafts replies to escalated My Learning
Cloud (MLC) support tickets from the Lumis platform. Read `docs/architecture.md`
first.

## Layout

- `docs/architecture.md`: infrastructure decision and data flow.
- `data/`: local ticket export. Git ignores it. Never commit ticket data.
- `etl.py`: transforms the Lumis JSON export into Knowledge Base documents.
- `app/`: AgentCore project, created with `agentcore create`.

## AWS

- Account: new isolated PoC account. Region `eu-west-2`.
- Use only the `-ro` Identity Center profile for reads. Ask before any change.
- Read `agentcore/.cli/logs/<command>/` when an `agentcore` command fails.

## Commands

- `python3 etl.py data/super-admin.tickets.json out/`: build documents locally.
- `agentcore dev`: run the agent locally.
- `agentcore deploy`: deploy.
- `agentcore invoke '<ticket json>'`: run the agent against a ticket.
