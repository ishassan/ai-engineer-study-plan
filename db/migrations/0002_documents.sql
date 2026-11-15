-- The documents of Phase 2: one row per document, and one row per chunk of text.
--
-- This file has no column for the embedding and no column for text search. You add them
-- with your own migration files in weeks 5 and 6, for example 0003_chunk_embeddings.sql.
-- `make up` applies each new file in this folder one time, in the order of the names.

CREATE TABLE documents (
    id        text PRIMARY KEY,          -- the id in data/documents.csv
    title     text NOT NULL,
    language  text NOT NULL CHECK (language IN ('ar', 'en')),
    publisher text NOT NULL,
    url       text NOT NULL,
    pages     integer NOT NULL
);

CREATE TABLE chunks (
    id          text PRIMARY KEY,        -- <document_id>:p<page>:c<n>, for example gastat-land-transport-en:p7:c2
    document_id text NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    language    text NOT NULL CHECK (language IN ('ar', 'en')),
    page        integer NOT NULL,        -- the first page of the document is page 1
    position    integer NOT NULL,        -- the n of the id: the first chunk of a page is 1
    text        text NOT NULL
);

CREATE INDEX chunks_document_id_idx ON chunks (document_id);
