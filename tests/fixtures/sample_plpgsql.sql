CREATE TABLE accounts (
    id INT PRIMARY KEY,
    name TEXT
);

CREATE FUNCTION exposed.important_function(a int, OUT fuzz text) LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1;
    fuzz := 'x';
END
$$;

CREATE OR REPLACE FUNCTION tagged_quote_fn(n int) RETURNS int LANGUAGE plpgsql AS $fn$
DECLARE
    total int := 0;
BEGIN
    total := total + n;
    RETURN total;
END
$fn$;

CREATE FUNCTION plain_sql_fn() RETURNS int LANGUAGE sql AS 'SELECT 1';

CREATE TABLE audit_log (
    id INT PRIMARY KEY,
    account_id INT REFERENCES accounts
);
