# Operations Runbook – What If FC

Reference for day-to-day Fabric operations, replay rebuilds, and live testing.

---

## 1 — Pause and resume Fabric capacity

**Capacity name**: `plhackf2`  
Fabric F2 is billed per running hour. Pause when not actively streaming or querying.

### Pause

1. Go to [app.fabric.microsoft.com](https://app.fabric.microsoft.com) → **Admin portal** →
   **Capacity settings** → **plhackf2**.
2. Click **Pause** and confirm.

### Resume

1. Same path → **Resume**.
2. Wait ~2 minutes for the capacity to become active.
3. **Always reactivate the three Eventstream destinations after every resume** (they
   disconnect when the capacity is paused — see section 2).

---

## 2 — Reactivate Eventstream destinations after resume

All three destinations disconnect when the capacity pauses. Reactivate them in the
Fabric portal every time you resume.

For each destination listed below, open the relevant Eventstream item, find the
destination node, and click **Activate** (or **Refresh** if it shows a warning):

| Destination | Eventstream | Target |
|-------------|-------------|--------|
| `dst-events` | `whatif-es` | Eventhouse `whatif` → table `events` |
| `dst-bronz` | `whatif-es` | Lakehouse `whatif_lh` → table `bronze_events` |
| `dst-snapshots` | `whatif-snapshots` | Eventhouse `whatif` → table `snapshots` |

**Verification**: send a test event with `--dry-run` disabled, then run:

```kql
events | count
snapshots | count
```

in the KQL queryset and confirm the counts increase.

---

## 3 — Recreate KQL functions after schema changes

KQL functions are stored in the Eventhouse and survive capacity pause/resume.  
Only re-run them if the database was dropped, the function logic changed, or you
see "function not found" errors in the API logs.

Open the `whatif` KQL queryset in Fabric. Run each `.create-or-alter function` block
**as a separate cell** (do not paste all scripts at once — Fabric rejects multi-block
statements):

| File | Function(s) |
|------|-------------|
| `fabric/kql/02_events_clean.kql` | `EventsClean()` |
| `fabric/kql/03_match_stats.kql` | `MatchStats(p_match_id)` |
| `fabric/kql/04_momentum.kql` | `Momentum(p_match_id)` |
| `fabric/kql/05_pressure.kql` | `PressureIndex(p_match_id)` |
| `fabric/kql/06_key_moments.kql` | `KeyMoments(p_match_id)` |
| `fabric/kql/07_headline_moments.kql` | `HeadlineMoments(p_match_id)` |
| `fabric/kql/08_snapshots.kql` | `SnapshotsClean()`, `GetSnapshot(p_match_id, p_snapshot_id)` |
| `fabric/kql/09_live.kql` | `LiveMatches()`, `EventsSince(p_match_id, p_clock_s)`, `LatestSnapshot(p_match_id)`, `MatchSnapshot(p_match_id, p_snapshot_id)` |

### Verification

Run this in the queryset and confirm the output shows exactly **12 functions**:

```kql
.show functions
| where Folder == "whatif"
| project Name, Parameters
| order by Name asc
```

Expected names: `EventsClean`, `EventsSince`, `GetSnapshot`, `HeadlineMoments`,
`KeyMoments`, `LatestSnapshot`, `LiveMatches`, `MatchSnapshot`, `MatchStats`,
`Momentum`, `PressureIndex`, `SnapshotsClean`.

---

## 4 — Rebuild and upload replay bundles

Replays are stored in `whatifreplay` blob storage, container `replay`.
Run from the project root with `.env` loaded:

```bash
# Build only (saves to data/replay/*.json, no upload)
python -m scripts.build_replay

# Build with agent-generated narratives (slower, requires Foundry)
python -m scripts.build_replay --agents

# Build and upload to Blob storage
python -m scripts.build_replay --upload

# Build with agents and upload
python -m scripts.build_replay --agents --upload
```

`DefaultAzureCredential` is used for the upload. In local dev this picks up your
`az login` session. On the Container App it uses the `id-whatif-api` managed identity.

**After uploading**, the Container App serves the new bundles automatically — no
restart needed (the store re-reads from Blob on every request).

---

## 5 — Run a live test

A live test streams a synthetic match into Fabric and watches the overlay pipeline
produce moments in real time.

### Prerequisites

- Fabric capacity is running and all three destinations are active (section 2).
- `.env` is populated with valid `EVENTSTREAM_CONNECTION_STRING`,
  `SNAPSHOT_EVENTSTREAM_CONNECTION_STRING`, `KQL_CLUSTER_URI`, `KQL_DATABASE`,
  `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`.

### Steps

**Terminal 1 – start the API in live mode**

```bash
WHATIF_MODE=live uvicorn api.main:app --reload
```

**Terminal 2 – stream a match**

```bash
# Stream seed 7 at maximum speed (no real-time delay)
python -m simulator.publisher --seed 7 --home T01 --away T02 --speed max
```

Use `--dry-run` to print the first 3 messages without sending anything.

**Watch in the browser**

1. Open http://localhost:8000
2. Click **Live** to see the live match list.
3. Select the match; the watcher starts polling KQL.
4. Overlays appear as the simulator sends events through Fabric.

**Check API logs** for KQL timing:

```
DEBUG: events_since took 0.42s, got 12 rows
DEBUG: match_snapshot took 0.18s
```

### Teardown

- Stop the publisher (Ctrl-C).
- Stop the API server.
- If you don't need the streamed data: truncate the tables in the KQL queryset:

```kql
.clear table events data
.clear table snapshots data
```

---

## 6 — Cost reference

| Resource | SKU / tier | Cost model |
|----------|-----------|------------|
| Fabric capacity `plhackf2` | F2 | Per running hour — **pause when idle** |
| Azure Container Apps `whatif-fc` | Dedicated (1 replica) | Per vCPU-s and memory-s consumed |
| Blob storage `whatifreplay` | LRS Standard | Per GB stored + GET/PUT operations |
| Azure AI Foundry | Pay-as-you-go | Per token for `FOUNDRY_MODEL` calls |

Fabric F2 dominates cost. A full end-to-end demo session (resume, stream, view
overlays, pause) takes under 30 minutes of capacity time.

---

## 7 — CI deployment and OIDC identity

The GitHub Actions `deploy` job in `.github/workflows/ci.yml` updates the Container
App on every push to `main`. It authenticates with Azure using a **user-assigned
managed identity** (`id-whatif-deploy`, Contributor on `rg-pl-hackathon`) via OIDC.

> **OIDC subject — known gotcha**: the classic subject format
> `repo:aravindh-c/what-if-fc:ref:refs/heads/main` fails with **AADSTS700213** for
> this repository. GitHub issues tokens with numeric owner and repo IDs in the subject:
>
> ```
> repo:aravindh-c@61825537/what-if-fc@1423213635:ref:refs/heads/main
> ```
>
> The federated credential stored on `id-whatif-deploy` uses this ID-based subject.

For the full setup procedure (identity creation, role assignment, federated credential,
GitHub secrets) see **docs/deploy.md § 5**.
