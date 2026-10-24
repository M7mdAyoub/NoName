-- 0002 MVP data model (docs/MVP.md). One implicit project, no tenancy, no soft delete.

CREATE TABLE project (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  created_at  TEXT NOT NULL
) STRICT;
INSERT INTO project (id, name, created_at) VALUES ('default', 'Default project', '2026-01-01T00:00:00.000Z');

-- One upload = one or more files; `ir` holds the parsed intermediate representation of each file
CREATE TABLE framework_upload (
  id          TEXT PRIMARY KEY,
  files       TEXT NOT NULL CHECK (json_valid(files)),          -- [{"filename","path","size_bytes","sha256"}]
  status      TEXT NOT NULL CHECK (status IN ('uploaded','parsing','parsed','extracting','extracted','failed')),
  ir          TEXT CHECK (ir IS NULL OR json_valid(ir)),        -- {"files": [<IR per file>]}
  error       TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
) STRICT;

CREATE TABLE result (
  id          TEXT PRIMARY KEY,
  upload_id   TEXT REFERENCES framework_upload(id),
  parent_id   TEXT REFERENCES result(id),
  level_name  TEXT NOT NULL,                                    -- e.g. 'Impact', 'Outcome', 'Output'
  code        TEXT,
  statement   TEXT NOT NULL,
  sort_order  INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL
) STRICT;

CREATE TABLE indicator (
  id           TEXT PRIMARY KEY,
  result_id    TEXT REFERENCES result(id),
  code         TEXT,
  name         TEXT NOT NULL,
  unit         TEXT,
  kind         TEXT CHECK (kind IS NULL OR kind IN ('count','sum','average','ratio','milestone')),
  baseline     REAL,
  target       REAL,
  frequency    TEXT,
  data_source  TEXT,
  status       TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published')),
  created_at   TEXT NOT NULL
) STRICT;

CREATE TABLE form (
  id          TEXT PRIMARY KEY,
  key         TEXT NOT NULL UNIQUE,
  title       TEXT NOT NULL,
  schema      TEXT NOT NULL CHECK (json_valid(schema)),
  status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published')),
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
) STRICT;

CREATE TABLE indicator_definition (
  id            TEXT PRIMARY KEY,
  indicator_id  TEXT NOT NULL UNIQUE REFERENCES indicator(id),
  definition    TEXT NOT NULL CHECK (json_valid(definition)),
  status        TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved')),
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
) STRICT;

CREATE TABLE submission (
  id            TEXT PRIMARY KEY,
  form_id       TEXT NOT NULL REFERENCES form(id),
  data          TEXT NOT NULL CHECK (json_valid(data)),
  entity_key    TEXT,                                           -- who/what the record is about (distinct counts)
  collected_at  TEXT NOT NULL,
  created_at    TEXT NOT NULL
) STRICT;
CREATE INDEX ix_submission_form ON submission(form_id);

CREATE TABLE open_question (
  id            TEXT PRIMARY KEY,
  indicator_id  TEXT REFERENCES indicator(id),
  question      TEXT NOT NULL,
  answer        TEXT,
  created_at    TEXT NOT NULL
) STRICT;
