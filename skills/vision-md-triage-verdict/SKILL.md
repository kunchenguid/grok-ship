---
name: VISION.md triage verdict
description: Use before any final triage decision when the repo has a VISION.md. Read it in full. Per-rule aligns / does not align / cannot tell, with evidence. Claims are not enough. Cannot-tell / inconclusive / undecided is no verdict and blocks auto-merge. Write a contract-class verdict next to the per-rule list: restore | new-default | opt-in | cannot-tell. new-default and cannot-tell block auto-merge.
---

# VISION.md triage verdict

If the repository has a `VISION.md` on the default branch, read that file in full before any final triage decision. If it does not exist, skip this skill.

Do not special-case a repository. The file in front of you is the only source of rules.

## Rules

Treat each `##` heading in `VISION.md` as one rule. If there are no `##` headings, treat the document as a single rule named after the `#` title, or as `VISION.md` if that is also missing.

For every rule, return exactly one of:

- `aligns` — the change or issue follows that rule. Cite the evidence.
- `does not align` — the change or issue conflicts with that rule. Cite the evidence.
- `cannot tell` — the text of the rule, the change, or both are insufficient. Cite what is missing.

Claims are not enough. A PR title, issue pitch, or author summary does not count as evidence. Read the actual diff, the actual issue body plus the code or docs it names, and the rule text.

Cannot-tell blocks auto-merge. Any rule that is `cannot tell`, inconclusive, or undecided is no verdict: do not auto-merge, do not close as decided on that rule. Flag Firstmate or stop. Do not ignore some undecided rules. Do not coerce `cannot tell` into `aligns` or `does not align`. Do not invent a matching heading. Do not skip a heading.

## Contract-class

Before any merge, close-as-decided, or captain-flag, write a contract-class verdict: restore | new-default | opt-in | cannot-tell.

- restore: the unconfigured run now matches what the product already promised (docs, VISION, existing default path). Auto-merge when otherwise ready.
- new-default: the unconfigured run now does something that promise did not include (new path, reorder, always-on). No auto-merge. Flag Firstmate when otherwise ready.
- opt-in: the new behavior stays off unless the user turns it on. Changing a default-on setting, or shipping a new default-on config, is new-default. Auto-merge when otherwise ready.
- cannot-tell: no auto-merge. Flag Firstmate when otherwise ready.

A VISION motive or "this is a bugfix" does not turn new-default into restore. Restoring means the old default path was already specified and broken. Replacing the specified default path is new-default. Write this next to the VISION per-rule verdict.

## Output

Write a per-rule list, then a one-line overall only if every rule is `aligns`. If any rule is `cannot tell` or `does not align`, say so, do not pretend a full verdict exists, and do not auto-merge. Write the contract-class verdict next to that list.

```
VISION (per rule):
- <rule>: aligns | does not align | cannot tell. <evidence>

Contract-class: restore | new-default | opt-in | cannot-tell. <evidence>
```

## Do not

- Do not auto-merge when any rule is `cannot tell`, inconclusive, or undecided
- Do not ignore some undecided rules
- Do not close as decided on a cannot-tell rule
- Do not auto-merge on new-default or contract-class cannot-tell
- Do not treat a VISION motive or "this is a bugfix" as restore when the unconfigured run now does something the promise did not include
- Do not decide from memory of another repo's VISION.md
- Do not treat a missing file as alignment
- Do not collapse several headings into one vibe
