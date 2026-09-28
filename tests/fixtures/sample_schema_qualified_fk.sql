-- drizzle-kit's generated shape: unqualified CREATE TABLE, default-schema-qualified FK.
CREATE TABLE "companies" (
  "id" uuid PRIMARY KEY
);

CREATE TABLE "children" (
  "id" uuid PRIMARY KEY,
  "company_id" uuid
);

ALTER TABLE "children" ADD CONSTRAINT "children_company_id_fk"
  FOREIGN KEY ("company_id") REFERENCES "public"."companies"("id");

-- A non-default schema must NOT bind to the bare definition.
CREATE TABLE "audit_log" (
  "id" uuid PRIMARY KEY,
  "company_id" uuid
);

ALTER TABLE "audit_log" ADD CONSTRAINT "audit_log_company_id_fk"
  FOREIGN KEY ("company_id") REFERENCES "archive"."companies"("id");
