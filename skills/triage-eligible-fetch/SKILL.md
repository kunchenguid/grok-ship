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
  --repo <OWNER/NAME> \
  --owner <captain personal GitHub login> \
  --firstmate-mark "<disclosure line>" \
  --stale-days <days, default 14> \
  --issues 5 \
  --prs 5
```

`--repo` is OWNER/NAME. `--owner` is the captain's personal GitHub login to skip, not the org or repo-owner slug. Both are required. `--firstmate-mark` is required and must match the start of a firstmate comment so those comments do not reset the stamp clock. There is no config file. Flags only.

The script prints JSON: `issues` then `prs`, already ranked, already capped. Work those numbers in that order. A ready-for-pr closer PR is a work-order preference, not a merge vote.

## What the script already does

- Open items only
- Skips `--owner` (captain's personal GitHub login) except a last-resort port (`Last-resort port of #N` in title or body)
- Skips automation authors (dependabot, github-actions, release-please, renovate, `[bot]`, `app/`, Greptile, GraphQL `Bot` actors such as codecov/vercel, and similar)
- Drops those skipped items before walking comments, so a captain with many open issues does not pay a full comment backfill every wake
- Counts existing stamps matching `<!-- *triage: ISO8601` (`triage:`, `gh-axi-triage:`, `treehouse-triage:`). Timestamps after now are ignored, including ready-for-pr stamps on linked closing issues
- Skips a stamped item whose only later activity is a firstmate-mark comment or an automation comment/review, unless that stamp is `--stale-days` old (stale-restamp)
- Firstmate-mark comments (mark at the start of the comment) and automation comments/reviews (including GraphQL Bot actors) do not reset the clock. Author comments (including inline review-thread replies on the diff), author review summaries, and new commits still jump the line
- Issues: unstamped and other live, newer first, then stale-restamp oldest stamp, cap `--issues` (default 5)
- PRs: those that close an **open** same-repo ready-for-pr issue first (Fixes / Closes / Resolves / Closing / Resolving with an issue ref in the PR title, body, or commit message, including `Fixes #1, #2` and title-only `Fixes #N`), then other live, then stale, cap `--prs` (default 5). A bare `fix:` / `Closing this now` is not enough. Cross-repo refs and Development-sidebar user links do not count. GitHub's closing list is keyword-closing refs only (`excludeUserLinked`). Parsed title/body/commit refs that GitHub omitted (title-only, Closing/Resolving, non-default base) are loaded from this repo before ranking. That ranking is a work-order preference, not proof the PR closes the issue.

## Do not

- Do not hardcode an owner login or a firstmate-mark string
- Do not widen the queue past the JSON list
- Do not treat a ready-for-pr closer as permission to merge
