-- An explicit public.x definition must win over the bare alias.
CREATE TABLE "public"."accounts" (
  "id" uuid PRIMARY KEY
);

CREATE TABLE "accounts_mirror" (
  "id" uuid PRIMARY KEY,
  "account_id" uuid
);

ALTER TABLE "accounts_mirror" ADD CONSTRAINT "accounts_mirror_account_id_fk"
  FOREIGN KEY ("account_id") REFERENCES "public"."accounts"("id");
