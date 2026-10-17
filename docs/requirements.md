# What If FC – Requirements & Proposal (v2)

As of 17 Oct 2026 · Aravindh C · working title (earlier drafts: MatchMind); final name decided by day 10.

## Overview

Solo entry for the Microsoft Premier League Hackathon (Inside the Game): a live football intelligence platform that streams synthetic match events through Microsoft Fabric, finds a potentially better alternative to key passes (the **Ghost Pass**), and explains it with evidence-bound AI for analysts and fans. Submission closes 27 Oct 2026, 11:59 pm PT (28 Oct, 12:29 pm IST).

**One-line pitch:** A normal dashboard tells you what happened; What If FC shows what else could have happened, proves why with traceable evidence, and tells the story two ways – for the analyst and for the fan.

**v2 design choices** (after review with Gemini and ChatGPT)

- Headline feature: Ghost Pass counterfactual, scored deterministically in Python, explained by agents.
- Evidence Ledger: every on-screen claim traceable to event IDs, metric values and a versioned formula.
- Two agents, plus a deterministic validator with retry and template fallback.
- Lakehouse and Data Factory in minimal form (bronze + one gold table, one pipeline), built after the core path works.
- Heuristic scores are labelled as such; no xG, xA or xT labels.

**Constraints**

- Solo, about 5 hours a day, 10 working days (17–26 Oct) plus a buffer day.
- Personal goal: hands-on Azure data engineering (Fabric Eventstream, Eventhouse/KQL, Lakehouse, Data Factory) with a GenAI layer.
- Azure free account ($200 credit, 30 days from 17 Oct). Fabric free trial is blocked for this new tenant; a paid Fabric F2 capacity (pay-as-you-go, paused when idle) is used.
- Rules require synthetic, football-realistic data; all clubs and players are fictional.

**Decisions**

- Confirmed 17 Oct: primary category Best Azure Cloud Native Integration, while competing for the Grand Prize; Ghost Pass is the headline feature; Lakehouse + Data Factory in minimal form for learning.
- Frontend: React web app (recommended for UX score); Streamlit only as an emergency fallback.
- All clubs and players are fictional, to avoid third-party trademarks in the demo video.

## Functional requirements

Each requirement traces to a clause in the Official Rules (section 4.1 unless noted) or to a v2 design decision. P0 = needed for the end-to-end demo; P1 = scores points, built after P0 works; P2 = only if time remains.

| ID | Requirement | Source | Priority |
| --- | --- | --- | --- |
| FR-01 | Generate seeded, synthetic, football-realistic match events: passes, shots, tackles, interceptions, pressure, possession changes, match metadata | 4.1(i)(a), 4.1(v), 4.7 | P0 |
| FR-02 | Generate a positions snapshot of all 22 players at each eligible pass (needed for the Ghost Pass) | v2 design | P0 |
| FR-03 | Ingest events as they happen through Fabric Eventstream (real-time or accelerated replay) | 4.1(i)(a) | P0 |
| FR-04 | Live statistics in KQL: pass completion, possession (event-based proxy, labelled), shots, pressure index, momentum index | 4.1(i)(b), 4.1(ii) | P0 |
| FR-05 | Detect key moments in KQL (goal, high-pressure pass in the final third, turnover, momentum swing) | 4.1(i)(c), 4.1(iii) | P0 |
| FR-06 | Tactical Twin: score the actual pass and every plausible alternative teammate with a documented heuristic; return the top alternative and score components | v2 design, 4.1(iv) | P0 |
| FR-07 | Ghost Pass visual: actual pass as a solid line, best alternative as a dashed line, target player and nearby defenders highlighted | 4.1(i)(d), 4.1(ii) | P0 |
| FR-08 | Agents explain why the moment matters, using only evidence from the packet | 4.1(i)(c), 4.1(iv) | P0 |
| FR-09 | Validator checks every overlay (event IDs exist, numbers match, coordinates in bounds, schema valid); retry once, then template fallback | v2 design | P0 |
| FR-10 | Render timed, machine-readable overlays on screen alongside the 2D match view | 4.1(i)(d) | P0 |
| FR-11 | Personalize: Analyst vs Casual fan modes – same numbers, different depth and wording | 4.1(i)(e) | P0 |
| FR-12 | Evidence Ledger drawer: claim, event IDs, metric values and definitions, formula version and weights, validation result, agent vs fallback source | v2 design | P0 |
| FR-13 | Replay mode: play saved events and overlays with Fabric paused, clearly labelled as replay | 4.8 | P0 |
| FR-14 | Pass difficulty rating (0–100) shown in Analyst mode | 4.1(ii) | P1 |
| FR-15 | Personalize by favorite club and favorite player (player-focus mode) | 4.1(i)(e) | P1 |
| FR-16 | Multi-language overlays: English plus Hindi and Spanish, produced in one agent call | 4.1(vi) | P1 |
| FR-17 | Lakehouse bronze + one gold table, and one Data Factory pipeline producing the post-match recap | 4.1(iii), learning goal | P1 |
| FR-18 | Defensive shape outline (convex hull) on the pitch | 4.1(iv) | P2 |
| FR-19 | Ball speed and shot speed metrics | 4.1(ii) | P2 |
| FR-20 | Auto-eventing from video | 4.1(ii) | Out of scope |

**Submission deliverables (4.4):** public GitHub repo, demo video under 2 minutes on YouTube, project pitch naming the Microsoft and Azure technologies used, testing link for judges. All materials in English (4.9).

## Non-functional requirements

| ID | Area | Target |
| --- | --- | --- |
| NFR-01 | Latency | Live stat update on screen within about 5 s of an event; agent narrative for a key moment within about 15 s |
| NFR-02 | Throughput | One match at real-time pace (roughly 1,500–2,500 events per 90 minutes), plus accelerated replay at 10× |
| NFR-03 | Explainability | Every displayed claim resolves to event IDs and metric values in the Evidence Ledger; the same seed always reproduces the same events, scores and Ghost Pass |
| NFR-04 | Reliability | Model calls have timeouts and one bounded retry; validation failure or timeout falls back to a template narrative; deterministic scoring never depends on the model; event processing tolerates duplicate delivery (unique event IDs) |
| NFR-05 | Cost | Total spend under about $50 beyond the free credit; Fabric F2 paused when idle; replay mode needs no Fabric during judging |
| NFR-06 | Security | No secrets in the repo; keys in environment variables or Azure Key Vault; managed identity where supported |
| NFR-07 | Code quality | Modular repo, typed Python, README with setup steps, architecture diagram, tests for simulator and metrics |
| NFR-08 | Responsible AI | Fictional names only; heuristic scores labelled as heuristic (no xG/xA/xT claims); content filter on model outputs; no betting or political content |
| NFR-09 | Portability | Runs locally for development; deployable to Azure Container Apps for the judge-facing demo |

## Architecture

Heavy, deterministic work stays in Fabric (KQL) and Python; agents only interpret validated evidence. One live path drives the overlays; a minimal batch path builds the recap; a replay path keeps the demo usable with Fabric paused.

```text
Match simulator (events + player positions)
   │ JSON events
   ▼
Fabric Eventstream (custom endpoint)
   ├─► Eventhouse (KQL): live stats, key moments ──┐
   └─► Lakehouse (bronze + one gold) ─► Data Factory pipeline ─► recap data
                                                   │
API (FastAPI on Azure Container Apps)  ◄───────────┘
   Tactical Twin (Ghost Pass scoring) → Agent 1 Investigator (KQL tool)
   → Agent 2 Broadcast Director → Validator (retry, then fallback)
   │ validated overlays                    │ save
   ▼                                       ▼
React web app (pitch, Ghost Pass,     Replay store (Blob: overlays + evidence)
Evidence Ledger, Analyst/Fan)  ◄────── replay mode (Fabric paused)
```

**Repository layout**

```text
what-if-fc/
├── core/           # shared pydantic contracts, pitch geometry, formations
├── simulator/      # reference data, match engine, scenarios, snapshots, publisher
├── analytics/      # tactical_twin.py, metrics.py, validation.py
├── fabric/         # eventstream config, KQL scripts, lakehouse notebooks, pipeline export
├── agents/         # investigator, broadcast_director, prompts, workflow
├── api/            # FastAPI: snapshot, events, overlays, replay, analyze, stream
├── web/            # React + Vite: pitch, Ghost Pass, Evidence Ledger
├── data/           # reference/, samples/, scenarios/, replay/ (small files)
├── tests/          # acceptance tests AT-01 to AT-12
├── infra/          # deployment scripts
├── docs/           # requirements, architecture, demo script
├── .env.example
└── README.md
```

**API endpoints**

| Endpoint | Purpose |
| --- | --- |
| GET /health | Readiness check |
| GET /matches/{id}/snapshot | Score, clock, live metrics |
| GET /matches/{id}/events | Recent events |
| GET /matches/{id}/overlays | Validated overlays (polling first) |
| GET /matches/{id}/stream | Server-sent events, added after polling works |
| GET /matches/{id}/replay/{scenario} | Saved deterministic replay |
| POST /matches/{id}/analyze/{event_id} | Run Tactical Twin + agents for a chosen event |

## Data design

A seeded Python simulator produces all data; nothing comes from real matches. Pitch is 105 × 68 m. Coordinates are always in the frame of the team in possession: origin at its left corner flag, x towards the goal it attacks. A positions snapshot expresses all 22 players in that same frame.

**Reference data (generated once):** 4 fictional clubs (formations 4-3-3, 4-2-3-1, 3-5-2; styles possession, direct, high press) with 18 players each, carrying ratings for passing, pace, finishing and pressing that drive the simulation. Implemented in `simulator/reference_data.py`.

**Event record (stream: one JSON object per event)** – contract `core.schemas.MatchEvent`

| Field | Type | Note |
| --- | --- | --- |
| event_id | string | unique; used for de-duplication |
| match_id, scenario_id, seed | string, string, int | reproducibility |
| event_time | timestamp | wall-clock emit time |
| match_clock_s, period | int, int | seconds since kickoff; 1 or 2 |
| event_type | enum | pass, reception, carry, shot, tackle, interception, pressure, foul, goal, kickoff, period_end |
| team_id, player_id | string | actor (absent only for period_end) |
| possession_id | int | groups a possession sequence |
| x, y, end_x, end_y | float | metres, within pitch bounds; end required for pass and carry |
| outcome | enum | complete, incomplete, on_target, off_target, saved, blocked, won, lost (valid combinations enforced) |
| receiver_id | string | passes only (intended receiver) |
| pressure_level | float | 0–1: nearest opponent to the actor, scaled |
| snapshot_id | string | set when a positions snapshot exists for this event |

**Positions snapshot (separate stream/table)** – contract `core.schemas.PositionSnapshot`; written for every pass in the final two thirds and every key moment.

| Field | Type | Note |
| --- | --- | --- |
| snapshot_id, match_id, match_clock_s | string, string, int | joins to the event |
| positions[].player_id, team_id, role | string | 22 rows: 11 per team, one GK each |
| positions[].x, y | float | metres |

Positions come from each team's formation shape (`core/formations.py`), shifted with the ball and phase of play, plus small random jitter.

**Scenarios**

- Background play from the possession engine (target about 80–85% pass completion, 10–18 shots, 1–4 goals per match).
- 3–4 hand-designed demo scenarios with fixed snapshots, so the Ghost Pass is clear on video: missed overlap on the right, forced pass into traffic, late counter-attack, high press turnover.
- One known-answer scenario used by the tests.

**Data quality rules:** coordinates within pitch bounds; event IDs unique; match clock non-decreasing; enums only; every snapshot has exactly 22 players; every snapshot_id on an event resolves.

**Derived metrics (KQL for live metrics; Python for geometry)**

- Pass completion = complete passes / passes, per team, rolling and full match.
- Possession (event-based proxy, labelled as such) = share of on-ball events per team in a 5-minute window.
- Pressure index = pressure events + regains in the opponent half per minute, per team.
- Momentum index = rolling 5-minute weighted share of final-third actions and shots.
- Pass difficulty (0–100) = clamp(1.5 × pass length in m + 30 × receiver pressured + 25 × (1 − lane openness), 0, 100).

**Tactical Twin score (Python, version twin-v1)**

For each eligible pass, every teammate within 40 m who is not in an offside position is a candidate, and so is the actual receiver. Each option gets:

S = 0.35·T + 0.25·P + 0.25·F − 0.15·R

- T (threat): closeness of the receiver to goal and width of the goal angle, scaled 0–1.
- P (progress): forward metres gained divided by 40, clamped 0–1.
- F (feasibility): lane openness (nearest defender to the pass line, 5 m or more = 1) times a length penalty above 35 m.
- R (risk): interception risk on the lane plus pressure on the receiver, scaled 0–1.

A Ghost Pass is shown only when the best alternative beats the actual pass by 0.10 or more and has F of 0.5 or more. Weights are starting values, tuned on the demo scenarios and published with the version. These are heuristic tactical scores, not calibrated probabilities.

## Agent design

Two agents run as one Microsoft Agent Framework workflow on a model deployed in Microsoft Foundry, with deterministic steps on either side. Code decides when a moment matters and computes every number; agents only interpret that evidence and write for each audience.

| Step | Kind | Input | Output |
| --- | --- | --- | --- |
| Evidence packet | Code | Key moment from KQL, event IDs, live metrics, snapshot | Compact JSON packet |
| Tactical Twin | Code | Packet + snapshot | Candidate scores, best alternative, score components, version |
| Agent 1: Investigator | LLM + KQL tool (read-only, parameterised queries) | Packet + Twin result | Structured findings: claims, each citing evidence fields |
| Agent 2: Broadcast Director | LLM | Findings + packet + viewer profiles | Analyst text, Fan text, commentary cue, translations (one structured call) |
| Validator | Code | Agent 2 output + packet | Pass, or retry once with the error list, then template fallback |

**Guardrails**

- Agents never produce coordinates or scores; those come only from the Twin and KQL.
- Validator checks: every event ID exists, every number matches the packet after rounding, coordinates in bounds, schema fields present, calculation version known, Analyst and Fan carry the same numbers.
- Timeouts on each model call; the overlay always ships, from agents or from the template, and the Evidence Ledger says which.

**Overlay contract:** `core.schemas.Overlay`; example in `data/samples/sample_overlay.json`.

**Post-match recap:** Agent 2 runs once over the gold table built by the Data Factory pipeline, through the same validator.

## Personalization and user experience

| Setting | Analyst mode | Casual fan mode |
| --- | --- | --- |
| Content | Score components, pass difficulty, pressure and momentum indices | Story-led caption, one simple number |
| Ghost Pass | Both lines plus the score table for actual vs alternative | Dashed line with a one-line explanation |
| Evidence Ledger | Open by default | One tap away ("Why do we say this?") |
| Frequency | Every detected moment | Only top-ranked moments |

**Viewer profile:** mode (Analyst / Casual fan); favorite club (P1); favorite player, player-focus mode (P1); language English, Hindi, Spanish (P1).

**Screens**

1. Match setup: pick scenario, profile and speed (live 1×, replay 10×); a badge shows Live (Fabric) or Replay.
2. Live view: 2D pitch with animated ball and players, scoreboard, timeline with key-moment markers, overlay layer, Ghost Pass toggle, side panel with live metrics.
3. Evidence Ledger drawer: claim, event IDs, metric values and definitions, Tactical Twin weights and version, validation result, agent or fallback.
4. Post-match recap from the gold table (P1).

**Frontend acceptance behaviour:** new events update the timeline and metrics; selecting a moment highlights its events; Ghost Pass toggles; the Evidence Ledger opens for the selected overlay; switching Analyst/Fan changes wording, never the numbers; replay starts, pauses and restarts with the same sequence.

## Tech stack and cost

| Layer | Service / library | Role | Cost note |
| --- | --- | --- | --- |
| Simulator | Python 3.11+, numpy, azure-eventhub SDK | Events, snapshots, publishing | Free |
| Streaming | Fabric Eventstream (custom endpoint) | Ingest and route events and snapshots | Fabric F2 capacity |
| Hot store | Fabric Eventhouse (KQL database) | Live metrics, key-moment triggers | Fabric F2 capacity |
| Lakehouse (minimal) | Fabric Lakehouse + one PySpark notebook | Bronze + one gold table | Fabric F2 + OneLake storage |
| Orchestration (minimal) | Fabric Data Factory pipeline | Post-match gold build and recap trigger | Fabric F2 capacity |
| Scoring + validation | Python: numpy, pydantic | Tactical Twin, evidence packet, validator | Free |
| Agents | Microsoft Agent Framework (`agent-framework`, `agent-framework-foundry`) | Two-agent workflow | Free library |
| Models | Microsoft Foundry model deployment (chosen on day 3 by region and quota) | LLM for agents | Pay per token from credit |
| API | FastAPI on Azure Container Apps | Endpoints, orchestration, replay | Low; from credit |
| Realtime push | Polling first, then server-sent events | Overlays to the browser | Free |
| Frontend | React + Vite, SVG pitch | Live view, Ghost Pass, Evidence Ledger | Hosted with the API or Static Web Apps |
| Replay store | Azure Blob Storage | Saved overlays and evidence | Pennies |
| Quality | pytest, ruff, GitHub Actions | Acceptance tests AT-01 to AT-12 | Free |

**Fabric F2 cost:** pay-as-you-go is $0.18 per capacity unit per hour (about $0.36/hour for F2) and can be paused; planned use about 60–70 running hours, roughly $20–30 ([Microsoft Fabric blog](https://blog.fabric.microsoft.com/blog/announcing-microsoft-fabric-capacities-are-available-for-purchase)). Pausing bills any smoothed future usage immediately ([SQLBI](https://www.sqlbi.com/nl/t/2410/0/MTc1MjQ=)).

**Azure free account:** $200 credit for the first 30 days (to about 16 Nov), then the subscription is disabled unless upgraded ([Azure offer terms](https://azure.microsoft.com/en-in/offers/ms-azr-0044p/)). Whether Fabric F2 charges draw from this credit is still to be checked in Cost Management.

## Judging criteria coverage

| Criterion (20% each) | What earns it here |
| --- | --- |
| Technological Implementation | Original seeded data generator with positions snapshots; Fabric Eventstream, Eventhouse, Lakehouse, Data Factory; Foundry + Agent Framework; tested Tactical Twin; acceptance tests in CI |
| Agentic Design & Innovation | Counterfactual Ghost Pass; evidence-bound agents with a KQL tool; validator feedback loop with retry and fallback |
| Real-World Impact & Applicability | Broadcast-style overlay contract; Evidence Ledger for trust; event-driven design; cost controls; replay mode |
| User Experience & Presentation | Animated Ghost Pass on a 2D pitch; Analyst vs Fan side by side; multi-language; 110-second demo script |
| Adherence to Category | Cloud Native: Fabric streaming, FastAPI on Container Apps, Blob, Foundry, each with a clear job |

## Delivery plan

About 50 hours over 10 days. The day-3 gate proves Foundry model access and Fabric streaming before anything depends on them; the Python core works locally regardless. Fabric runs only on days marked ON and is paused every night.

| Day | Date | Work (about 5 h) | Done when | Fabric |
| --- | --- | --- | --- | --- |
| 1 | Sat 17 Oct | Repo, folders, pydantic models for event, snapshot and overlay; reference clubs and players | Schemas and sample JSON committed | OFF |
| 2 | Sun 18 Oct | Simulator: possession engine, formation-based positions, snapshots, seeded runs; local replay files | AT-01, AT-02 pass; stats look realistic | OFF |
| 3 | Mon 19 Oct | **Gate:** Foundry project, model deployment, hello agent; Eventstream custom endpoint → Eventhouse; stream one match | Events in KQL; agent replies | ON |
| 4 | Tue 20 Oct | KQL metrics and key-moment triggers; build the 3–4 demo scenarios | AT-03, AT-04 pass | ON |
| 5 | Wed 21 Oct | Tactical Twin, evidence packet, pass difficulty; Lakehouse bronze as an Eventstream destination (1 h) | AT-05 passes; Ghost Pass found in every demo scenario | OFF, ON last hour |
| 6 | Thu 22 Oct | Agent 1 + Agent 2 workflow, validator, retry, fallback; FastAPI endpoints with polling; replay export to Blob | AT-06 to AT-09 pass | ON (testing) |
| 7 | Fri 23 Oct | React: SVG pitch, animation, timeline, overlays, Ghost Pass | Ghost Pass animates from replay data | OFF |
| 8 | Sat 24 Oct | React: Evidence Ledger, Analyst/Fan, languages, replay controls; local end-to-end | AT-10, AT-11 pass | OFF |
| 9 | Sun 25 Oct | Deploy to Container Apps; gold notebook + Data Factory pipeline + recap | Public URL works with Fabric paused; recap generated | ON |
| 10 | Mon 26 Oct | AT-12 end to end on Azure; README, architecture, record and upload video | Video public on YouTube | ON (recording) |
| 11 | Tue 27 Oct | Buffer, clean-browser test of all links, make repo public, submit | Submission confirmed | OFF |

**Scope cuts if behind (in order):** SSE (stay on polling) → Spanish (keep English + Hindi) → favorite club/player → gold table and pipeline (keep bronze) → animation polish.

## Acceptance tests

| ID | Test | Pass condition |
| --- | --- | --- |
| AT-01 | Deterministic simulator | Same seed produces identical events and snapshots |
| AT-02 | Schema validation | Bad fields or out-of-bounds coordinates are rejected |
| AT-03 | Known metric fixture | Small known dataset gives expected KQL metric values |
| AT-04 | Moment detection | Known-answer scenario triggers the expected key moment |
| AT-05 | Candidate ranking | Known positions give the expected Ghost Pass ranking |
| AT-06 | Evidence integrity | Every overlay event ID resolves to a generated event |
| AT-07 | Numeric integrity | Published numbers match computed values after rounding |
| AT-08 | Agent failure | Timeout or malformed output produces the template fallback |
| AT-09 | Persona consistency | Analyst and Fan share the same evidence and numbers |
| AT-10 | Replay determinism | Replay restarts with the same event and overlay sequence |
| AT-11 | UI update | New overlay reaches the UI through polling (or SSE) |
| AT-12 | End to end | Trigger → validated overlay → Ghost Pass on the deployed app |

## Demo script (110 seconds)

| Time | Show | Message |
| --- | --- | --- |
| 0–12 s | Pitch at a key moment | A dashboard tells you what happened; What If FC asks what else could have happened |
| 12–30 s | Events arriving, live KQL metrics, Fabric badge | Real Azure streaming path, not a mock-up |
| 30–52 s | Ghost Pass animates | Actual pass vs the better option, scored in code |
| 52–72 s | Evidence Ledger | Event IDs, score components, formula version, validation passed |
| 72–88 s | Analyst and Fan side by side, language switch | Same evidence, two audiences |
| 88–101 s | Model call forced to fail | Template fallback; the app never invents a claim |
| 101–110 s | Architecture diagram | Fabric + Foundry + Container Apps, cloud native end to end |

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| No model quota on the free subscription, or region lacks the model | Agents blocked | Day-3 gate; try another region or a smaller model; template fallback keeps the demo working |
| Ghost Pass suggestions look unrealistic with generated positions | Weak headline feature | Hand-designed demo scenarios with fixed snapshots; F ≥ 0.5 and offside filter; tune weights on scenarios |
| Fabric F2 charges not covered by credit, or blocked by spending limit | Cost or blocker | Check Cost Management after day 3; pause discipline; replay mode keeps judging cost near zero |
| KQL too awkward for geometry | Lost time | Geometry in Python by design; KQL only for aggregates and triggers |
| Duplicate event delivery | Wrong stats | Unique event IDs; de-duplicate in KQL |
| Agents invent claims | Credibility | Evidence-bound prompts; validator; Evidence Ledger shows the source |
| Scope too large for one person | Incomplete demo | Daily done-when checks; scope cuts in order |
| New to Azure: identity and permission errors | Lost hours | Entra user has Contributor and Fabric Administrator; note fixes in README |
| Public demo fails during judging | Lower score | Clean-browser test; replay mode on cheap hosting; judging ends 10 Nov, inside the credit window |
| Trademark or real-data issues | Disqualification | Fictional clubs and players; no league logos, footage or music in the video |

## Open decisions

- [x] Main category: Cloud Native.
- [x] Lakehouse + Data Factory: minimal version, kept for learning.
- [x] Ghost Pass: headline feature.
- [ ] Frontend: React (proposed) or Streamlit – needed by day 7.
- [ ] Foundry model and region – decided at the day-3 gate.
- [ ] Languages beyond English: Hindi and Spanish, or others – needed by day 6.
- [ ] Final project name – needed by day 10.
