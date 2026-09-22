# my-learning-cloud-support-poc-agentcore

Read [`README.md`](README.md) first. It holds the decisions, the findings, the
requirements table and the repo layout. This file holds only the commands and
the rules.

## Commands

```shell
uv run tests/test_split_tickets.py                               # ETL self-check
uv run etl/split_tickets.py data/super-admin.tickets.json out/   # split the export
cfn-lint --regions eu-west-2 -t infrastructure/template.yaml     # lint the stack
```

Every script runs with `uv run`. Each one declares its own dependencies in a
[PEP 723](https://peps.python.org/pep-0723/) header, so nobody installs
anything first. There is no `requirements.txt` and no shared virtual
environment. `cfn-lint` is installed with `uv tool install cfn-lint`.

## Rules

Never commit anything under `data/` or `out/`. The export holds customer PII.

Use the `mlc-support-poc` profile. It is an admin profile, so ask before any
command that changes AWS state. Switch to a `-ro` profile for reads once one
exists.

Update the requirements table in `README.md` when a requirement changes status.

Track the session goals in Claude todos. Create them at the start of the
session. Add a todo for each new piece of work before you start it. Check the
list before you switch task. Implementation detail drifts the chat away from
the goal, and the list is how we return to it.
