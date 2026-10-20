# fabric

- `eventstream/` - custom endpoint setup notes (Day 3)
- `kql/` - Eventhouse tables, live metrics, key-moment queries (Days 3-4)
- `lakehouse/` - bronze/gold notebook and Data Factory pipeline export (Days 5, 9)

Fabric F2 is billed per running hour: pause the capacity when not in use.

## Day 3 setup

**Eventhouse:** `whatif` (region: UK South)
**KQL database:** `whatif`
**Eventstream:** `whatif-es`

| Component | Name | Notes |
| --- | --- | --- |
| Custom endpoint source | `src-simulator` | Event Hub-compatible; connection string in `.env` as `EVENTSTREAM_CONNECTION_STRING` |
| Destination | `dst-events` | Table `events` in database `whatif`; format JSON |
| Table | `events` | Schema created by the destination on first message |

### Streaming a match

```bash
python -m simulator.publisher --seed 7 --home T01 --away T02 --speed max
```

Use `--dry-run` to print the first 3 messages without connecting.

### After each session

Pause capacity **plhackf2** in the Fabric portal to avoid unnecessary charges.

## Day 5 setup

**Lakehouse:** `whatif_lh` (schemas enabled; table `dbo.bronze_events`)

### Eventstream destination

| Field | Value |
| --- | --- |
| Destination name | `dst-bronz` |
| Type | Lakehouse |
| Lakehouse | `whatif_lh` |
| Table | `bronze_events` |
| Input format | JSON |
| Batch size | 100 000 rows or 60 s (whichever comes first) |

The destination only targets Delta reader 1 / writer 2. Run
`fabric/lakehouse/01_bronze_events.sql` in a Fabric notebook (cell magic `%%sql`)
**before** activating the destination to pin the protocol; otherwise the Eventstream
rejects the table with `Unsupported writer features: invariants`.

### Verification (SQL analytics endpoint)

```sql
-- Run against the whatif_lh SQL analytics endpoint (not in a Spark notebook)
SELECT TOP 10 *
FROM dbo.bronze_events
ORDER BY match_clock_s DESC;
```

### Tips

- Use the **SQL analytics endpoint** for ad-hoc checks; F2 fits only one Spark session
  at a time, so running a notebook blocks the Eventstream writer.
- Stop notebook sessions after use (**Stop session** in the notebook toolbar) to free
  the Spark slot for the Eventstream destination.
