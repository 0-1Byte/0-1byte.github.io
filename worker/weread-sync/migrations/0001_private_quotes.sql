CREATE TABLE IF NOT EXISTS weread_uploads (
  upload_id TEXT PRIMARY KEY,
  expected_records INTEGER NOT NULL,
  expected_chunks INTEGER NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('receiving', 'complete', 'aborted')),
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS weread_upload_chunks (
  upload_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  record_count INTEGER NOT NULL,
  PRIMARY KEY (upload_id, chunk_index),
  FOREIGN KEY (upload_id) REFERENCES weread_uploads(upload_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS weread_datasets (
  dataset_id TEXT PRIMARY KEY,
  record_count INTEGER NOT NULL,
  activated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS weread_quotes (
  dataset_id TEXT NOT NULL,
  quote_key TEXT NOT NULL,
  text TEXT NOT NULL,
  source TEXT NOT NULL,
  author TEXT NOT NULL,
  chapter TEXT NOT NULL,
  private_json TEXT NOT NULL,
  PRIMARY KEY (dataset_id, quote_key),
  FOREIGN KEY (dataset_id) REFERENCES weread_datasets(dataset_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS weread_quotes_dataset_idx
  ON weread_quotes(dataset_id);

CREATE TABLE IF NOT EXISTS weread_active_dataset (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  dataset_id TEXT NOT NULL
);
