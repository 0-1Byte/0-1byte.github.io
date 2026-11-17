CREATE TABLE thoughts (
  id TEXT PRIMARY KEY NOT NULL,
  content TEXT NOT NULL
    CHECK (
      length(content) BETWEEN 1 AND 6000
      AND length(trim(content, ' ' || char(9) || char(10) || char(13))) > 0
    ),
  date TEXT NOT NULL
    CHECK (
      length(date) = 10
      AND substr(date, 1, 4) <> '0000'
      AND date(date, '+0 days') IS NOT NULL
      AND date(date, '+0 days') = date
    ),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX thoughts_date_created_at
  ON thoughts (date DESC, created_at DESC, id ASC);
