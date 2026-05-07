-- =============================================================
-- Zeutec Central Data Infrastructure — SQLite schema
-- =============================================================
-- Run with: sqlite3 zeutec.db < schema_sqlite.sql
-- =============================================================

PRAGMA foreign_keys = ON;

-- -------------------------------------------------------------
-- IDENTITY LAYER
-- -------------------------------------------------------------

CREATE TABLE organization (
  organization_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  code             TEXT    UNIQUE NOT NULL,
  name             TEXT    NOT NULL,
  org_type         TEXT
);

CREATE TABLE farm_detail (
  farm_detail_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  organization_id INTEGER UNIQUE NOT NULL,
  address         TEXT,
  country         TEXT,
  lat             REAL,
  lon             REAL,
  size_ha         REAL,
  polygon_geojson TEXT,
  FOREIGN KEY (organization_id) REFERENCES organization(organization_id)
);

CREATE TABLE silo (
  silo_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  organization_id INTEGER NOT NULL,
  name            TEXT NOT NULL,
  lat             REAL NOT NULL,
  lon             REAL NOT NULL,
  capacity_tonnes REAL,
  material_id     INTEGER,
  FOREIGN KEY (organization_id) REFERENCES organization(organization_id),
  FOREIGN KEY (material_id) REFERENCES material(material_id)
);

CREATE TABLE org_material (
  organization_id INTEGER NOT NULL,
  material_id     INTEGER NOT NULL,
  PRIMARY KEY (organization_id, material_id),
  FOREIGN KEY (organization_id) REFERENCES organization(organization_id),
  FOREIGN KEY (material_id) REFERENCES material(material_id)
);

CREATE TABLE user_account (
  user_id          INTEGER PRIMARY KEY AUTOINCREMENT,
  organization_id  INTEGER NOT NULL,
  username         TEXT    UNIQUE NOT NULL,
  password_hash    TEXT    NOT NULL,
  password_salt    TEXT    NOT NULL,
  full_name        TEXT,
  role             TEXT,
  FOREIGN KEY (organization_id) REFERENCES organization(organization_id)
);

-- -------------------------------------------------------------
-- INSTRUMENT LAYER
-- -------------------------------------------------------------

CREATE TABLE instrument (
  instrument_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  organization_id  INTEGER NOT NULL,
  serial_number    TEXT    UNIQUE NOT NULL,
  model            TEXT,
  FOREIGN KEY (organization_id) REFERENCES organization(organization_id)
);

CREATE TABLE sensor_channel (
  sensor_channel_id INTEGER PRIMARY KEY AUTOINCREMENT,
  instrument_id     INTEGER NOT NULL,
  channel_index     INTEGER NOT NULL,
  label             TEXT,
  FOREIGN KEY (instrument_id) REFERENCES instrument(instrument_id)
);

-- -------------------------------------------------------------
-- SAMPLE LAYER
-- -------------------------------------------------------------

CREATE TABLE material (
  material_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  code         TEXT    UNIQUE NOT NULL,
  name         TEXT    NOT NULL,
  category     TEXT
);

CREATE TABLE sample (
  sample_id            INTEGER PRIMARY KEY AUTOINCREMENT,
  material_id          INTEGER,
  external_ref         TEXT    UNIQUE,
  batch_lot            TEXT,
  collected_by_user_id INTEGER,
  FOREIGN KEY (material_id)          REFERENCES material(material_id),
  FOREIGN KEY (collected_by_user_id) REFERENCES user_account(user_id)
);

-- -------------------------------------------------------------
-- CALIBRATION LAYER
-- -------------------------------------------------------------

CREATE TABLE method (
  method_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    UNIQUE NOT NULL,
  version    TEXT
);

CREATE TABLE calibration_model (
  calibration_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  method_id       INTEGER,
  name            TEXT    NOT NULL,
  version         TEXT,
  analyte         TEXT,
  FOREIGN KEY (method_id) REFERENCES method(method_id)
);

-- -------------------------------------------------------------
-- LEDGER / DATA LAYER
-- -------------------------------------------------------------

CREATE TABLE event_type (
  event_type_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  code           TEXT    UNIQUE NOT NULL,
  description    TEXT
);

CREATE TABLE event (
  event_id          INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type_id     INTEGER NOT NULL,
  organization_id   INTEGER NOT NULL,
  operator_user_id  INTEGER,
  instrument_id     INTEGER,
  method_id         INTEGER,
  sample_id         INTEGER,
  local_timestamp   TEXT    NOT NULL,
  global_timestamp  TEXT    NOT NULL,
  location_text     TEXT,
  previous_event_id INTEGER,
  visibility        TEXT    DEFAULT 'PRIVATE' CHECK (visibility IN ('PRIVATE','SHARED','PUBLIC')),
  FOREIGN KEY (event_type_id)     REFERENCES event_type(event_type_id),
  FOREIGN KEY (organization_id)   REFERENCES organization(organization_id),
  FOREIGN KEY (operator_user_id)  REFERENCES user_account(user_id),
  FOREIGN KEY (instrument_id)     REFERENCES instrument(instrument_id),
  FOREIGN KEY (method_id)         REFERENCES method(method_id),
  FOREIGN KEY (sample_id)         REFERENCES sample(sample_id),
  FOREIGN KEY (previous_event_id) REFERENCES event(event_id)
);

CREATE TABLE measurement_data (
  data_id           INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id          INTEGER NOT NULL,
  sensor_channel_id INTEGER,
  spectrum_uri      TEXT    NOT NULL,
  FOREIGN KEY (event_id)          REFERENCES event(event_id),
  FOREIGN KEY (sensor_channel_id) REFERENCES sensor_channel(sensor_channel_id)
);

CREATE TABLE measurement_image (
  image_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id   INTEGER NOT NULL,
  image_uri  TEXT    NOT NULL,
  format     TEXT,
  FOREIGN KEY (event_id) REFERENCES event(event_id)
);

CREATE TABLE result (
  result_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id        INTEGER NOT NULL,
  data_id         INTEGER,
  calibration_id  INTEGER,
  analyte         TEXT,
  value           REAL    NOT NULL,
  unit            TEXT,
  FOREIGN KEY (event_id)       REFERENCES event(event_id),
  FOREIGN KEY (data_id)        REFERENCES measurement_data(data_id),
  FOREIGN KEY (calibration_id) REFERENCES calibration_model(calibration_id)
);

CREATE TABLE soft_data (
  soft_data_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id            INTEGER NOT NULL,
  value_text          TEXT,
  recorded_by_user_id INTEGER,
  FOREIGN KEY (event_id)            REFERENCES event(event_id),
  FOREIGN KEY (recorded_by_user_id) REFERENCES user_account(user_id)
);

-- -------------------------------------------------------------
-- QUERY INDEXES
-- -------------------------------------------------------------

CREATE INDEX idx_event_org_visibility_timestamp
  ON event(organization_id, visibility, local_timestamp);

CREATE INDEX idx_event_previous_event
  ON event(previous_event_id);

CREATE INDEX idx_silo_organization
  ON silo(organization_id);

CREATE INDEX idx_farm_detail_organization
  ON farm_detail(organization_id);
