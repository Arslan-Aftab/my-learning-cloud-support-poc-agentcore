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
any command that changes AWS state. The PoC account is not provisioned yet.

Update the requirements table in `README.md` when a requirement changes status.
