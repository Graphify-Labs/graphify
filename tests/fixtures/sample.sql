CREATE TABLE organizations (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email TEXT NOT NULL,
  org_id INT REFERENCES organizations(id)
);

CREATE VIEW active_users AS
  SELECT * FROM users WHERE active = true;

CREATE FUNCTION get_user(user_id INT) RETURNS users AS $$
  BEGIN
    RETURN QUERY SELECT * FROM users WHERE id = user_id;
  END;
$$ LANGUAGE plpgsql;
