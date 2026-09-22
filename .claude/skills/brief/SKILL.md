---
name: brief
description: Write the starting prompt for a new feature chat, one per ticket, bug or PR. Use from the PM chat.
---

Write a brief for a new chat that will do one piece of work: `$ARGUMENTS`.
Do not do the work here.

Read `README.md`, `HANDOFF.md` and `git log --oneline -20` first. Then write
the brief to the chat, as one fenced block the user can paste. Headings, in
this order:

- **Goal**: one sentence. The ticket key if there is one.
- **Done when**: the checks that prove it, such as a test, a command output or
  a requirement row to update.
- **Context**: what already works and what does not, from the README and the
  handoff. Three to six bullets. Link files, do not paste them.
- **Constraints**: PII rules, AWS profile rules, `uv run`, PR target branch.
- **Report back**: open a PR with the repo template and comment on the Jira
  ticket. Research and findings go in `docs/<topic>.md`, one file per task,
  not in `README.md`. Do not edit the README requirements table; give the
  evidence in the PR and the PM chat writes the row after merge.

End with the command to start the chat: `claude --worktree <branch>`.
