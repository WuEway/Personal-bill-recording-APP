export const SCHEMA_SQL = `
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS accounts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  type        TEXT NOT NULL,
  name        TEXT NOT NULL,
  institution TEXT,
  last_4      TEXT,
  is_credit   INTEGER NOT NULL DEFAULT 0,
  is_active   INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(type, COALESCE(last_4,''), COALESCE(institution,''))
);

CREATE TABLE IF NOT EXISTS imported_files (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  source       TEXT NOT NULL,
  file_path    TEXT NOT NULL,
  file_hash    TEXT NOT NULL UNIQUE,
  file_format  TEXT NOT NULL,
  is_encrypted INTEGER NOT NULL DEFAULT 0,
  period_start TEXT,
  period_end   TEXT,
  row_count    INTEGER NOT NULL DEFAULT 0,
  imported_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS raw_transactions (
  id                   INTEGER PRIMARY KEY AUTOINCREMENT,
  source               TEXT NOT NULL,
  source_file_id       INTEGER NOT NULL,
  txn_time             TEXT NOT NULL,
  amount_cents         INTEGER NOT NULL,
  currency             TEXT NOT NULL DEFAULT 'CNY',
  counterparty         TEXT,
  description          TEXT,
  payment_account_id   INTEGER,
  txn_type_raw         TEXT,
  direction            TEXT NOT NULL,
  external_txn_id      TEXT,
  external_merchant_id TEXT,
  raw_json             TEXT NOT NULL DEFAULT '{}',
  imported_at          TEXT NOT NULL DEFAULT (datetime('now')),
  is_internal_transfer INTEGER NOT NULL DEFAULT 0,
  transfer_reason      TEXT,
  is_group_payment     INTEGER NOT NULL DEFAULT 0,
  is_refund            INTEGER NOT NULL DEFAULT 0,
  UNIQUE(source, external_txn_id),
  FOREIGN KEY (source_file_id) REFERENCES imported_files(id),
  FOREIGN KEY (payment_account_id) REFERENCES accounts(id)
);

CREATE INDEX IF NOT EXISTS idx_raw_time   ON raw_transactions(txn_time);
CREATE INDEX IF NOT EXISTS idx_raw_source ON raw_transactions(source);
CREATE INDEX IF NOT EXISTS idx_raw_amount ON raw_transactions(amount_cents);

CREATE TABLE IF NOT EXISTS manual_categories (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  name                  TEXT NOT NULL UNIQUE,
  icon                  TEXT NOT NULL DEFAULT '',
  monthly_budget_cents  INTEGER,
  yearly_budget_cents   INTEGER,
  is_active             INTEGER NOT NULL DEFAULT 1,
  created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  primary_raw_id     INTEGER NOT NULL,
  txn_time           TEXT NOT NULL,
  amount_cents       INTEGER NOT NULL,
  counterparty       TEXT,
  description        TEXT,
  payment_account_id INTEGER,
  direction          TEXT NOT NULL,
  is_group_payment   INTEGER NOT NULL DEFAULT 0,
  inclusion          TEXT NOT NULL DEFAULT 'auto',
  inclusion_set_at   TEXT,
  inclusion_note     TEXT,
  manual_category_id INTEGER,
  notes              TEXT,
  FOREIGN KEY (primary_raw_id) REFERENCES raw_transactions(id),
  FOREIGN KEY (payment_account_id) REFERENCES accounts(id),
  FOREIGN KEY (manual_category_id) REFERENCES manual_categories(id)
);

CREATE INDEX IF NOT EXISTS idx_txn_time      ON transactions(txn_time);
CREATE INDEX IF NOT EXISTS idx_txn_direction ON transactions(direction);
CREATE INDEX IF NOT EXISTS idx_txn_inclusion ON transactions(inclusion);

CREATE TABLE IF NOT EXISTS dedup_links (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_txn_id INTEGER NOT NULL,
  raw_txn_id       INTEGER NOT NULL,
  match_confidence REAL NOT NULL,
  match_reason     TEXT NOT NULL,
  match_method     TEXT NOT NULL,
  created_at       TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (canonical_txn_id) REFERENCES transactions(id),
  FOREIGN KEY (raw_txn_id) REFERENCES raw_transactions(id),
  UNIQUE(raw_txn_id)
);

CREATE TABLE IF NOT EXISTS manual_entries (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id   INTEGER NOT NULL,
  txn_time      TEXT NOT NULL,
  amount_cents  INTEGER NOT NULL,
  description   TEXT,
  linked_txn_id INTEGER,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (category_id) REFERENCES manual_categories(id),
  FOREIGN KEY (linked_txn_id) REFERENCES transactions(id)
);

CREATE TABLE IF NOT EXISTS app_config (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT OR IGNORE INTO app_config(key, value) VALUES ('schema_version', '2');
INSERT OR IGNORE INTO app_config(key, value) VALUES ('onboarded', '0');
`;
