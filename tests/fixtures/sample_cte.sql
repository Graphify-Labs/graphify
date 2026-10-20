CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  role TEXT NOT NULL
);

CREATE VIEW v_roles AS
  WITH levels AS (SELECT 'admin' AS role)
  SELECT * FROM users JOIN levels ON levels.role = users.role;
