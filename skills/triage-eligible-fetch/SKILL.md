---
name: Triage eligible fetch
description: Use at the start of every triage wake. Run fetch.py with the charter flags and work only the returned issue and PR numbers, in order.
---

# Triage eligible fetch

Start every triage wake with this skill. Do not pick issues or PRs from memory, search, or `gh issue list` by hand.

## Command

From the shared Grok Bot computer:

```
python3 /home/box/agent-data/grok-ship/pack/skills/triage-eligible-fetch/fetch.py \
  --repo <owner/name> \
  --owner <owner-login> \
  --firstmate-mark "<disclosure line>" \
  --stale-days <days, default 14> \
  --issues 5 \
  --prs 5
```

`--repo` and `--owner` are required. `--firstmate-mark` is required and must match the start of a firstmate comment so those comments do not reset the stamp clock. There is no config file. Flags only.

The script prints JSON: `issues` then `prs`, already ranked, already capped. Work those numbers in that order. A ready-for-pr closer PR is a work-order preference, not a merge vote.

## What the script already does

- Open items only
- Skips `--owner` except a last-resort port (`Last-resort port of #N` in title or body)
- Skips automation authors (dependabot, github-actions, release-please, renovate, `[bot]`, `app/`)
- Counts existing stamps matching `<!-- *triage: ISO8601` (`triage:`, `gh-axi-triage:`, `treehouse-triage:`)
- Skips a stamped item whose only later activity is a firstmate-mark comment, unless that stamp is `--stale-days` old (stale-restamp)
- Firstmate-mark comments (mark at the start of the comment) do not reset the clock
- Issues: unstamped and other live, newer first, then stale-restamp oldest stamp, cap `--issues` (default 5)
- PRs: those that close a ready-for-pr issue first (Fixes / Closes / Resolves / Closing / Resolving, including `Fixes #1, #2`), then other live, then stale, cap `--prs` (default 5)

## Do not

- Do not hardcode an owner login or a firstmate-mark string
- Do not widen the queue past the JSON list
- Do not treat a ready-for-pr closer as permission to merge
