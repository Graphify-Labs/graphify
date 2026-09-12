from __future__ import annotations
from pathlib import Path, PurePosixPath
from graphify.extract import extract_sql


def _quote_ident(name: str) -> str:
    """Double-quote a PostgreSQL identifier, escaping embedded double-quotes."""
    return '"' + name.replace('"', '""') + '"'


def introspect_postgres(dsn: str | None = None) -> dict:
    """Connect to PostgreSQL, reconstruct DDL, and extract via extract_sql()."""
    try:
        import psycopg
    except ModuleNotFoundError:
        raise ImportError(
            "psycopg is required for --postgres. "
            "Install with: pip install 'graphifyy[postgres]'"
        )

    try:
        conn = psycopg.connect(dsn or "")  # empty string = PG* env vars
    except psycopg.OperationalError as exc:
        # Sanitize: strip the DSN/credentials that psycopg may embed in the
        # OperationalError message (e.g. "connection to server … failed: …\nDETAIL: …")
        msg = str(exc).split("\n")[0]
        raise ConnectionError(f"could not connect to PostgreSQL: {msg}") from None

    try:
        conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE READ ONLY DEFERRABLE")

        # 1. Query tables
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_schema, table_name, table_type
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name;
            """)
            tables = cur.fetchall()

            # 2. Query views
            cur.execute("""
                SELECT table_schema, table_name, view_definition
                FROM information_schema.views
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name;
            """)
            views = cur.fetchall()

            # 3. Query routines (functions/procedures), including language
            cur.execute("""
                SELECT routine_schema, routine_name, routine_type,
                       routine_definition, external_language
                FROM information_schema.routines
                WHERE routine_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY routine_schema, routine_name;
            """)
            routines = cur.fetchall()

            # 4. Query foreign keys — grouped by constraint to handle composites.
            # Read pg_catalog.pg_constraint, NOT information_schema.referential_
            # constraints: that view only shows constraints where the current
            # user has WRITE access to the referencing table (owner or a
            # privilege other than SELECT), so a read-only introspection role
            # sees zero FK rows while tables/views/routines all appear — the
            # graph then silently loses every 'references' edge (#1746).
            # pg_constraint is not privilege-filtered. It also keys constraints
            # by oid rather than by name (constraint names are only unique per
            # table, so the old name-based key_column_usage joins could
            # cross-match same-named constraints on sibling tables).
            cur.execute("""
                SELECT
                    con.conname AS constraint_name,
                    ns.nspname AS table_schema,
                    rel.relname AS table_name,
                    (SELECT ARRAY_AGG(att.attname ORDER BY k.ord)
                       FROM UNNEST(con.conkey) WITH ORDINALITY AS k(attnum, ord)
                       JOIN pg_catalog.pg_attribute att
                         ON att.attrelid = con.conrelid AND att.attnum = k.attnum
                    ) AS columns,
                    fns.nspname AS foreign_table_schema,
                    frel.relname AS foreign_table_name,
                    (SELECT ARRAY_AGG(att.attname ORDER BY k.ord)
                       FROM UNNEST(con.confkey) WITH ORDINALITY AS k(attnum, ord)
                       JOIN pg_catalog.pg_attribute att
                         ON att.attrelid = con.confrelid AND att.attnum = k.attnum
                    ) AS foreign_columns
                FROM pg_catalog.pg_constraint con
                JOIN pg_catalog.pg_class rel ON rel.oid = con.conrelid
                JOIN pg_catalog.pg_namespace ns ON ns.oid = rel.relnamespace
                JOIN pg_catalog.pg_class frel ON frel.oid = con.confrelid
                JOIN pg_catalog.pg_namespace fns ON fns.oid = frel.relnamespace
                WHERE con.contype = 'f'
                  AND ns.nspname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY ns.nspname, rel.relname, con.conname;
            """)
            fks = cur.fetchall()

            # 5. Query row-level-security policies. There is no
            # information_schema view for these, and pg_policies (the
            # human-readable one) filters rows the current role cannot see, so
            # read pg_catalog.pg_policy directly — same reasoning as the FK
            # query above. Policies are the access-control layer of an RLS
            # schema; without them the graph shows the tables but nothing about
            # who may read a row (#3401).
            cur.execute("""
                SELECT ns.nspname AS table_schema,
                       rel.relname AS table_name,
                       pol.polname AS policy_name
                FROM pg_catalog.pg_policy pol
                JOIN pg_catalog.pg_class rel ON rel.oid = pol.polrelid
                JOIN pg_catalog.pg_namespace ns ON ns.oid = rel.relnamespace
                WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY ns.nspname, rel.relname, pol.polname;
            """)
            policies = cur.fetchall()
    finally:
        conn.close()

    ddl = []

    # Tables — quote identifiers to handle reserved words, hyphens, mixed-case
    for schema, name, ttype in tables:
        if ttype == "BASE TABLE":
            ddl.append(f"CREATE TABLE {_quote_ident(schema)}.{_quote_ident(name)} (id INT);")

    # Views — real body if available, stub if NULL (permission denied)
    for schema, name, body in views:
        if body:
            ddl.append(f"CREATE VIEW {_quote_ident(schema)}.{_quote_ident(name)} AS {body};")
        else:
            ddl.append(f"CREATE VIEW {_quote_ident(schema)}.{_quote_ident(name)} AS SELECT 1;")

    # FK edges — one ALTER TABLE per constraint (handles composite FKs correctly).
    # Emitted BEFORE the function DDL: routine bodies the grammar can't parse
    # (notably C-language extension functions, whose "body" is just the C symbol
    # name) put tree-sitter into error recovery that consumes the statements
    # after them — with FKs last, every 'references' edge is silently lost on
    # any DB with a common extension installed (#1854). FK statements only
    # reference tables, which are emitted first, so this order is always safe.
    for constraint_name, t_schema, t_name, cols, r_schema, r_name, r_cols in fks:
        col_list = ", ".join(_quote_ident(c) for c in cols)
        ref_col_list = ", ".join(_quote_ident(c) for c in r_cols)
        ddl.append(
            f"ALTER TABLE {_quote_ident(t_schema)}.{_quote_ident(t_name)} "
            f"ADD CONSTRAINT {_quote_ident(constraint_name)} "
            f"FOREIGN KEY ({col_list}) REFERENCES {_quote_ident(r_schema)}.{_quote_ident(r_name)}({ref_col_list});"
        )

    # Functions & Procedures — real body if available, stub if NULL
    # Use $gfx$ as the dollar-quote tag to avoid collision with $$ inside bodies.
    # Use external_language from the catalog; fall back to plpgsql if NULL/blank.
    for schema, name, rtype, body, ext_lang in routines:
        lang = (ext_lang or "plpgsql").lower()
        fn_sig = f"{_quote_ident(schema)}.{_quote_ident(name)}()"
        stub_body = "BEGIN SELECT 1; END;"
        if rtype in ("FUNCTION", "PROCEDURE"):
            actual_body = body if body else stub_body
            # Represent PROCEDUREs as FUNCTION so tree-sitter-sql can parse them
            ddl.append(
                f"CREATE FUNCTION {fn_sig} RETURNS void"
                f" AS $gfx$ {actual_body} $gfx$ LANGUAGE {lang};"
            )

    # RLS policies — emitted LAST, for the mirror image of the reason the FKs are
    # emitted first. tree-sitter-sql has no rule for CREATE POLICY at all, so each
    # of these statements shreds into an ERROR node that consumes the statements
    # following it; anything after them would be lost from the AST. They survive
    # being last because the SQL extractor recovers policies by regex over the
    # whole file rather than from the tree (see _POLICY_RECOVERY_RX), which is
    # also why no body/USING clause is reconstructed here: only the name and the
    # table it guards are read, and both fit in the header.
    for p_schema, p_table, p_name in policies:
        ddl.append(
            f"CREATE POLICY {_quote_ident(p_name)} "
            f"ON {_quote_ident(p_schema)}.{_quote_ident(p_table)};"
        )

    ddl_string = "\n".join(ddl)

    # Determine host/dbname for virtual path DSN sanitization
    info = psycopg.conninfo.conninfo_to_dict(dsn or "")
    host = info.get("host", "localhost")
    dbname = info.get("dbname", "db")
    virtual_path = PurePosixPath(f"postgresql://{host}/{dbname}")

    # Pass virtual path and in-memory DDL content to extract_sql
    result = extract_sql(virtual_path, content=ddl_string)
    # extract_sql() reports a missing grammar as an 'error' key with empty
    # nodes/edges; surface it instead of letting the CLI print
    # "PostgreSQL: 0 nodes" as if the database were empty.
    if result.get("error"):
        raise ImportError(
            f"{result['error']} (required by --postgres; "
            "install with: pip install 'graphifyy[postgres]')"
        )
    return result