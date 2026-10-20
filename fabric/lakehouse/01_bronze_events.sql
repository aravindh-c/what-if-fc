-- Run in a Fabric notebook (%%sql). Eventstream Lakehouse destinations only write Delta
-- protocol reader 1 / writer 2 (Microsoft Learn: Delta Lake table format interoperability).
-- Spark Runtime 2.0 defaults to 3/7 with table features, which the Eventstream rejects
-- ('Unsupported writer features: invariants'), so pin the protocol. event_time stays STRING
-- in bronze (raw, as received); parse it in gold.

DROP TABLE IF EXISTS bronze_events;

CREATE TABLE bronze_events (
    event_id     STRING,
    match_id     STRING,
    scenario_id  STRING,
    seed         INT,
    event_time   STRING,
    match_clock_s INT,
    period       INT,
    event_type   STRING,
    team_id      STRING,
    player_id    STRING,
    possession_id INT,
    x            DOUBLE,
    y            DOUBLE,
    end_x        DOUBLE,
    end_y        DOUBLE,
    outcome      STRING,
    receiver_id  STRING,
    pressure_level DOUBLE,
    snapshot_id  STRING
)
USING DELTA
TBLPROPERTIES (
    'delta.minReaderVersion' = '1',
    'delta.minWriterVersion' = '2'
);

DESCRIBE DETAIL bronze_events;
