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
