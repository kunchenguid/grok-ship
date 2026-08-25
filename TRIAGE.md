# Triage

Written judgment for Firstmate and for the one crewmate per repo signed on from `GROK_BOT_TRIAGE.md` (or a mapped factory crewmate that later received standing triage). This is not an installer. Factory install stays `GROK_SHIP.md`. Do not tell a random bot to follow this file.

One crewmate per repo: standing triage plus factory addendum. Humans talk only to Firstmate. Reports never go to the captain. Do not treat factory scout/ship and standing triage as two bots or two projects rows.

## Queue

Every wake starts with `skills/triage-eligible-fetch`. Work only the numbers it returns, in order, five issues and five PRs. Do not browse the rest of the repo for extra work.

Skip the captain's personal GitHub login (`--owner`, not the org or repo-owner slug) except last-resort ports (`Last-resort port of #N`). Skip automation (dependabot, github-actions, release-please, renovate, `[bot]`, `app/`, Greptile, and similar). Automation comments and reviews do not reset the stamp clock.

A PR that closes a ready-for-pr issue (Fixes / Closes / Resolves only) is worked first. That preference is not a merge vote.

## VISION

If `VISION.md` exists on the default branch, run `skills/vision-md-triage-verdict` before any final decision. Per-rule `aligns` / `does not align` / `cannot tell`, with evidence. Claims are not enough. Inconclusive means do not decide that rule.

No `VISION.md` means you still classify the work; you just have no vision file to cite.

## Classes

- **Security** — flag Firstmate immediately. Do not auto-merge. Do not stale-close while the captain flag is still owed.
- **Default-behavior** — changes what the product does for people who did not opt in. Flag Firstmate only when the item is otherwise ready except for that decision.
- **Opt-in** — new behavior that stays off unless chosen. May auto-merge when the rest of the bar is met.
- **Corrective** — bugfix, test, docs, or restore-intended-behavior. May auto-merge when the rest of the bar is met.

Factory ships on the `GROK_BOT_CREWMATE.md` path still need the captain's word. Do not auto-merge them from a standing triage wake. When Firstmate sends a factory scout or ship, that same crewmate follows `GROK_BOT_CREWMATE.md`; this file does not apply to that wake.

## Ready vs not

May auto-merge only when all of these hold: class is corrective or opt-in; VISION has no `does not align` and no undecided rule that matters; CI green; review is safe; not default-behavior; not security; not a captain hold; not waiting on the author.

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

A standing scheduled wake with an empty eligible list may stay quiet. A tasked ask from Firstmate always gets a reply against the task id, including empty, none, and nothing happened.
