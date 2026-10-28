# Gameday Intelligence

Entry for the Microsoft x Premier League "Inside the Game" hackathon. Deadline: Oct 27, 2026, 11:59 PM PT. Goal: win the Grand Prize. Category label: Best Multi-Agent System.

Product: a live match companion for fans. It turns synthetic football events with full player tracking into verified, explainable overlay cards, personalized by club, player, depth and language, with an Analyst tab and Ask the match. Read `docs/SPEC.md` before any task. Main competitor and how we beat it: `docs/SPEC.md` section 1.

## Hard rules

1. Synthetic data only. Fictional clubs, players and league. No real Premier League data, names, logos, badges, footage, trademarks or copyrighted music anywhere, including the video.
2. No LLM calls inside `engine/`. Anything that must be correct (stats, probabilities, rankings, claim checks) is deterministic Python.
3. Same seed gives the same output. All randomness goes through `engine/rng.py`. The determinism test must always pass.
4. Agents never type numbers or names. They write text with slots like `{xg}` and code fills the slots from engine state. The Verifier checks slots and claims.
5. Runtime AI calls go through Microsoft Foundry using Microsoft Agent Framework. Never hardcode keys. Read config from environment variables (`.env`, gitignored). Never commit secrets.
6. Every AI feature has a fallback. If a model call fails or takes longer than 8 seconds, serve template text or a cached replay. The demo must never show an error.
7. Write tests first for engine code (pytest). Run tests before every commit. Small commits with clear messages.
8. Keep `main` always deployable. Never leave it broken.
9. No em dashes anywhere: code comments, docs, UI copy, prompts. Use plain language and short sentences.
10. No medical or injury prediction claims.
11. Scope is fixed in `docs/SPEC.md` section 3. Anything not listed there is out of scope unless I say otherwise.
12. All UI follows `docs/DESIGN.md`: a black broadcast-style dashboard, like a premium TV sports graphics package. Never ship anything on its banned list (blue or purple gradients, glassmorphism, glows, soft rounded cards, sparkle or robot icons, default shadcn look). Read it before any frontend task.

## Stack

- Backend: Python 3.12, FastAPI, pydantic v2, numpy, pytest
- Frontend: React, Vite, TypeScript, Tailwind, recharts
- Agents: Microsoft Agent Framework (Python) on Microsoft Foundry
- MCP: Python MCP server exposing match state tools to agents
- Voice (stretch only): Azure AI Speech (text to speech)
- Hosting: Azure Container Apps (one container serves the API and the built frontend), Bicep in `infra/`, deployed with `azd up`
- CI: GitHub Actions
- Stream: in-memory async queue behind an interface

Ask before adding any dependency outside this list.

## Layout

```
engine/        deterministic core: rng, simulator, metrics, win probability, moments, recap facts
agents/        Foundry agents, prompts, slot filling, verifier, fallbacks, llm wrapper
mcp_server/    MCP tools that expose match state to agents
app/           FastAPI app, WebSocket, replay mode, speech endpoint
web/           React dashboard
data/          scenario scripts and cached replays
docs/          SPEC.md, validation.md, architecture notes, video script
tests/         pytest, agent_eval.py
infra/         Bicep for azd up
.github/       CI workflow, copilot-instructions.md, prompts/
.vscode/       mcp.json for Copilot Agent Mode (our MCP server and Azure MCP Server)
```

## Working style

- Before coding, summarize the plan in 10 lines or fewer. For big changes, wait for my OK.
- Do one milestone at a time (see `docs/SPEC.md`, section 11). Stop when its acceptance checks pass.
- Keep `README.md` current: setup, run, architecture, validation results. Judges read it.
- When unsure about a Microsoft SDK detail, check the current docs instead of guessing.
- Every feature should be visible in the demo video. If it cannot be shown, question whether to build it.

## Environment variables

```
FOUNDRY_PROJECT_ENDPOINT=https://<resource-name>.services.ai.azure.com/api/projects/<project-name>
MODEL_FAST=gpt-5-mini
MODEL_STRONG=gpt-5-mini
SPEECH_REGION=<region>
SPEECH_RESOURCE_ID=<resource-id>
REPLAY_MODE=0
```

Auth: the Foundry SDK (`azure-ai-projects` 2.x) uses `DefaultAzureCredential`. Locally run `az login`. On Azure Container Apps use a managed identity with the Foundry User role on the project and the Cognitive Services Speech User role on the Speech resource. No API keys in code or in the repo.

Model call pattern (confirm against the current quickstart before M3):

```python
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

project = AIProjectClient(endpoint=FOUNDRY_PROJECT_ENDPOINT, credential=DefaultAzureCredential())
openai = project.get_openai_client()
response = openai.responses.create(model=MODEL_FAST, input="...")
print(response.output_text)
```

All model calls go through one wrapper in `agents/llm.py` that adds the 8 second timeout, logging and fallback.
