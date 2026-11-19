-- Reference solution: row security for the data tables, the
-- documents and the chunks, with the rules of access_rules (migration 0009).
--
-- The database session carries the user: the code sets app.user (the preferred_username of the
-- token) and app.groups (the groups, separated by commas) with SET LOCAL before each query.
-- The owner of the tables (assistant) is a superuser, so row security does not apply to it: the
-- loaders and the ingest still see each row. The queries of users run as a role without these
-- rights: the SQL server as assistant_reader, the document search as assistant_retrieval.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'assistant_retrieval') THEN
        CREATE ROLE assistant_retrieval NOLOGIN;
    END IF;
END $$;
GRANT SELECT ON documents, chunks TO assistant_retrieval;

-- The principals of the session: 'user:<name>' and 'group:<name>' for each group.
CREATE OR REPLACE FUNCTION app_principals() RETURNS text[]
LANGUAGE sql STABLE AS $$
    SELECT array_append(
        ARRAY(SELECT 'group:' || btrim(name)
              FROM unnest(string_to_array(coalesce(current_setting('app.groups', true), ''), ',')) AS name
              WHERE btrim(name) <> ''),
        'user:' || coalesce(nullif(current_setting('app.user', true), ''), '-'))
$$;

-- True when the session may read the object: no rule for it, or a rule for a principal of the
-- session. SECURITY DEFINER: the roles of the users do not need to read access_rules.
CREATE OR REPLACE FUNCTION app_may_read(kind text, object text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT NOT EXISTS (SELECT 1 FROM access_rules WHERE object_kind = kind AND object_id = object)
        OR EXISTS (SELECT 1 FROM access_rules
                   WHERE object_kind = kind AND object_id = object AND principal = ANY (app_principals()))
$$;

-- The same for a table of the schema `data`: data.sources gives the dataset of the table.
CREATE OR REPLACE FUNCTION app_may_read_table(name text) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
    SELECT coalesce((SELECT app_may_read('dataset', dataset_id) FROM data.sources WHERE table_name = name), true)
$$;

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS read_permitted ON documents;
CREATE POLICY read_permitted ON documents FOR SELECT USING (app_may_read('document', id));

ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS read_permitted ON chunks;
CREATE POLICY read_permitted ON chunks FOR SELECT USING (app_may_read('document', document_id));

-- One policy for each table of the schema `data` (not data.sources, the list of the tables).
DO $$
DECLARE
    item record;
BEGIN
    FOR item IN SELECT tablename FROM pg_tables WHERE schemaname = 'data' AND tablename <> 'sources' LOOP
        EXECUTE format('ALTER TABLE data.%I ENABLE ROW LEVEL SECURITY', item.tablename);
        EXECUTE format('DROP POLICY IF EXISTS read_permitted ON data.%I', item.tablename);
        EXECUTE format('CREATE POLICY read_permitted ON data.%I FOR SELECT USING (app_may_read_table(%L))',
                       item.tablename, item.tablename);
    END LOOP;
END $$;

-- A query that the model wrote must not change the settings that carry the user. Each role
-- may call set_config() by default; the code uses SET LOCAL, which needs no such right, and
-- the SQL server refuses each statement that is not a query.
REVOKE EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) FROM PUBLIC;
