# Judging guide

Gameday Intelligence is a live match companion. AI agents explain a synthetic football match to every fan, in eight languages, at casual or analyst depth, and every number they show is guaranteed by code.

- **Live app:** https://gameday-intelligence.orangecliff-ca1053f4.eastus2.azurecontainerapps.io (no sign-in; a match is always live)
- **Architecture:** [docs/architecture.svg](docs/architecture.svg), explained in the [README](README.md#architecture-end-to-end)
- **Category:** Best Multi-Agent System. Also built for the Grand Prize brief: synthetic events to explainable, personalized match intelligence on the Microsoft AI stack.

## A three-minute tour

1. **Home** (click the Gameday Intelligence logo). The whole product on one page. Watch the demo card: an agent writes a line with slots, code fills them, VAR checks it. The second example is sent back because "4 in 100 is not a clear chance."
2. **Meet the Gameday XI** (on Home). Twelve agents as a team, each marking one fan problem. Press **Kick off** to watch them solve all eleven.
3. **Live Match.** The 3D pitch with all 22 players. Key moment cards arrive as they happen; open one to see its evidence and formula. Switch **Depth** to Analyst and the same moment reads differently. Switch **Language** and everything follows, voice included.
4. **Ask the match** (under the charts on Live Match). Press a suggested question. Open "Show the evidence" to see the MCP tool calls code re-ran to fill each number.
5. **Match Theatre** (the white button on Live Match). Pick a goal and press Explain this moment, or play the narrated Highlights reel.
6. **Trace** (top bar). Every agent step live: drafts, VAR rejections with reasons, retries, fallbacks, timings and OpenTelemetry spans.
7. **Blueprint, Preview, Newsdesk, League.** Before, after and around the match, each written by its own agent over verified facts.
8. **Evals** (`#/evals`, linked from Home). The numbers below, with every check broken out.

## By judging criterion

### Technological implementation

- **Our own synthetic data.** A simulator for a fictional ten-club league: 22 players tracked at 5 frames a second, with events sampled from hidden team strengths and player traits. Checked against real football ranges ([docs/realism.md](docs/realism.md)). Scenario scripts give each fixture a story, and the tests replay every one.
- **Models validated on held-out data.** We refitted xG, team ratings, win probability and game-state effects on four simulated seasons and scored them on a fifth: win probability at kickoff is 29% better than a league-average baseline ([docs/validation.md](docs/validation.md)).
- **Hero technologies.** Microsoft Foundry for every model call. Microsoft Agent Framework for the agents, the card desk workflow and the MCP client. Our own MCP server (15 tools), also used by GitHub Copilot Agent Mode through `.vscode/mcp.json`. Azure AI Speech with Entra ID. Azure Container Apps with a managed identity. GitHub Actions with OIDC.
- **Engineering practice.** 293 pytest tests. Same seed gives the same match, and a test checks it. A test also keeps `engine/` free of any model SDK. CI runs every test and the planted-error eval before it deploys. No keys exist anywhere: managed identity in Azure, OIDC in GitHub.

### Agentic design and innovation

- **Agents never type numbers or names.** They write templates with slots. Code fills each slot from engine state. VAR checks typed numbers and names, unknown slots, claims the evidence cannot back, and wording that implies something false, such as "equaliser" when the score is not level.
- **Rejections are feedback.** VAR sends its reasons back to the agent, which gets up to two retries. After that, or after 8 seconds, a template that was written and translated ahead of time takes over.
- **Tool use you can audit.** The Analyst explores the match through MCP, then cites the tool, arguments and field behind each number. Code re-runs those calls itself and shows them as evidence.
- **Cost-aware.** The Personalizer writes only the languages fans are watching right now. Commentary styles are written once and shared by every viewer.

### Real-world impact and applicability

- **Ready for a real league.** Everything reads a match through one `Feed` interface, so a real league only needs a provider adapter. The overlay is a 1920x1080 transparent page with a timed cues API (`/api/rooms/{room}/cues`), ready for a vision mixer or a rendering partner.
- **Built for production.** The app runs as a single always-on container. The 8 second fallback keeps errors off screen, traces show every step, and the evals run in CI.
- **For every audience.** One verified fact base becomes a casual card, an analyst card, eight languages, a voice, a broadcast graphic and a match report.

### User experience and presentation

- **A black broadcast look**, in the spirit of NBA Inside the Game ([docs/DESIGN.md](docs/DESIGN.md)): condensed type and one signal colour, with no gradients or glows.
- **Balanced front and back end.** A three.js 3D stadium with seven cameras, telestration on goals, beeswarm and xG race charts, a pass network and Gravity heatmaps, all driven by a deterministic engine and a streaming WebSocket API.
- **Everything is one tap from its evidence.**

### Adherence to category: Best Multi-Agent System

| What the category asks | Where to see it |
|---|---|
| Specialized agents with distinct roles | The Gameday XI: twelve agents, one fan problem each (Home, [README](README.md#the-gameday-xi)) |
| Coordination through shared state and handoffs | Agents share the match room and the MCP tools. The card desk is an Agent Framework workflow: Dispatch fans out to two Narrators in parallel, Settle fans back in, then the Personalizer runs. The Producer chains the Explainer's verified stories into one reel. |
| Recovery from failures | VAR rejections with reasons and up to two retries; 8 second timeouts; templates translated ahead of time; Foundry rate limits queued and retried. All visible in Trace. |
| An outcome one agent could not achieve as well | One agent cannot narrate, check itself, translate, present and answer questions live without making up numbers. Splitting the work, with VAR in code, is what makes 0 errors on screen possible. |

## The numbers

From `python -m tests.agent_eval`. The results are in `data/evals/report.json` and on `#/evals`.

| Check | Result |
|---|---|
| Planted errors caught (typed numbers and names, false claims, made-up details, broken translations, fake tools, across every agent) | **5,111 of 5,111** |
| Clean lines let through | **557 of 557** |
| Live agent lines on Foundry that went out in the agent's own words | 199 of 206 (97%); the other 7 kept a verified template |
| Numbers in a published line that no slot supplied | **0** |
| Ask the match | 10 of 12 right, 2 declined, 0 wrong answers shown; 3 of 3 unanswerable questions honestly refused |

## What we learned

The eval harness and live runs found real bugs, and each one became a check:

- A fallback template that overclaimed. Templates are now covered by the eval.
- Missing checks: gendered pronouns, units after slots, a doubled plus sign, "drawn", "early" and "late win".
- VAR rejected true lines about team shape and about past leads. We fixed the checks, and now clean lines are tested as well as planted errors.
- With more facts on offer, the model pinned numbers on the wrong player. The In-depth Analyst now gets only the facts for its card.
- A comeback was credited to both sides. The facts now name the comeback team.
- Foundry rate limits under load. Calls are now queued and retried, inside the 8 second budget.
- Our own simulator had a flaw: one hidden setting decided almost every match. Validation caught it ([docs/validation.md](docs/validation.md)).

## Rules we kept

- Synthetic data only. Every club, player, crest and league is fictional and made by us.
- No language model inside `engine/`.
- No secrets in the repository.
