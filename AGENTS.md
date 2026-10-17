# AGENTS.md – brief for AI coding assistants

Read this file and `docs/requirements.md` before changing code. When they disagree, `docs/requirements.md` wins; flag the conflict instead of guessing.

## What this project is

What If FC (working title) is a solo entry for the Microsoft Premier League Hackathon, deadline **27 Oct 2026, 11:59 pm PT**. It streams **synthetic** football events through Microsoft Fabric, finds a better alternative to key passes (the **Ghost Pass**) with deterministic Python scoring, and uses two Microsoft Agent Framework agents (on Microsoft Foundry) to explain each moment for an analyst and a casual fan. Category target: Best Azure Cloud Native Integration.

## Non-negotiable rules

1. **Synthetic, fictional data only.** No real clubs, players, logos, footage or match data. Use `data/reference/` clubs and players.
2. **Numbers come from code, never from the LLM.** Coordinates, scores and metrics come from the Tactical Twin (`analytics/`) or KQL. Agents only interpret an evidence packet.
3. **Every overlay is validated** against `core.schemas.Overlay` and the evidence packet before it reaches the UI. On failure: retry once, then use the template fallback, and set `narrative_source="template"`.
4. **Label heuristics honestly.** Tactical Twin values are "tactical option scores", not probabilities. Never call them xG, xA or xT.
5. **No secrets in the repo.** Read config from environment variables (see `.env.example`). Never print keys in logs.
6. **Deterministic by seed.** Anything random takes a seed or an injected `random.Random`; the same seed must reproduce the same events, snapshots, scores and overlays.
7. **Fabric costs money per running hour.** Prefer designs that let the UI work from replay files with Fabric paused.

## Code conventions

- Python 3.11+, fully type-annotated; pydantic v2 for all data contracts. Shared contracts live in `core/schemas.py`; do not duplicate them elsewhere.
- Coordinates in metres on a 105 × 68 pitch, always in the frame of the team in possession (see `core/pitch.py`).
- Small, pure functions in `analytics/`; I/O (Eventstream, KQL, Blob, Foundry) lives at the edges (`simulator/publisher.py`, `api/`, `agents/`).
- Every new module gets tests in `tests/`. Name acceptance tests after their IDs (AT-01 … AT-12) in docstrings.
- Run before committing: `ruff check . && pytest -q`.
- Commit messages: plain, descriptive text only. Do not mention any AI assistant or tool, and do not add `Co-Authored-By`, "Generated with" or similar trailers.
- Keep `data/` files small; generated full matches go to `data/generated/` (git-ignored).

## Repository map

| Folder | Purpose | Status |
| --- | --- | --- |
| `core/` | Contracts (`schemas.py`), pitch geometry, formation shapes | Day 1 – done |
| `simulator/` | Reference data, samples; match engine, scenarios, Eventstream publisher | Day 1 done; engine Day 2 |
| `analytics/` | Tactical Twin, metrics, validator | Day 5 |
| `fabric/` | KQL scripts, Eventstream notes, Lakehouse notebook, pipeline export | Days 3–5, 9 |
| `agents/` | Investigator + Broadcast Director workflow, prompts, templates | Day 6 |
| `api/` | FastAPI app on Azure Container Apps | Day 6 |
| `web/` | React + Vite frontend (SVG pitch, Ghost Pass, Evidence Ledger) | Days 7–8 |
| `infra/` | Deployment scripts | Day 9 |
| `tests/` | pytest suite | ongoing |

## Day plan (see docs/requirements.md for "done when")

1. Sat 17 – contracts, reference data, samples ✅
2. Sun 18 – simulator engine + snapshots + local replay files
3. Mon 19 – gate: Foundry hello agent; Eventstream → Eventhouse
4. Tue 20 – KQL metrics, key-moment triggers, demo scenarios
5. Wed 21 – Tactical Twin, evidence packet, Lakehouse bronze
6. Thu 22 – agents, validator, FastAPI, replay export
7. Fri 23 – React pitch + Ghost Pass
8. Sat 24 – Evidence Ledger, modes, languages, replay controls
9. Sun 25 – deploy; gold table + pipeline + recap
10. Mon 26 – end-to-end on Azure, README, video
11. Tue 27 – buffer and submit

## When unsure

Ask the human rather than inventing Azure resource names, model names, endpoints or credentials.
