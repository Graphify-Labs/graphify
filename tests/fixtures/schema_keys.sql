CREATE TABLE customers (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  name TEXT
);

CREATE TABLE orders (
  id INT,
  customer_id INT NOT NULL,
  org_id INT,
  slug VARCHAR(64),
  total NUMERIC(10,2),
  PRIMARY KEY (id),
  UNIQUE (org_id, slug)
);
