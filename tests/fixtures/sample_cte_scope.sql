CREATE TABLE orders (
  id SERIAL PRIMARY KEY,
  total NUMERIC NOT NULL
);

-- A SQL-standard function body (Postgres 14+) holds sibling statements under one
-- node. `orders` is a CTE in the first one and the real table in the second.
CREATE FUNCTION f_orders() RETURNS int LANGUAGE sql BEGIN ATOMIC
  WITH orders AS (SELECT 1 AS id) SELECT id FROM orders;
  SELECT id FROM orders;
END;

-- A CTE body sees the CTEs declared beside it, so `a` is not a table here.
CREATE VIEW v_chain AS
  WITH a AS (SELECT 1 AS id),
       b AS (SELECT id FROM a)
  SELECT id FROM b;
