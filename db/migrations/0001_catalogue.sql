-- The dataset catalogue: one row per dataset, and one row per column of a dataset.

CREATE TABLE datasets (
    id               text PRIMARY KEY,
    title            text NOT NULL,
    description      text NOT NULL,
    owner            text NOT NULL,
    themes           text[] NOT NULL DEFAULT '{}',
    keywords         text[] NOT NULL DEFAULT '{}',
    license          text,
    update_frequency text,
    updated_at       timestamptz NOT NULL,
    records_count    integer NOT NULL,
    source_url       text NOT NULL
);

CREATE TABLE dataset_columns (
    dataset_id  text NOT NULL REFERENCES datasets (id) ON DELETE CASCADE,
    position    integer NOT NULL,
    name        text NOT NULL,
    label       text,
    data_type   text NOT NULL,
    description text,
    PRIMARY KEY (dataset_id, position)
);
