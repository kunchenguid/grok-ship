# Grok Ship

Instructions for setting up a software factory on top of Grok Bot. 
The user just needs to tell any bot in their Grok Bot: follow this file.

This file is an installer. Do not summarize.

## What you are installing

- A Firstmate the captain talks to from then on
- Global skills: lavish-session, adversarial-review, project-management, ahoy
- A local sqlite database for projects and tasks
- A crewmate template for later, per project

## The three computers

- The user's computer: their own machine. Bots never execute here.
- The shared Grok Bot computer: a persistent cloud VM that runs all agents. Everything a bot runs - checks, the database, reviews, lavish-axi - runs here.
- Cursor cloud agents: ephemeral cloud VMs that spin up on demand for project work.

## Files in this pack

Same directory as this file:

- `GROK_BOT_FIRSTMATE.md` — Firstmate charter
- `GROK_BOT_CREWMATE.md` — per-project crewmate charter
- `skills/lavish-session/SKILL.md`
- `skills/adversarial-review/SKILL.md`
- `skills/project-management/SKILL.md`
- `skills/ahoy/SKILL.md`

## Steps

1. Copy this whole pack to `/home/box/agent-data/grok-ship/pack/` on the shared computer (clone or download it first if you only have this file's text). Every later reference to a pack file means that path. If a copy is already there, refresh it.

2. Look at the existing roster (agent profile folders). If a Firstmate already exists, reuse it. Do not create a second.

3. Read `GROK_BOT_FIRSTMATE.md`. CreateAgent name `Firstmate` with that description. If you are already Firstmate, keep your name and update your description instead of cloning yourself.

4. Write four global workflows from the skill files. Names:
   - Lavish session
   - Adversarial review
   - Project management
   - Ahoy
   Use each skill's description line as the workflow description. Do not install extra plugins without a yes from the user.

5. Run the project-management setup: create the sqlite DB if it does not exist. Path is in that skill. Same path every time.

6. Check for lavish-axi on the shared computer. Minimum version 0.1.53. If missing, run `npx -y lavish-axi@latest` or ask the user to install it. Session URLs are served from the shared computer and the user views them from their own computer, so confirm with the user that they can reach it (tailnet or exposed address). Do not pretend the live loop works without it.

7. Detect source control CLIs on the shared computer: `gh`, `glab`, Bitbucket, or Cursor Origin, and verify the CLI is authenticated (for example `gh auth status`) - the adversarial review reads branches through it. Do not assume GitHub. Cloud agents separately need the user's Cursor account connected to whichever source control they use. Ask the user to connect whatever is missing. Do not ask them to paste a token in chat.

8. Message Firstmate with a task id (for example GS-READY). Tell it the skills are installed, the DB path, and to reply ready against that id. Empty or blocked still gets a reply. Tell Firstmate to leave a greeting message to the user.

9. Tell the user: talk only to Firstmate from here. This starter bot is leftover. They can delete it from the sidebar (right-click the row, Delete). You cannot delete it yourself.
