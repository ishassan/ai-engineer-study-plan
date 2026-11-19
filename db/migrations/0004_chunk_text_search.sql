-- Reference solution, week 6: the text-search form of each chunk, in the configuration of its language.

ALTER TABLE chunks ADD COLUMN tsv tsvector GENERATED ALWAYS AS (
    CASE WHEN language = 'ar' THEN to_tsvector('arabic', text) ELSE to_tsvector('english', text) END
) STORED;

CREATE INDEX chunks_tsv_gin_idx ON chunks USING gin (tsv);
