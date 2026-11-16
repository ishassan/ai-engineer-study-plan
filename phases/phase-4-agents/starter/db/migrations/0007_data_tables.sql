-- Phase 4, week 16: the records of eight datasets of the catalogue, for the SQL server.
-- `make up` applies this file, and then scripts/load_tables.py loads data/tables/*.csv.
--
-- Source: the CSV export of each dataset on the KAPSARC open-data portal
-- (https://datasource.kapsarc.org), license "Public Domain". data/tables/sources.json gives
-- the dataset ID, the publisher and the URL of each export. A column of the type "date" on the
-- portal that holds only a year is an integer here.

CREATE SCHEMA data;

-- One row for each table of this schema: the dataset of the catalogue that it holds.
CREATE TABLE data.sources (
    table_name text PRIMARY KEY,
    dataset_id text NOT NULL UNIQUE,
    title text NOT NULL,
    publisher text,
    license text NOT NULL,
    source_url text NOT NULL,
    fetched_at timestamptz NOT NULL,
    records integer NOT NULL
);

-- cement-production-and-sales
CREATE TABLE data.cement (
    date integer NOT NULL,
    name text NOT NULL,
    value double precision
);

-- saudi-crude-oil-production-from-sama-annual-statistics-2015-dec
CREATE TABLE data.crude_oil_production (
    time_period integer NOT NULL,
    production_indicator text NOT NULL,
    value double precision,
    periodicity text,
    date_object date
);

-- electricity-consumption-by-sectors
CREATE TABLE data.electricity_consumption (
    year integer NOT NULL,
    region text NOT NULL,
    sector text NOT NULL,
    electricity_consumption_mwh double precision,
    name text,
    date_object date,
    periodicity text
);

-- gas-sales-by-region-2001-2013. geopoint is "latitude, longitude".
CREATE TABLE data.gas_sales (
    year integer NOT NULL,
    month text NOT NULL,
    city text NOT NULL,
    gas_sales_in_tons double precision,
    geopoint text
);

-- installed-generation-capacity-peak-load-in-mw-by-region-for-2014
CREATE TABLE data.generation_capacity (
    year integer NOT NULL,
    area text NOT NULL,
    indicator text NOT NULL,
    value_gw double precision
);

-- population-by-gender-age-nationality-saudinon-saudi
CREATE TABLE data.population (
    year_time integer NOT NULL,
    sex_engl text NOT NULL,
    nationality_engl text NOT NULL,
    obs_value_obsv bigint
);

-- per_capita_average_water_use_in_saudi_regions (the per capita average daily use of water)
CREATE TABLE data.water_use_per_capita (
    regions text NOT NULL,
    year integer NOT NULL,
    value integer
);

-- world-oil-production
CREATE TABLE data.world_oil_production (
    time_period integer NOT NULL,
    producers text NOT NULL,
    value double precision,
    date_object date,
    periodicity text
);
