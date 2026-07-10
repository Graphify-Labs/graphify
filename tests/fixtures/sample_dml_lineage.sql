-- ETL-style DML lineage fixture (#1572)
CREATE TABLE raw_events (id INT, user_id INT, amount INT);
CREATE TABLE dim_users (id INT, name TEXT);

-- INSERT ... SELECT with a JOIN: fct_daily reads from raw_events and dim_users
INSERT INTO fct_daily (user_id, name, total)
SELECT e.user_id, u.name, SUM(e.amount)
FROM raw_events e
JOIN dim_users u ON u.id = e.user_id
GROUP BY e.user_id, u.name;

-- CTAS: agg_monthly reads from fct_daily
CREATE TABLE agg_monthly AS
SELECT user_id, SUM(total) AS total
FROM fct_daily
GROUP BY user_id;

-- MERGE: dim_users reads from staging_users
MERGE INTO dim_users d
USING staging_users s ON d.id = s.id
WHEN MATCHED THEN UPDATE SET name = s.name;

-- UPDATE ... FROM: fct_daily reads from dim_users
UPDATE fct_daily SET name = u.name
FROM dim_users u
WHERE fct_daily.user_id = u.id;

-- plain VALUES insert: audit_log node exists, but no reads_from edge
INSERT INTO audit_log (msg) VALUES ('refreshed');

-- self-referential backfill: no self-loop edge
INSERT INTO raw_events SELECT * FROM raw_events WHERE id > 100;
