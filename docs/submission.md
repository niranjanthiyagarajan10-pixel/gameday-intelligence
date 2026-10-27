# Submission

Deadline: October 27, 2026, 11:59 PM Pacific Time, which is **October 28, 2026, 12:29 PM in India (IST)**.

Submit on the Projects page of https://aka.ms/insidethegame. All materials in English.

## Checklist

- [ ] Project name: Gameday Intelligence
- [ ] Elevator pitch (below)
- [ ] Demo video under 2 minutes, public on YouTube or Vimeo. Footage of the app running; no third-party trademarks, no copyrighted music.
- [ ] Public GitHub repository URL. The repository must be public to be considered.
- [ ] Testing link: the live app (no sign-in needed). It must stay up, free and unrestricted until the end of judging on November 10, 2026.
- [ ] Category: Best Multi-Agent System

## Elevator pitch

Gameday Intelligence is a live match companion that explains football to every fan, in their language, at their depth, without ever making up a number.

**What it does.** A synthetic match streams in with all 22 players tracked. A deterministic engine turns it into xG, live win probability, leverage, gravity and key moments. Twelve AI agents explain it: key moment cards, commentary with a voice, a beat-by-beat breakdown of each goal in 3D, a narrated highlights reel, previews, match reports, a newsdesk and answers to any question about the match. Fans pick casual or analyst depth, one of eight languages, their clubs, their players and a metric to follow.

**The problem it solves.** Stats apps show numbers with no story. AI can tell the story, but it makes numbers up. Our agents never type a number or a name. They write templates with slots, code fills every slot from the match engine, and VAR, our Verifier, checks every claim before a fan sees it. If a model is slow or wrong, a checked template takes over within 8 seconds. In our evals, VAR caught 5,111 of 5,111 planted errors and let through 557 of 557 clean lines.

**Built with.** Microsoft Foundry, Microsoft Agent Framework (agents, a fan-out and fan-in workflow, MCP tools), our own MCP server with 15 tools (also used by GitHub Copilot Agent Mode), Azure AI Speech, Azure Container Apps with a managed identity, OpenTelemetry tracing, and GitHub Actions deploying with OIDC. All data is synthetic, from our own simulator.
