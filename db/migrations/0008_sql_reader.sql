-- Reference solution: the read-only role of the SQL server.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'assistant_reader') THEN
        CREATE ROLE assistant_reader LOGIN PASSWORD 'assistant_reader';
    END IF;
END $$;

ALTER ROLE assistant_reader SET default_transaction_read_only = on;
GRANT USAGE ON SCHEMA data TO assistant_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA data TO assistant_reader;
GRANT SELECT ON datasets, dataset_columns TO assistant_reader;
