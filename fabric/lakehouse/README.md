# Lakehouse: bronze → silver → gold

The live path (Eventstream → Eventhouse → app) answers "what is happening now". This batch path answers "what happened in every match", for reporting and history.

```text
Eventstream dst-bronz ─► dbo.bronze_events (raw, as received)
                              │
              pipeline pl-whatif-gold ─► notebook nb-silver-gold
                              │
                              ├─► silver.events            deduplicated, typed, validated
                              ├─► gold.match_summary       one row per match
                              ├─► gold.match_team_stats    one row per match and team
                              ├─► gold.player_match_stats  one row per match and player
                              └─► gold.pipeline_runs       one row per run (data quality)
```

| File | Purpose |
| --- | --- |
| `01_bronze_events.sql` | Creates the bronze table with Delta protocol 1/2 (run once, before activating `dst-bronz`) |
| `02_silver_gold.ipynb` | The notebook the pipeline runs |

## Rules the notebook applies

- **Reject** rows with no `event_id`, no `match_id`, no `match_clock_s`, an unknown `event_type`, or no `team_id` (except `period_end`). The count goes to `gold.pipeline_runs.rejected_rows`.
- **Deduplicate** on `(match_id, event_id)`, the same key as KQL `EventsClean()`. The count goes to `duplicate_rows`.
- **Type** `event_time` (a string in bronze) as a timestamp `event_ts`.
- **Same definitions as live:** passes, completed passes, completion %, shots, goals and possession proxy % follow KQL `MatchStats()` and `analytics.metrics.match_stats()`, so the batch numbers equal the live numbers.
- **Idempotent:** every run rebuilds silver and gold from bronze, so rerunning is safe.

## One-time setup in Fabric

1. **Import the notebook.** Workspace `pl-hackathon` → **Import** → **Notebook** → **From this computer** → `02_silver_gold.ipynb`. Rename it `nb-silver-gold`.
2. **Attach the Lakehouse.** Open the notebook → **Lakehouse** pane on the left → **Add** → existing `whatif_lh`, and set it as the default.
3. **Check the parameter cell.** The cell with `p_run_id = "manual"` must be marked as the parameter cell. If it is not, open the cell's **…** menu → **Toggle parameter cell**.
4. **Test run.** **Run all**. It should print the data-quality counts and the row counts, then show the match tables. Then **Stop session**, because F2 has room for only one Spark session.
5. **Create the pipeline.** Workspace → **New item** → **Pipeline** → name `pl-whatif-gold`.
   - Add a **Notebook** activity, name it `Build silver and gold`.
   - **Settings**: Notebook = `nb-silver-gold`. Under **Base parameters**, set `p_run_id` (String) to the dynamic content `@pipeline().RunId`.
   - **General**: Retry = `1`, Retry interval = `60` s, Timeout = `0.00:30:00`.
   - **Save**, then **Run**. Watch it on the **Output** tab.
6. **Schedule it.** **Schedule** → daily, at a time when no match is streaming. Turn the schedule off whenever the capacity is paused.

## Check the result

Run against the `whatif_lh` **SQL analytics endpoint**:

```sql
SELECT * FROM gold.match_summary ORDER BY match_id;
SELECT * FROM gold.match_team_stats ORDER BY match_id, team_id;
SELECT TOP 5 * FROM gold.pipeline_runs ORDER BY processed_at DESC;
```

Then, in the Eventhouse, run `MatchStats("match_s7_T01_T02")`. The passes, completed passes, completion %, shots, goals and possession proxy % must be equal to `gold.match_team_stats` for that match.

## Notes

- Run the pipeline after a match has finished streaming. F2 fits one Spark session at a time, and the Eventstream needs room to write to the Lakehouse.
- At scale, the full rebuild would become an incremental `MERGE` on `(match_id, event_id)`, processing only new bronze rows since the last run.
