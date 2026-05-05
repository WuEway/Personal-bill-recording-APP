import * as SQLite from 'expo-sqlite';
import { SCHEMA_SQL } from './schema';

let _db: SQLite.SQLiteDatabase | null = null;

export function getDb(): SQLite.SQLiteDatabase {
  if (!_db) throw new Error('Database not initialized. Call initDb() first.');
  return _db;
}

export async function initDb(): Promise<void> {
  if (_db) return;
  _db = await SQLite.openDatabaseAsync('mz.db');
  await _db.execAsync(SCHEMA_SQL);
}

// ── Generic helpers ──────────────────────────────────────────────────────────

export async function dbRun(sql: string, params: unknown[] = []): Promise<SQLite.SQLiteRunResult> {
  return getDb().runAsync(sql, params as SQLite.SQLiteBindValue[]);
}

export async function dbGet<T>(sql: string, params: unknown[] = []): Promise<T | null> {
  return getDb().getFirstAsync<T>(sql, params as SQLite.SQLiteBindValue[]);
}

export async function dbAll<T>(sql: string, params: unknown[] = []): Promise<T[]> {
  return getDb().getAllAsync<T>(sql, params as SQLite.SQLiteBindValue[]);
}

export async function getConfig(key: string): Promise<string | null> {
  const row = await dbGet<{ value: string }>('SELECT value FROM app_config WHERE key=?', [key]);
  return row?.value ?? null;
}

export async function setConfig(key: string, value: string): Promise<void> {
  await dbRun('INSERT OR REPLACE INTO app_config(key, value) VALUES(?,?)', [key, value]);
}
