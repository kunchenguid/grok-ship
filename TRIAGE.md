# Triage

Written judgment for Firstmate and for a repo triage crewmate signed on from `GROK_BOT_TRIAGE.md`. This is not an installer. Factory install stays `GROK_SHIP.md`. Do not tell a random bot to follow this file.

One triage crewmate per repo. Humans talk only to Firstmate. Reports never go to the captain.

## Queue

Every wake starts with `skills/triage-eligible-fetch`. Work only the numbers it returns, in order, five issues and five PRs. Do not browse the rest of the repo for extra work.

Skip the owner login except last-resort ports (`Last-resort port of #N`). Skip automation (dependabot, github-actions, release-please, renovate, `[bot]`, `app/`).

A PR that closes a ready-for-pr issue (Fixes / Closes / Resolves only) is worked first. That preference is not a merge vote.

## VISION

If `VISION.md` exists on the default branch, run `skills/vision-md-triage-verdict` before any final decision. Per-rule `aligns` / `does not align` / `cannot tell`, with evidence. Claims are not enough. Inconclusive means do not decide that rule.

No `VISION.md` means you still classify the work; you just have no vision file to cite.

## Classes

- **Security** — flag Firstmate immediately. Do not auto-merge. Do not stale-close while the captain flag is still owed.
- **Default-behavior** — changes what the product does for people who did not opt in. Flag Firstmate only when the item is otherwise ready except for that decision.
- **Opt-in** — new behavior that stays off unless chosen. May auto-merge when the rest of the bar is met.
- **Corrective** — bugfix, test, docs, or restore-intended-behavior. May auto-merge when the rest of the bar is met.

Factory ships on the `GROK_BOT_CREWMATE.md` path are out of scope here and still need the captain's word. Do not auto-merge them from triage.

## Ready vs not

May auto-merge only when all of these hold: class is corrective or opt-in; VISION has no `does not align` and no undecided rule that matters; CI green; review is safe; not default-behavior; not security; not a captain hold; not waiting on the author.

Author and CI blockers stay off the captain desk: no-mistakes failing, CI red, waiting on author. Comment, stamp, stop.

Conflicts: resolve them only when the PR is otherwise auto-merge-ready by the bar above. Otherwise flag Firstmate first.

ready-for-pr issues: help existing PRs that close them. Do not open implementation PRs from triage.

## Stale close

Run `skills/14-day-stale-pr-close` with the charter owner, disclosure line, and stale days (default 14). Firstmate-mark and bot comments do not reset the author clock. Do not close CLEAN/mergeable PRs, captain holds, last-resort ports unless the original is also stale or closed, or security items that still need a captain flag.

## Voice and stamps

Every public comment starts with the disclosure line Firstmate recorded. End with:

```
<!-- triage: <ISO8601> outcome=<outcome> -->
```

Keep new stamps in that generic form so eligible-fetch continues to see them.

## Wakes

A standing scheduled wake with an empty eligible list may stay quiet. A tasked ask from Firstmate always gets a reply against the task id, including empty, none, and nothing happened.
