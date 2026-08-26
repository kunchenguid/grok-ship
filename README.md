<h1 align="center">Grok Ship</h1>
<p align="center">
  <a
    href="https://img.shields.io/badge/platform-Grok%20Bot-blue?style=flat-square"
    ><img
      alt="Platform"
      src="https://img.shields.io/badge/platform-Grok%20Bot-blue?style=flat-square"
  /></a>
  <a href="https://x.com/kunchenguid"
    ><img
      alt="X"
      src="https://img.shields.io/badge/X-@kunchenguid-black?style=flat-square"
  /></a>
  <a href="https://discord.gg/Wsy2NpnZDu"
    ><img
      alt="Discord"
      src="https://img.shields.io/discord/1439901831038763092?style=flat-square&label=discord"
  /></a>
</p>

<h3 align="center">Turn your Grok Bot into a software factory.</h3>

## What it is

Grok Ship is an agent distro for Grok Bot.
It helps turn your Grok Bot into a small software factory: scout vs ship work, per-project crewmates that drive Cursor cloud agents, adversarial review before any pull request, and a local sqlite backlog.

Bots never execute on your machine.
They run on the shared Grok Bot computer; project work runs on ephemeral Cursor cloud agents.

After install, talk only to Firstmate - the one agent you chat with in the factory. If you ask, Firstmate can sign on a repo triage crewmate; that is not part of the factory install.

## Features

- **A software factory on Grok Bot** - you bring work; the factory files it, delegates it, and brings back reports or pull requests.
- **Scout vs ship** - scout is investigation, diagnosis, planning, or audit, and the deliverable is a report, never a PR. Ship is authorized change. Promoting a scout flips the same task row rather than opening a duplicate.
- **Per-project crewmates** - each project or project area gets a persistent crewmate that drives Cursor cloud agents.
- **Review before any PR** - after a ship cloud agent pushes a branch, a fresh adversarial review reads it through the project's forge CLI. No pull request until that pass is clean.
- **Local sqlite backlog** - chat is not the source of truth. Projects and tasks live in a sqlite database on the shared computer.
- **You merge** - factory ships never merge without your word, and never while checks are red. A wired triage crewmate may auto-merge corrective or opt-in work only when CI is green, VISION is aligned with no cannot-tell, and the change is not default-behavior and not security.
- **Forge-agnostic** - detect GitHub, GitLab, Bitbucket, or Cursor Origin. Do not assume GitHub.

## Quick Start

Tell any Grok Bot:

```
follow https://github.com/kunchenguid/grok-ship/blob/main/GROK_SHIP.md
```

That sets up the factory on the shared computer and hands you over to Firstmate.
Talk only to Firstmate from then on.

```
> look at my project xyz, then fix the flaky login test

# The factory files a ship task. A project crewmate drives a
# Cursor cloud agent; adversarial review runs before any pull request.

  PR ready: https://github.com/you/xyz/pull/42

> merge it
```

## How It Works

```
            you
                  │  work requests, decisions, "merge it"
                  ▼
 ┌─────────────────────────────────────┐
 │ Grok Bot software factory           │
 │ sqlite backlog · scout vs ship      │
 └──┬──────────────┬───────────────┬───┘
    │                              │
    ▼              ▼               ▼
 ┌────────┐   ┌────────┐      ┌────────┐
 │crewmate│   │crewmate│      │crewmate│   one per project
 └───┬────┘   └───┬────┘      └───┬────┘
     ▼            ▼               ▼
  Cursor cloud agents
     │
     ├─ ship: branch ► adversarial review ► PR ► you merge
     │
     └─ scout: report, never a PR
```

Work is filed as scout or ship in the local sqlite backlog, then handed to the crewmate whose project charter fits.
Software goes through a project crewmate and a Cursor cloud agent.
Scout reports land on the shared computer.
Ship work is reviewed on the pushed branch before a pull request is opened.

## License

MIT - see [LICENSE](LICENSE).
