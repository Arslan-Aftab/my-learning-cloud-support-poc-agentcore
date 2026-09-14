# my-learning-cloud-support-poc-agentcore

Read [`README.md`](README.md) first. It holds the decisions, the findings, the
requirements table and the repo layout. This file holds only the commands and
the rules.

## Commands

```shell
python3 tests/test_split_tickets.py                                  # ETL self-check
python3 etl/split_tickets.py data/super-admin.tickets.json out/      # split the export
```

Standard library only so far. Add `boto3` to `requirements.txt` when `demo/`
needs it.

## Rules

Never commit anything under `data/` or `out/`. The export holds customer PII.

Use only an Identity Center profile with the `-ro` suffix for reads. Ask before
any command that changes AWS state.

Update the requirements table in `README.md` when a requirement changes status.

Track the session goals in Claude todos. Create them at the start of the
session. Add a todo for each new piece of work before you start it. Check the
list before you switch task. Implementation detail drifts the chat away from
the goal, and the list is how we return to it.
