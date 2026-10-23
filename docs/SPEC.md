# Gameday Intelligence spec

## 1. Goal and judging map

Win the Grand Prize. In the organisers' words: "Best overall solution with real-world impact and innovative use of Microsoft platform. Awarded to the team that delivers the most complete and compelling solution, demonstrating innovative use of the Microsoft AI platform product stack while transforming synthetic football event data into meaningful, explainable match intelligence. The winning solution will also best demonstrate how AI can turn football events and statistics into engaging narratives, contextual insights, and accessible and personalized experiences for fans, analysts, and broadcasters."

Every piece of work is ranked by the phrase of that text it earns. The category label on the submission form (Best Multi-Agent System) is only a form field. It is never the reason to build or cut anything.

| Grand Prize phrase | What earns it | Status on Oct 23 |
|---|---|---|
| Innovative use of the Microsoft AI platform | Foundry models, a multi-agent pipeline on Microsoft Agent Framework, MCP tools, Azure AI Speech, Azure Container Apps, GitHub Copilot Agent Mode with the Azure MCP Server | Not started. The biggest gap. |
| Meaningful, explainable match intelligence | Tracking engine, xG, leverage, Gravity, shape and press, control vs chaos, evidence drawer, held-out validation | Done |
| Engaging narratives | Narrator writes the live cards, Recap writes the full-time report, milestones | Word templates only |
| Contextual insights | Ask the match, leverage, spells, Match Blueprint | Numbers done; Ask the match not started |
| Accessible | English, Spanish and Hindi; voice read-outs; keyboard, contrast and screen-reader pass; Explain simply | Explain simply only |
| Personalized | Depth, favourite clubs, favourite players, player focus, single-metric mode, language | Depth and player focus done |
| For fans, analysts and broadcasters | Live Match; Analyst tab and Match Blueprint; broadcast overlay and cue API | Done |
| Most complete and compelling | Public demo URL, video under 2 minutes, JUDGING.md, published eval pass rate | Not started |

Every submission is also scored on five criteria, 20% each: technological implementation, agentic design and innovation, real-world impact, user experience and demo video, and fit to category. The Grand Prize table above already covers them.

Signature story for judges: "The AI never makes up a number." Every number on screen comes from code, every claim is checked by the Verifier, and every card opens its evidence.

Hero user: a fan watching live. The analyst view is the same fan going deeper. No games, predictions or points.

### Main competitor: Lasso (github.com/bradhack/lasso)

A finished, polished fan phone app with 182 commits. Strengths: Bayesian win probability validated on a held-out season, 7 agents over MCP and A2A, an evaluation harness (27 of 27 answers pass) and a two-agents-vs-one study, Event Hubs, Web PubSub, Cosmos DB, Fabric, Speech in 4 languages, Bicep and azd, CI, WCAG audit, prediction games, VAR, season outlook, a judge guide and jump-to-moment links. Same category label as us.

Gaps we win on:

| Lasso | Gameday Intelligence |
|---|---|
| Ball only, moving between events | All 22 players tracked at 5 frames per second |
| No player focus, speed or distance features | Player focus mode, speed and distance tags, shot speed (all named in the rules) |
| No tactical shape analysis | Low block and high press detection, press resistance, control vs chaos |
| Fan and analyst differ in wording | Analyst gets a different screen: shot quality beeswarm, leverage table |
| Code checks fix AI slips after writing | Agents cannot type numbers at all. Code fills slots, Verifier checks claims, evidence on every card |
| Navy and brass phone app with games | Black broadcast-grade dashboard, no betting-like mechanics |

Do not chase: season simulation, prediction games, Event Hubs, Fabric, A2A, Web PubSub. Learn from their patterns, never copy their code (rules require original work).

## 2. Rules to respect

- Synthetic football-realistic data only. No real match data, footage, names, logos or trademarks.
- Project must be newly built after Sept 29, 2026.
- Required: public GitHub repo with an open source license, working demo URL free to access until Nov 10, 2026, public video under 2 minutes, all in English. No copyrighted music in the video.
- Hero tech to use visibly: Microsoft Foundry, Microsoft Agent Framework, MCP, Azure services. Built with GitHub Copilot where practical, and say so in the README.
- Submit by Oct 27, 2026, 11:59 PM PT.

### Coverage of the full brief

| The brief asks for | Our feature | Status on Oct 23 | Plan |
|---|---|---|---|
| (i)(a) Ingest events as they happen: passes, shots, tackles, possession changes, pressure events, metadata | Simulator streams all of these, plus 5 Hz tracking of all 22 players, through the `Feed` boundary | Done | |
| (i)(b) Interpret into statistics, patterns and context | Live stats engine, Analyst tab, Match Blueprint | Done | |
| (i)(c) Explain why a moment matters | Leverage on every action, key moment cards, evidence drawer with formula | Done, in template words | Narrator agent, Oct 24 |
| (i)(d) Render on screen, timed and machine-readable for synchronized overlays | Live cards, broadcast overlay page, `GET /api/rooms/{room}/cues` with start time and duration | Done | |
| (i)(e) Analyst and casual fan as two different experiences | Depth toggle; analyst depth opens the Analyst tab | Done | Personalizer agent, Oct 25 |
| (i)(e) Favourite club(s) | Several favourite clubs; their cards are marked and filterable | Done Oct 23 | |
| (i)(e) Favourite player(s) | Several favourite players: always tagged on the pitch, cards marked; player focus follows one | Done Oct 23 | |
| (i)(e) Player-focused mode throughout the match | Player focus: ring, tag, live speed and distance, trail | Done | |
| (i)(e) Viewing mode by language | English, Spanish, Hindi for cards, answers and the recap (Personalizer agent) | Done Oct 23 | |
| (i)(e) Viewing mode by a single performance metric | Metric mode: top speed, distance, xG or leverage, as a live board and on pitch tags | Done Oct 23 | |
| (ii) Player name tags, speed and distance indicators when thresholds are reached | Tags on the focus player and card players; top speed cards | Partial: no distance milestones, no tag when any player crosses a threshold | Threshold tags and milestones, Oct 25 |
| (ii) Pass quality: distance, accuracy, difficulty rating | Pass completion model in the engine | Gap: not shown anywhere | Pass quality panel and lines coloured by difficulty, Oct 25 |
| (ii) Ball speed and shot speed | Shot speed on shot pages, from tracking | Partial: live ball speed not shown | Ball speed on the pitch, Oct 25 |
| (ii) Auto-eventing from video | No video in a synthetic project; every metric is computed from tracking automatically | Partial | Stretch: detect passes and shots from raw tracking and report recall against the true events |
| (iii) Key narratives, player-performance context, milestones, match recaps | Narrator writes the cards, Recap agent writes the match report, Analyst answers player questions | Done Oct 23; distance milestones still open | |
| (iv) Control vs chaos, tactical pressure changes, game rhythm | Control and chaos indices, block and press detection, press resistance, spells, momentum | Done | |
| (v) Create or extend a synthetic dataset | Seeded simulator with hidden truth, tracking, calibration report | Done | Publish a dataset with a data card, Oct 26 |
| (vi) Multi-language storytelling | Personalizer writes en, es, hi with slots intact | Done Oct 23 | Azure AI Speech voices, Oct 26 |
| Automated match recaps for studio, broadcast or streaming | Recap agent at full time and on request, in three languages | Done Oct 23 | |
| Studio, broadcast and streaming scenarios | Match Blueprint (studio), overlay page (broadcast), live companion (streaming) | Done | |
| Responsive enough for live play | Room streams frames 10 times a second; agents get an 8 s timeout with a template fallback | Engine done | Agents, Oct 24 |
| Fans in any market tailor their experience | Depth, focus | Partial | Language, clubs, players, metric mode, Oct 25 |

### Benchmark: NBA Inside the Game

The Premier League judges will know NBA Inside the Game (Shot Difficulty, Leverage, Gravity, Zone Defense, Handle Score). It is mostly post-game stats pages with no live narrative, personalization or languages. We bring football versions of its best ideas into a live, verified, personalized experience.

Positioning line: "NBA Inside the Game shows you the numbers after the game. Gameday Intelligence tells you the story live, verified, and made for you."

| NBA feature | Our football version |
|---|---|
| Shot Difficulty (xFG% beeswarm) | Shot quality beeswarm by xG |
| Leverage | Counterfactual leverage with credit split across players |
| Zone Defense detection | Low block and high press detection |
| Defensive Pressure | Press resistance |
| Gravity | Stretch |

Auto-eventing from video is out of scope. Say so in the README.

## 3. Scope

### Core (must ship)

1. Simulator with full 2D tracking at 5 frames per second, fictional league, scenario scripts.
2. Live stats engine: xG, xT, pass difficulty, ball and shot speed, sprints and distance, win probability, momentum, control and chaos.
3. NBA-inspired metrics: counterfactual leverage with player credit, low block and high press detection, press resistance.
4. Live Match screen: 2D pitch, scoreboard, momentum bar, win probability line, overlay cards, key moments list, trace panel.
5. Analyst tab: shot quality beeswarm, player leverage table, press resistance, match leaderboards.
6. Agent pipeline: Editor, Narrator, Verifier, Personalizer, using MCP tools.
7. Personalization: casual or analyst depth, favourite club, player focus mode, languages en, es, hi.
8. Evidence drawer: every card opens the events, numbers and formulas behind it.
9. Ask the match: chat answered by the Analyst agent through MCP tools, with evidence.
10. Replay mode: cached agent outputs so the demo works with Foundry off.
11. Shot replay and player pages (NBA style): click a shot to watch a tracking replay of the move with its difficulty and details; player pages with goals above expected, xG of goals and misses, nearest defender distance and every shot. Built on an explicit `Feed` ingest boundary (`engine/feed.py`).
12. Match Blueprint page (`#/blueprint`), adapted from the NBA Inside the Game Blueprint: match overview, highlight reel of tracking replays, top performers, shot difficulty explorer with the nearest defender named, Gravity heatmap and player card, marking spotlight, leverage spotlight. Updates live and works as the full-time report.
13. Judge-facing extras:
    - `docs/JUDGING.md`: each criterion mapped to the screen, file and number that proves it, plus a 2-minute tour.
    - Jump-to-moment links (for example `/?match=demo&t=55m`) that start playback just before the red card, the shape change and the winner.
    - Agent evaluation harness (`tests/agent_eval.py`): scripted questions and moments at set minutes, every card and answer checked by code, pass rate published in `docs/agent-eval.md` and the README.
    - GitHub Copilot setup: `.vscode/mcp.json` connecting Copilot Agent Mode to our MCP server and the Azure MCP Server, `.github/copilot-instructions.md`, one prompt file in `.github/prompts/`.
    - Infrastructure as code: Bicep in `infra/`, deployed with `azd up`.
    - GitHub Actions CI running pytest and the web build on every push.

### Should (Oct 25 to 26; the Grand Prize names every one of these)

1. Automated match recap by the Recap agent, verified like every card. The brief asks for recaps twice, so this is never cut.
2. Voice read-outs of cards and the recap with Azure AI Speech in en, es and hi.
3. Accessibility pass: keyboard navigation, contrast against the black canvas, screen-reader labels on every chart, reduced motion.
4. Personalization the brief names: several favourite clubs and players, single-metric mode, threshold-triggered player tags, pass quality, live ball speed.
5. A published synthetic dataset with a data card.

### Stretch (only if ahead on Oct 26)

1. Auto-eventing from tracking: detect passes and shots from raw frames and report recall against the true events.
2. Season storylines (drought, upset, comeback, rivalry).
3. Event Hubs adapter behind the stream interface.

### Cut (mention as roadmap in README and video)

Team Mode and Coach agent, producer console, prediction games or points, forks and what-ifs, handle or dribble score, workload watch, multi-season validation, separate glossary screen (use tooltips), languages beyond three, auto-eventing from video.

## 4. Product

Visual direction, tokens, type, chart and pitch rules live in `docs/DESIGN.md`. Follow it for every screen.

One main screen, Live Match, with an Analyst tab beside it. The fan story happens on Live Match so the video stays on one view. Switching to analyst depth also opens the Analyst tab, which makes the "two different experiences" requirement visible in seconds.

Layout:
- Top bar: scoreboard, minute, viewer settings (depth, club, player focus, language, voice on or off).
- Centre: 2D pitch with moving players, ball, and player name tags. Player focus mode highlights one player and shows their live speed, distance and actions.
- Pitch animation: players and ball glide between tracking frames on requestAnimationFrame, timed by the measured gap between frames. The room streams a compact `events` message with each frame batch (passes, shots, won tackles, interceptions, cards, goals); the pitch draws pass lines, shot trails, tackle bursts, card pops and a net ripple on goals from it, shorter at high speed. A goal shows a broadcast GOAL banner. Numbers tick to each new value over 300 ms. Reduced motion turns all of it off.
- Under the pitch: momentum bar and win probability line.
- Right rail: overlay cards as they arrive. Each card has "Show evidence" and "Explain simply" or "Go deeper".
- Bottom drawer: Ask the match chat.
- Side panel (toggle): agent trace for judges, showing each agent step, timing, retries and fallbacks.
- Full time: recap view with the verified recap and key moments timeline.

Analyst tab (updates live):
- Shot quality beeswarm: one row per team, each shot a dot placed on an xG axis from 0 to 1 ("more difficult" on the left). Goals are filled dots in the team colour, misses are grey crosses. Header shows total xG and goals from shots. Hover shows shooter, minute, distance, pressure and xG. Click opens the shot on the pitch.
- Player leverage table: total leverage plus subtypes (shot making, creation, defending, turnovers), sortable, with a club filter.
- Press resistance: players ranked by retention under pressure, with attempts shown so small samples are obvious.
- Match leaderboards: hardest shots scored (lowest xG goals), top leverage moments, top speeds.
- Team shape strip: a timeline showing when each side was in a low block, mid block or high press.
- xG race: cumulative xG for both teams over the match, goals marked with the scorer.
- Pass network: each player's average position while their team has the ball, from tracking, joined by lines for pairs with 2 or more completed passes. Line width is the pass count, node size the passes a player made or received.

Player page: adds a heatmap from every tracking frame on 5 m cells, drawn attacking left to right.

Match Blueprint (`#/blueprint`, built from `GET /api/rooms/{room}/blueprint`, refreshed every 5 s):
- Header: crests, score (the trailing side greyed), live minute or full time.
- Match overview: a headline and a paragraph from word-only templates in `agents/report.py`, slots filled by `app/blueprint.py` (result, top scorer or threat, wasteful finisher, chance battle, best spell, red cards, gravity and leverage callouts). The Recap agent rewrites it in M3.
- Highlights: up to five goals and big chances, each a tracking replay with a broadcast title such as "MENSAH SCORES AFTER A DRIBBLE".
- Top performers: four different players for goals above xG, creation leverage, defensive leverage and average gravity, each with an info tooltip.
- Shot difficulty: the attacking half stood up like the NBA half court, every shot marked Hard (under 0.05 xG), Average or Easy (0.20 and up), goals filled. Filter by half. Clicking a shot shows the shooter, the nearest defender by name, xG on a bar against the 0.12 league average, defender distance, pressure, shot speed, distance, angle and result, with a replay link.
- Gravity: team heatmap in the NBA's diverging scale with an Overall, On-ball or Off-ball switch, and a player card with overall gravity and its final third and build-up, on-ball and off-ball parts.
- Marking spotlight: for each side, the opponent's main threat and the defender who marked them most, with the time bar, shots, xG and goals allowed and passes received.
- Leverage spotlight: each side's top player, total leverage and its four parts as diverging bars.

Broadcast overlay (`#/overlay`): a 1920x1080 stage on a transparent page for OBS or a vision mixer. Score bug with clock and a win probability strip, a GOAL flash in the scoring club's colour, and the newest verified cue as a lower third, held at least 6 s. `?bg=pitch` previews it over the live pitch, `aud=analyst` switches the cue depth.

Personas: casual and analyst. Casual uses short plain sentences. Analyst shows metrics, formulas and comparisons. The facts are the same, only the wording and depth change.

Favourite club: cards are framed from that club's side, and their moments are prioritized.

Player focus: the Editor prioritizes moments involving the chosen player, and the pitch highlights them.

## 5. Architecture

```
Simulator -> Event stream -> Live stats engine -> Shared match state
Shared match state -> (fast path) WebSocket -> Dashboard, under 100 ms
Shared match state -> Moment detector -> Agent team -> Overlay cards, 2 to 5 s
Viewer question -> Analyst agent -> MCP tools -> Verifier -> Answer
Full time -> Recap agent -> Verifier -> Recap
Card text -> Azure Speech -> Audio in the viewer's language
```

- Fast path has no AI. Every event updates state in constant time.
- Slow path is triggered only by detected moments and viewer questions.
- Personalization runs per viewer profile. Cache by (cue_id, persona, club, lang) so repeat viewers do not cost extra calls.
- Replay mode serves cached agent outputs when `REPLAY_MODE=1` or when Foundry fails.

## 6. Data contracts

All models are pydantic v2 in `engine/models.py`. Units: pitch 105 x 68 meters, time in seconds from kickoff.

### MatchEvent
```json
{
  "event_id": "m001-000342",
  "match_id": "m001",
  "t": 2054.2,
  "minute": 34,
  "period": 1,
  "type": "tackle",
  "team": "home",
  "player_id": "H08",
  "x": 61.2, "y": 30.5,
  "end_x": null, "end_y": null,
  "outcome": "won",
  "pressure": 0.7,
  "ball_speed_ms": null,
  "body_part": null,
  "meta": {}
}
```
Types: pass, carry, shot, tackle, interception, foul, card, goal, substitution, possession_change, pressure.

### TrackingFrame (5 per second)
```json
{
  "t": 2054.2,
  "ball": {"x": 61.2, "y": 30.5},
  "players": [{"id": "H08", "team": "home", "x": 61.0, "y": 30.1, "speed_ms": 4.2}]
}
```
Speed, distance, ball speed and shot speed are derived from frames in `engine/metrics.py`, never hand-set.

### StatsUpdate
```json
{
  "t": 2054.2, "score": [1, 1],
  "xg": [0.9, 1.1], "xt": [3.4, 2.8],
  "possession": [0.52, 0.48],
  "win_prob": [0.58, 0.19, 0.23],
  "momentum": 0.31,
  "control_index": 0.64, "chaos_index": 0.22
}
```

### Moment
```json
{
  "moment_id": "m001-mo-07",
  "minute": 34,
  "kind": "leverage_swing",
  "leverage": 1.7,
  "team": "home",
  "players": ["H08"],
  "evidence": {"wp_before": 0.41, "wp_after": 0.58, "wp_opposite": 0.41, "player": "H08", "action": "tackle"},
  "event_ids": ["m001-000340", "m001-000342"],
  "state_ref": "m001@2054.2"
}
```

### Claim
```json
{
  "claim_id": "c1",
  "metric": "win_prob_delta",
  "subject": "home",
  "slot": "wp_delta",
  "direction": "up",
  "minute": 34
}
```

### OverlayEvent
```json
{
  "cue_id": "m001-cue-07",
  "match_id": "m001",
  "t_start": 2056.0,
  "duration_s": 8,
  "kind": "key_moment",
  "audience": "casual",
  "club": "home",
  "lang": "en",
  "template": "{player} wins the ball and lifts home win chance from {wp_before} to {wp_after}.",
  "slots": {"player": "Rivera", "wp_before": "41%", "wp_after": "58%"},
  "verified": true,
  "source_claims": ["c1"],
  "evidence_ref": "m001-mo-07"
}
```
Overlays are timed and machine-readable so a broadcast renderer could draw them. Expose them at `GET /api/matches/{id}/cues` as well as over the WebSocket.

### Answer (Ask the match)
```json
{
  "question": "Why is the away side losing control?",
  "template": "Away completed {away_pass_pct} of passes in the last 10 minutes, down from {away_pass_pct_before}.",
  "slots": {"away_pass_pct": "71%", "away_pass_pct_before": "84%"},
  "tools_used": ["compare_windows"],
  "event_ids": ["m001-000401", "m001-000415"],
  "verified": true,
  "limits": "Based on 38 passes. Small sample."
}
```

## 7. Simulator (`engine/sim/`)

- Seeded numpy generator via `engine/rng.py`.
- Tick loop at 5 Hz for tracking frames. The ball carrier decides every 0.7 to 2.6 seconds: shoot, pass, carry or hold.
- Players move toward formation anchors shifted by ball position, team style and fatigue. Defenders stay goal-side of the ball and squeeze toward goal. Attackers respect an offside line.
- Home attacks toward x = 105 in both halves.
- Each team has hidden truth parameters: attack, defence, press, tempo. Each player has pace, passing, finishing, stamina.
- Action probabilities depend on zone, pressure and traits. Outcomes are sampled from the same true functions the metrics later try to recover.
- State includes momentum and fatigue, so matches have rhythm.
- Scenario script (JSON) can inject incidents at set minutes: red card, injury, formation change. The demo match uses a script so the video has a guaranteed story arc (early goal, red card, comeback).
- Modes: `full` (events and frames) and `events_only` (fast, for calibration and stretch storylines).
- Fictional league: 10 clubs with original names and colours, 18-player squads with invented names.
- Invariants tested: players stay on the pitch, one possession holder at a time, event times increase, score matches goals.
- Realism targets (tune in config): per team per match roughly 10 to 14 shots, 400 to 500 passes, 80 to 85 percent pass completion, about 2.5 to 3 total goals per match. Print a realism report table in the README.
- Playback speed is configurable (1x, 4x, 10x) so a full match fits in a demo.

## 8. Metrics and formulas (`engine/metrics.py`)

```
xG = sigmoid(b0 + b1*distance + b2*angle + b3*header + b4*pressure)
```
Coefficients (in `engine/metrics.py`) give unpressured central shots of about 0.49 from 6 m, 0.24 from 11 m, 0.12 from 16 m and 0.04 from 25 m. Penalties are not simulated. Mean xG per shot over simulated matches is about 0.11, as in real football.

```
xT(z) = s(z)*g(z) + m(z) * SUM_w T(z->w) * xT(w)     (value iteration on a 16 x 12 grid)
pass value = xT(end zone) - xT(start zone)
```

```
P(complete) = sigmoid(c0 + c1*distance + c2*forward + c3*pressure)    forward = cosine of pass direction vs attack direction
pass difficulty = 1 - P(complete)
```

Win probability:
```
lambda_live = w*lambda_prior + (1-w)*xg_per_90_observed,   w = k/(k + minutes_played), k = 30
lambda_state = lambda_live * men_effect * score_effect     (a man down or up; trailing or leading)
exposure = (minutes left before 75 + late_effect * minutes left after 75) / 90
remaining goals per team ~ NegBin(mean lambda_state * exposure, size r), or Poisson if it fits as well
P(win/draw/loss) from the difference, truncated at 10 goals
```
Game-state effects are fitted by a Poisson regression of each minute's xG on the game state, with the pre-match rate as offset (ridge, intercept dropped). The size r is chosen on held-out remaining goals and kept only when it beats Poisson by more than 1 log-likelihood point. Learned on five seasons: losing 1.09x, winning 0.95x, a man down 0.78x per player, a man up 1.14x, after minute 75 1.01x, size 20. Lasso reports 1.08x and 0.94x for losing and winning, learned on its own simulator.

```
WPA = P_after - P_before        (win probability added)
momentum_t = alpha*dxT_t + (1-alpha)*momentum_(t-1),  shown as home minus away
control_index = possession_share * pass_completion
chaos_index = turnovers_per_min_last_5 / baseline
```

Counterfactual leverage (adapted from NBA Leverage, implemented in `engine/leverage.py`):
```
value = P(win) + 0.5 * P(draw)        (so an equaliser gets its due)
possession at a spot = xT(spot) * value(score + 1) + (1 - xT(spot)) * value(score)
swing = value(actual outcome) - value(opposite outcome)
  shot:     goal vs no goal
  tackle:   ball won vs carrier keeps it at that spot
  pass:     completed vs lost at the receiver spot
  turnover: ball lost vs retained
Credit is earned against expectation, so an average player sums to about zero:
  shot:      shooter (goal - xG) * swing for shot making, creator xG * swing for creation,
             stopper xG * swing for defending on a save or block
  pass:      completed pass earns (1 - P(complete)) * swing for creation
  turnover:  ball winner gets the swing for defending, the loser a share for turnovers
  red card:  the change in value goes to the player sent off, under turnovers
Player leverage = sum over the match. Scale: 1.0 leverage = 10 points of win value.
```
Moments rank by |leverage|, not by before and after change.

Block and press detection (from tracking frames, per team, rolling 60 s window while out of possession and the ball is 50 to 85 m from the defending goal, where a block is chosen rather than forced):
```
line_height = mean distance from own goal of the four deepest outfield players
compactness = area of the convex hull of the outfield players
pressers    = defenders within 5 m of the ball
low block:  line_height < 36 m and compactness below 650 m2 (set on training matches, scored on held-out ones)
high press: line_height > 45 m and pressers >= 0.35 on average (calibrated on simulated matches)
mid block:  otherwise
```
Emit a `shape_change` moment when a team's state changes and holds for at least 60 s.

Press resistance (inspired by Bundesliga Pressure Handling):
```
pressured possession = carrier has a defender within 3 m, or event pressure >= 0.6
press resistance = retained / pressured possessions  (retained = still in team possession 5 s later)
```
Show attempts next to every rate. Hide a rate with fewer than 5 attempts.

Gravity (`engine/gravity.py`, adapted from NBA Gravity):
```
attention(player) = sum over outfield defenders of max(0, 1 - distance / 6 m)
gravity = 100 * (attention - league average attention for the same zone and role)
zones: 7.5 m x 6.8 m in attacking coordinates; role: on the ball (nearest attacker within 2 m of a grounded ball) or off it
parts: final third (x >= 70 m) or build-up, on-ball or off-ball
```
The league average is fitted on 8 simulated tracked matches (`python -m engine.gravity`, also run by calibration) and stored in `data/models/gravity.json`. +100 means one extra defender held close. A player's gravity shows after five minutes measured with the ball.

Marking (`engine/matchups.py`): every frame out of possession, each outfield attacker's nearest outfield defender is the marker. Time accumulates per pair; shots, xG, goals and passes received while marked are charged to the marker, and tackles to the tackler. Share = time marking that attacker / time the defender spent defending. A spotlight needs 3 minutes together.

Spells (`engine/spells.py`): for each team, the 10-minute window with the largest threat (xT) margin over the opponent, kept if the team held at least 60% of the threat in it.

Player thresholds: sprint above 7 m/s, high-speed running above 5.5 m/s. Emit a player cue when a player passes a distance milestone or hits a top speed for the match.

Moment detector: emit a moment when |leverage| is above threshold, or for goal, red card, shot with xG above 0.3 or a goal with xG below 0.1, a top speed record, a control to chaos flip, or a shape change. Debounce within 20 seconds.

Calibration (`docs/validation.md`): fit on four simulated seasons, score on a fifth. Report the xG calibration table, the learned game-state effects, and win probability RPS, Brier and log loss at minutes 0, 45 and 75 for the current model, the hand-set effects and a league-average baseline. If we do not beat the baseline, say so.

## 9. Agents (`agents/`)

Built with Microsoft Agent Framework on Foundry. Fast model for Editor and Personalizer, strong model for Narrator, Verifier, Analyst and Recap.

| Agent | Input | Output |
|---|---|---|
| Editor | Moment, recent cards, viewer profiles | Emit or skip, card kind, priority, personas to render. Today the moment detector and its debounce do this in code; the card desk skips older cards when a backlog builds at high speed |
| Narrator (built, `agents/narrator.py`) | Evidence pack JSON: moment, evidence, formatted slot values, required slots, and on a retry the rejected draft with reasons | `template` with slots, plus a `claims` list |
| Verifier (built, `agents/verifier.py`) | Template, claims, moment evidence | Pass, or fail with reasons. Deterministic code, not a model, so it cannot be talked out of a check |
| Personalizer | Verified template, persona, club, language | Rewritten template with every slot kept exactly once |
| Analyst | Viewer question, match state via MCP tools | Answer with slots, claims, tools used, limits |
| Recap | Verified moments and final stats | Recap template with slots and claims |

Rules:
- Every number and every name is a slot. Code fills slots.
- Verifier calls the deterministic `verify_claims` tool. It checks that each slot value exists in evidence and that each claim matches the numbers (direction, size, minute).
- On fail: send reasons back to the author agent. Maximum 2 retries, then use the fallback template for that moment in `agents/fallback.py`.
- Personalizer output is re-checked for slot integrity before use.
- Analyst only uses read-only MCP tools. If the data cannot answer, it says so.
- Timeout per model call: 8 seconds. On timeout use fallback or replay cache.
- All agent steps are logged with timing, retries and fallback used, and shown in the trace panel.

MCP server tools (`mcp_server/`, served at `/mcp` over streamable HTTP by the same app): `get_match_state`, `get_moment_evidence`, `get_player_live`, `compare_windows`, `list_supporting_events`, `get_shot_map`, `get_leverage_table`, `get_team_shape`, `get_press_resistance`, `get_gravity`, `verify_claims`. All read-only, each takes an optional `room`. `.vscode/mcp.json` points GitHub Copilot Agent Mode at it.

How it runs (built Oct 23):
- `agents/llm.py` is the one door for model calls: Microsoft Agent Framework `Agent(client=FoundryChatClient(...))` against the Foundry project, `DefaultAzureCredential`, 8 s timeout, timing, and a replay cache (`REPLAY_MODE=1` answers from `data/replays/agent_cache.json`, `RECORD_REPLAY=1` fills it). Without an endpoint it reports offline and every card keeps its template.
- `agents/desk.py` runs Narrator, then Verifier, then up to 2 retries with the reasons, then the template. Every step is a trace step.
- The room publishes each card instantly with its template, then swaps in the Narrator's verified text with a `card_update` message, so live play never waits on a model.
- The Verifier rejects typed digits and names, unknown slots, missing required slots, details the evidence lacks (headers, penalties, assists, careers, injuries, the crowd), declared claims that contradict the numbers, and wording that implies an unsupported claim ("equaliser" at 1-0, "late" in the 12th minute). Every fallback template passes the same checks.
- `python -m agents.check_foundry` sends one real moment through Foundry and prints the trace.

## 10. Voice (`app/speech.py`), stretch only

- Azure AI Speech text to speech, one neural voice per language (en, es, hi).
- Speak the filled card text when voice is on. Queue so cards never overlap.
- Cache audio by (cue_id, lang). Replay mode uses cached audio.
- If Speech fails, show the card silently. Never block the UI.

## 11. Milestones and plan

| Day | ID | Scope | Acceptance |
|---|---|---|---|
| Oct 22 to 23 | M0 | Repo, license, pydantic models, rng, determinism test, Azure and Foundry setup | `pytest` passes, same seed gives same hash, one Foundry call works from a script |
| Oct 22 to 23 | M1 | Simulator (full and events_only), live stats engine, win probability, counterfactual leverage, block and press detection, press resistance, realism report | Invariants pass, realism table prints, stats and leverage stream from CLI, unit tests for each new metric |
| Oct 23 | M2 | FastAPI, WebSocket, Live Match screen, Analyst tab, then shot pages, accuracy work, animation, overlay and Match Blueprint | Done locally; public URL waits on Azure |
| Oct 24 | M3 | Model wrapper with timeout and fallback, MCP server, Narrator, Verifier, trace panel, Foundry on, Container Apps deploy | Cards are written live by agents on the public URL, a forced failure shows the fallback, the trace shows each agent step |
| Oct 25 | M4 | Personalizer, favourite clubs and players, metric mode, en, es, hi, Ask the match, Recap agent, threshold tags, pass quality, ball speed | Settings change the cards, questions get verified answers, the Blueprint overview is written by the Recap agent |
| Oct 26 | M5 | Azure AI Speech voices, accessibility pass, agent eval harness, dataset and data card, replay mode, Copilot setup files, CI, Bicep and azd, README, JUDGING.md, video script | Eval pass rate published, voice works in three languages, JUDGING.md maps every Grand Prize phrase to a screen |
| Oct 27 | Submit | Feature freeze, polish, record video, submit before 11:59 PM PT | Video under 2 minutes uploaded, repo public, demo URL live, jump links work |

If time is short, cut in this order: auto-eventing, Bicep (keep the manual deploy guide), CI, Copilot prompt file, dataset release. Never cut the agents on Foundry, the Recap agent, languages, the eval harness, JUDGING.md or jump links.

Stretch storylines only start after M4 passes.

## 12. Demo video plan (under 2 minutes)

1. 0:00 to 0:10. Hook: "Football stories do not end with the scoreline. And our AI never makes up a number."
2. 0:10 to 0:35. Casual fan, favourite club set. Live match with all 22 players moving, a key moment card slides in.
3. 0:35 to 0:55. Switch to analyst depth. Same moment, deeper card with its leverage. The Analyst tab shows the shot quality beeswarm and leverage table. Open the evidence drawer.
4. 0:55 to 1:10. Player focus mode with live speed and distance, a shape change card ("Ashford drop into a low block"), and a language switch to Spanish or Hindi.
5. 1:10 to 1:25. Ask the match a question. Verified answer with evidence.
6. 1:25 to 1:40. Trace panel: agents hand off, Verifier rejects a claim, Narrator fixes it.
7. 1:40 to 1:55. Eval pass rate and architecture slide: Foundry, Agent Framework, MCP, Container Apps, Copilot. Full time recap if built.
8. 1:55 to 2:00. Close: "One engine. Next stop, the coaching room."

Use royalty-free or no music. No real club names, badges or footage.

## 13. Risks

- Foundry rate limits or quota: replay cache and template fallback.
- Model availability: use GPT-family models deployable on Foundry. Confirm on day 1.
- Simulator looks unrealistic: realism report, tune config, keep claims modest.
- Scope creep: one milestone at a time, never break `main`, stretch only after M4.
- Cold starts during judging: minimum replicas 1, basic rate limiting.
- Azure costs after the free credit: set a budget alert on day 1.
- Submission site login: resolved with support before Oct 27.
- Lasso is more complete on breadth: win on tracking visuals, analyst depth, verification by construction and design. Never add features just because Lasso has them.
