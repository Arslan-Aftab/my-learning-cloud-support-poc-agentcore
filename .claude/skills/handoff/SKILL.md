---
name: handoff
description: End-of-day handoff or pre-call catch-up. Updates HANDOFF.md and the README requirements table from git, PRs and Jira. Use from the PM chat.
---

Bring the project state up to date. Mode: `$ARGUMENTS` (`handoff` by default,
or `catchup` for a briefing before a call).

1. Read `HANDOFF.md`, the requirements table in `README.md`,
   `git log --oneline -30`, `gh pr list --state all --limit 10` and the open
   Jira tickets for this project.
2. `handoff`: rewrite `HANDOFF.md`. Keep its structure: where the PoC stands,
   requirements not met, next steps. Open work only. Move a requirement to the
   README table when it is met, with the date and the evidence. Commit with a
   `doc:` prefix. Do not push without asking.
3. `catchup`: do not edit files. Reply with three parts: what works now, what
   is open, and the decisions the call needs. Ten lines or fewer.
