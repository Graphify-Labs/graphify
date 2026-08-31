-- Generated-style PostgreSQL DDL (#2180): every identifier is double-quoted and
-- each body uses a PL/pgSQL-only statement, so tree-sitter-sql parses these as
-- ERROR nodes. Name recovery is the only path that can see them, and a bare
-- [\w$.]+ name pattern stops at the leading quote -- which silently dropped
-- every routine in files shaped like this.

CREATE TABLE "public"."accounts" (
    "id" INT PRIMARY KEY,
    "name" TEXT
);

CREATE OR REPLACE FUNCTION "public"."raise_exception_fn"("p_id" "uuid") RETURNS "void"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
BEGIN
  RAISE EXCEPTION 'insufficient_privilege' USING ERRCODE = '42501';
END;
$$;

CREATE OR REPLACE FUNCTION "public"."raise_notice_fn"() RETURNS "void" LANGUAGE "plpgsql" AS $$
BEGIN
  RAISE NOTICE 'hi';
END;
$$;

CREATE OR REPLACE FUNCTION "public"."perform_fn"() RETURNS "void" LANGUAGE "plpgsql" AS $$
BEGIN
  PERFORM "public"."raise_notice_fn"();
END;
$$;

CREATE OR REPLACE FUNCTION "public"."assign_fn"() RETURNS "void" LANGUAGE "plpgsql" AS $$
DECLARE
  "x" int;
BEGIN
  x := 1;
END;
$$;

CREATE OR REPLACE FUNCTION "public"."if_then_fn"() RETURNS "void" LANGUAGE "plpgsql" AS $$
BEGIN
  IF true THEN RAISE EXCEPTION 'x'; END IF;
END;
$$;

CREATE OR REPLACE FUNCTION "public"."null_body_fn"() RETURNS "void" LANGUAGE "plpgsql" AS $$
BEGIN
  NULL;
END;
$$;

CREATE PROCEDURE "public"."quoted_proc"() LANGUAGE "plpgsql" AS $$
BEGIN
  PERFORM 1;
END;
$$;

CREATE TABLE "public"."audit_log" (
    "id" INT PRIMARY KEY,
    "account_id" INT REFERENCES "public"."accounts"
);
