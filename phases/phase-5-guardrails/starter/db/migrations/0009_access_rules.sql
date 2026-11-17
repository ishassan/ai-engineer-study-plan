-- Phase 5, week 19: who may read which dataset and which document.
--
-- One row gives one principal the right to read one object. A principal is a user
-- ('user:<name>', the preferred_username of the token) or a group ('group:<name>', an item of
-- the claim `groups` of the token). The rule:
--
--   - an object without a row may be read by every user,
--   - an object with rows may be read only by the principals of its rows.
--
-- A dataset is a row of datasets (id). The rows of its table in the schema `data` belong to
-- it: data.sources gives the table of each dataset. A document is a row of documents (id), and
-- its chunks belong to it.
--
-- This file only stores the rules. Your migration of week 19 makes Postgres apply them with row
-- security policies, for the tables of the schema `data`, for documents and for chunks.

CREATE TABLE access_rules (
    object_kind text NOT NULL CHECK (object_kind IN ('dataset', 'document')),
    object_id   text NOT NULL,
    principal   text NOT NULL CHECK (principal ~ '^(user|group):.+$'),
    PRIMARY KEY (object_kind, object_id, principal)
);

-- The rules of the lab. The test users of keycloak/realm-lab.json: viewer (no group), analyst
-- (group analysts), auditor (group auditors).
INSERT INTO access_rules (object_kind, object_id, principal) VALUES
    ('dataset', 'population-by-gender-age-nationality-saudinon-saudi', 'group:analysts'),
    ('document', 'gastat-business-confidence-en', 'group:auditors'),
    ('document', 'gastat-business-confidence-ar', 'group:auditors');
