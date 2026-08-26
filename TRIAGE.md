# Triage

Written judgment for Firstmate and for the one crewmate per repo signed on from `GROK_BOT_TRIAGE.md` (or a mapped factory crewmate that later received standing triage). This is not an installer. Factory install stays `GROK_SHIP.md`. Do not tell a random bot to follow this file.

One crewmate per repo: standing triage plus factory addendum. Humans talk only to Firstmate. Reports never go to the captain. Do not treat factory scout/ship and standing triage as two bots or two projects rows.

## Queue

Every wake starts with `skills/triage-eligible-fetch`. Work only the numbers it returns, in order, five issues and five PRs. Do not browse the rest of the repo for extra work.

Skip the captain's personal GitHub login (`--owner`, not the org or repo-owner slug) except last-resort ports (`Last-resort port of #N`). Skip automation (dependabot, github-actions, release-please, renovate, `[bot]`, `app/`, Greptile, and similar). Firstmate-mark comments and automation comments/reviews do not reset the stamp clock. Author comments, including inline review-thread replies on the diff, and new commits still jump the line.

A PR that closes an open ready-for-pr issue in this repo (Fixes / Closes / Resolves with an issue ref in the title, body, or commit message) is worked first. That preference is a sort hint, not a merge vote and not proof the PR closes the issue. Closed linked issues and cross-repo refs do not consume preferred PR slots.

## VISION

If `VISION.md` exists on the default branch, run `skills/vision-md-triage-verdict` before any final decision. Per-rule `aligns` / `does not align` / `cannot tell`, with evidence. Claims are not enough.

Cannot-tell blocks auto-merge. Any VISION rule that is `cannot tell`, inconclusive, or undecided is no verdict: do not auto-merge, do not close as decided on that rule. Flag Firstmate or stop. Do not ignore some undecided rules.

No `VISION.md` means you still classify the work; you just have no vision file to cite.

## Classes

- **Security** — flag Firstmate immediately. Do not auto-merge. Do not stale-close while the captain flag is still owed.
- **Default-behavior** — changes what the product does for people who did not opt in. Flag Firstmate only when the item is otherwise ready except for that decision.
- **Opt-in** — new behavior that stays off unless chosen. May auto-merge when the rest of the bar is met.
- **Corrective** — bugfix, test, docs, or restore-intended-behavior. May auto-merge when the rest of the bar is met.

Factory ships on the `GROK_BOT_CREWMATE.md` path still need the captain's word. Do not auto-merge them from a standing triage wake. Follow `GROK_BOT_CREWMATE.md` ONLY when Firstmate sends a real factory scout or ship for that repo (product investigation or authorized change). This file does not apply to that factory wake.

## Ready vs not

May auto-merge only when all of these hold: class is corrective or opt-in; VISION has no `does not align` and no `cannot tell` / inconclusive / undecided rule; CI green; review is safe; not default-behavior; not security; not a captain hold; not waiting on the author.

Author and CI blockers stay off the captain desk: no-mistakes failing, CI red, waiting on author. Comment, stamp, stop.

Conflicts: resolve them only when the PR is otherwise auto-merge-ready by the bar above. Otherwise flag Firstmate first.

ready-for-pr issues: help existing PRs that close them. Do not open implementation PRs from triage.

## Stale close

Run `skills/14-day-stale-pr-close` with the charter repo `OWNER/NAME`, owner, disclosure line, and stale days (default 14). Close with `gh pr close <n> --repo <OWNER/NAME> --comment "..."`. Do not clone. Firstmate-mark and bot comments do not reset the author clock. Do not close CLEAN/mergeable PRs, captain holds, last-resort ports unless the original is also stale or closed, or security items that still need a captain flag.

## Voice and stamps

Every public comment starts with the disclosure line Firstmate recorded. End with:

```
<!-- triage: <ISO8601> outcome=<outcome> -->
```

Keep new stamps in that generic form so eligible-fetch continues to see them.

## Wakes

Triage wakes stay in chat or cron, not factory.db. Do not file them as scout or ship. There is no kind=triage.

Standing wakes and Firstmate chat task ids (FM-…) run eligible-fetch, VISION, and stale-close. Never launch a cloud agent for issue fixes. A standing scheduled wake with an empty eligible list may stay quiet. An FM-… ask from Firstmate always gets a reply against that id, including empty, none, and nothing happened.
