CREATE TABLE alfa (id integer PRIMARY KEY);

BEGIN;

CREATE TABLE gamma (id integer PRIMARY KEY);
CREATE TABLE delta (
  id integer PRIMARY KEY,
  alfa_id integer REFERENCES alfa(id)
);

COMMIT;
