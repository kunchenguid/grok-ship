---
name: 14-day stale PR close
description: Use to close contributor PRs that have been waiting on the author for stale-days with no author push, comment, or review. Parameterized owner, disclosure line, and stale days. Firstmate-mark and bot comments do not reset the clock.
---

# 14-day stale PR close

Close contributor pull requests that have been waiting on the author past the stale threshold. This is not a merge, not a VISION verdict, and not a factory-ship close.

## Parameters

Read these from the triage charter or the invocation. Do not hardcode them.

- `repo` — `OWNER/NAME` of the target repository. Required on every `gh` call. Do not clone.
- `owner` — captain's personal GitHub login to exempt (not the org or repo-owner slug). Never close that login's PRs except a last-resort port whose original is also stale (or already closed).
- `disclosure-line` — the exact first line of the required close comment.
- `stale-days` — default 14.
- `firstmate-mark` — text that must start a firstmate comment. Usually the disclosure line.

Stamp outcome is `closed-stale-<stale-days>d` (so `closed-stale-14d` at the default).

## Clock

Waiting on author means a prior triage outcome such as `waiting-author`, `waiting-author-no-mistakes`, or an equivalent "please push / fix CI / address review" that the author still owns.

The clock starts at the last **author** push, author comment, author review, or inline review-thread reply on the diff. Firstmate-mark comments and bot comments do not reset it.

Close only when that clock is at least `stale-days` old.

## Do not close

- CLEAN and mergeable PRs (mergeable `MERGEABLE`, merge state `CLEAN`)
- Captain holds (`hold`, `waiting-captain`, `captain-hold`, or a comment that the captain still owes a decision)
- Last-resort ports (`Last-resort port of #N`) unless original `#N` is also past `stale-days` or already closed
- Security items that still need a captain flag
- Owner-authored PRs that are not last-resort ports
- Automation authors (dependabot, github-actions, release-please, renovate, `[bot]`, `app/`, Greptile, and similar)
- Drafts that are not waiting on author
- Anything whose last author push, comment, or review is newer than `stale-days`

## Required comment

The close comment must start with the `disclosure-line` parameter, explain the stale-days wait on the author, and end with an HTML stamp:

```
<disclosure-line> this pull request has been waiting on the author for <stale-days> days with no author push, comment, or review, so I am closing it. Reopen if you intend to continue.

<!-- triage: <ISO8601> outcome=closed-stale-<stale-days>d -->
```

Use `gh pr close <n> --repo <OWNER/NAME> --comment "<body>"`. Do not omit `--repo`. Do not clone the target repo. Do not delete the branch unless the charter says to.

## Do not

- Do not close to tidy the queue
- Do not treat firstmate or bot chatter as author activity
- Do not close a CLEAN mergeable PR as stale
