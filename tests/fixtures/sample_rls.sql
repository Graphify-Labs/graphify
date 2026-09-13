-- Row-level security: two tables that share a policy name, plus a quoted,
-- schema-qualified table. tree-sitter-sql has no CREATE POLICY rule, so the
-- whole file parses into ERROR nodes.
CREATE TABLE tenants (id integer PRIMARY KEY);
CREATE TABLE invoices (id integer PRIMARY KEY, tenant_id integer REFERENCES tenants);

ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoices ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenants
  FOR SELECT USING (id = current_tenant());

CREATE POLICY tenant_isolation ON invoices
  FOR ALL USING (tenant_id = current_tenant())
  WITH CHECK (tenant_id = current_tenant());

CREATE POLICY invoices_admin_write ON "public"."invoices"
  FOR UPDATE USING (true);

-- Commented-out DDL must not become a node.
-- CREATE POLICY commented_out ON tenants FOR SELECT USING (true);
