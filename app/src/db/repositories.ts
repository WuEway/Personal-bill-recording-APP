import { dbAll, dbGet, dbRun } from './database';
import type {
  Account, AccountType, ImportedFile, ManualCategory, ManualEntry,
  RawTransaction, RawTransactionDraft, Transaction, InclusionState,
} from '../models';

// ── Accounts ─────────────────────────────────────────────────────────────────

export async function getOrCreateAccount(
  type: AccountType,
  name: string,
  institution?: string,
  last4?: string,
  isCredit = false,
): Promise<Account> {
  const existing = await dbGet<{ id: number; type: string; name: string; institution: string; last_4: string; is_credit: number }>(
    `SELECT * FROM accounts WHERE type=? AND COALESCE(last_4,'')=? AND COALESCE(institution,'')=?`,
    [type, last4 ?? '', institution ?? ''],
  );
  if (existing) return rowToAccount(existing);

  const res = await dbRun(
    'INSERT INTO accounts(type, name, institution, last_4, is_credit) VALUES(?,?,?,?,?)',
    [type, name, institution ?? null, last4 ?? null, isCredit ? 1 : 0],
  );
  return { id: res.lastInsertRowId, type, name, institution, last4, isCredit };
}

export async function getAccountById(id: number): Promise<Account | null> {
  const row = await dbGet<Record<string, unknown>>('SELECT * FROM accounts WHERE id=?', [id]);
  return row ? rowToAccount(row) : null;
}

function rowToAccount(r: Record<string, unknown>): Account {
  return {
    id: r.id as number,
    type: r.type as AccountType,
    name: r.name as string,
    institution: (r.institution as string) || undefined,
    last4: (r.last_4 as string) || undefined,
    isCredit: Boolean(r.is_credit),
  };
}

// ── Imported Files ────────────────────────────────────────────────────────────

export async function fileExistsByHash(hash: string): Promise<boolean> {
  const row = await dbGet<{ id: number }>('SELECT id FROM imported_files WHERE file_hash=?', [hash]);
  return row !== null;
}

export async function createImportedFile(
  source: string, filePath: string, fileHash: string, fileFormat: string,
  isEncrypted: boolean, periodStart?: string, periodEnd?: string,
): Promise<number> {
  const res = await dbRun(
    `INSERT INTO imported_files(source, file_path, file_hash, file_format, is_encrypted, period_start, period_end, row_count)
     VALUES(?,?,?,?,?,?,?,0)`,
    [source, filePath, fileHash, fileFormat, isEncrypted ? 1 : 0, periodStart ?? null, periodEnd ?? null],
  );
  return res.lastInsertRowId;
}

export async function updateFileRowCount(fileId: number, count: number): Promise<void> {
  await dbRun('UPDATE imported_files SET row_count=? WHERE id=?', [count, fileId]);
}

export async function listImportedFiles(): Promise<ImportedFile[]> {
  const rows = await dbAll<Record<string, unknown>>('SELECT * FROM imported_files ORDER BY imported_at DESC');
  return rows.map(r => ({
    id: r.id as number,
    source: r.source as string,
    filePath: r.file_path as string,
    fileHash: r.file_hash as string,
    fileFormat: r.file_format as string,
    isEncrypted: Boolean(r.is_encrypted),
    periodStart: (r.period_start as string) || undefined,
    periodEnd: (r.period_end as string) || undefined,
    rowCount: r.row_count as number,
    importedAt: r.imported_at as string,
  }));
}

// ── Raw Transactions ──────────────────────────────────────────────────────────

export async function insertRaw(
  draft: RawTransactionDraft,
  sourceFileId: number,
  paymentAccountId?: number,
): Promise<number | null> {
  try {
    const res = await dbRun(
      `INSERT INTO raw_transactions
       (source, source_file_id, txn_time, amount_cents, currency, counterparty, description,
        payment_account_id, txn_type_raw, direction, external_txn_id, external_merchant_id,
        raw_json, is_group_payment)
       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
      [
        draft.source, sourceFileId, draft.txnTime, draft.amountCents, draft.currency,
        draft.counterparty ?? null, draft.description ?? null, paymentAccountId ?? null,
        draft.txnTypeRaw ?? null, draft.direction,
        draft.externalTxnId ?? null, draft.externalMerchantId ?? null,
        JSON.stringify(draft.rawJson), draft.isGroupPayment ? 1 : 0,
      ],
    );
    return res.lastInsertRowId;
  } catch {
    return null; // UNIQUE constraint violation = duplicate
  }
}

export async function markInternalTransfer(rawId: number, reason: string): Promise<void> {
  await dbRun('UPDATE raw_transactions SET is_internal_transfer=1, transfer_reason=? WHERE id=?', [reason, rawId]);
}

export async function listRawByFileId(fileId: number): Promise<RawTransaction[]> {
  const rows = await dbAll<Record<string, unknown>>(
    'SELECT * FROM raw_transactions WHERE source_file_id=?', [fileId],
  );
  return rows.map(rowToRaw);
}

export async function listRawInPeriod(
  start: string, end: string, source?: string,
): Promise<RawTransaction[]> {
  let sql = 'SELECT * FROM raw_transactions WHERE txn_time >= ? AND txn_time <= ?';
  const params: unknown[] = [start, end + 'T23:59:59'];
  if (source) { sql += ' AND source=?'; params.push(source); }
  sql += ' ORDER BY txn_time DESC';
  const rows = await dbAll<Record<string, unknown>>(sql, params);
  return rows.map(rowToRaw);
}

function rowToRaw(r: Record<string, unknown>): RawTransaction {
  return {
    id: r.id as number,
    source: r.source as string,
    sourceFileId: r.source_file_id as number,
    txnTime: r.txn_time as string,
    amountCents: r.amount_cents as number,
    currency: (r.currency as string) || 'CNY',
    counterparty: (r.counterparty as string) || undefined,
    description: (r.description as string) || undefined,
    paymentAccountId: (r.payment_account_id as number) || undefined,
    txnTypeRaw: (r.txn_type_raw as string) || undefined,
    direction: r.direction as 'expense' | 'income' | 'transfer',
    externalTxnId: (r.external_txn_id as string) || undefined,
    externalMerchantId: (r.external_merchant_id as string) || undefined,
    rawJson: r.raw_json as string,
    isInternalTransfer: Boolean(r.is_internal_transfer),
    transferReason: (r.transfer_reason as string) || undefined,
    isGroupPayment: Boolean(r.is_group_payment),
    isRefund: Boolean(r.is_refund),
  };
}

// ── Canonical Transactions ────────────────────────────────────────────────────

export async function createTransaction(
  primaryRawId: number, txnTime: string, amountCents: number,
  counterparty: string | undefined, description: string | undefined,
  paymentAccountId: number | undefined, direction: 'expense' | 'income',
  isGroupPayment: boolean,
): Promise<number> {
  const res = await dbRun(
    `INSERT INTO transactions
     (primary_raw_id, txn_time, amount_cents, counterparty, description,
      payment_account_id, direction, is_group_payment, inclusion)
     VALUES(?,?,?,?,?,?,?,?,'auto')`,
    [primaryRawId, txnTime, amountCents, counterparty ?? null, description ?? null,
     paymentAccountId ?? null, direction, isGroupPayment ? 1 : 0],
  );
  return res.lastInsertRowId;
}

export async function transactionExistsForRaw(rawId: number): Promise<boolean> {
  const row = await dbGet<{ id: number }>('SELECT id FROM transactions WHERE primary_raw_id=?', [rawId]);
  return row !== null;
}

export async function listTransactionsInPeriod(
  start: string, end: string, direction?: 'expense' | 'income',
): Promise<Transaction[]> {
  let sql = `
    SELECT t.*, a.name as account_name, r.source
    FROM transactions t
    LEFT JOIN accounts a ON a.id = t.payment_account_id
    LEFT JOIN raw_transactions r ON r.id = t.primary_raw_id
    WHERE t.txn_time >= ? AND t.txn_time <= ?`;
  const params: unknown[] = [start, end + 'T23:59:59'];
  if (direction) { sql += ' AND t.direction=?'; params.push(direction); }
  sql += ' ORDER BY t.txn_time DESC';
  const rows = await dbAll<Record<string, unknown>>(sql, params);
  return rows.map(rowToTxn);
}

export async function getTransactionById(id: number): Promise<Transaction | null> {
  const row = await dbGet<Record<string, unknown>>(
    `SELECT t.*, a.name as account_name, r.source
     FROM transactions t
     LEFT JOIN accounts a ON a.id = t.payment_account_id
     LEFT JOIN raw_transactions r ON r.id = t.primary_raw_id
     WHERE t.id=?`, [id],
  );
  return row ? rowToTxn(row) : null;
}

export async function updateInclusion(
  txnId: number, state: InclusionState, note = '',
): Promise<void> {
  await dbRun(
    `UPDATE transactions SET inclusion=?, inclusion_set_at=datetime('now'), inclusion_note=? WHERE id=?`,
    [state, note, txnId],
  );
}

export async function updateTxnCategory(txnId: number, categoryId: number | null): Promise<void> {
  await dbRun('UPDATE transactions SET manual_category_id=? WHERE id=?', [categoryId, txnId]);
}

export async function addDedupLink(
  canonicalTxnId: number, rawTxnId: number,
  confidence: number, reason: string, method: string,
): Promise<void> {
  try {
    await dbRun(
      `INSERT INTO dedup_links(canonical_txn_id, raw_txn_id, match_confidence, match_reason, match_method)
       VALUES(?,?,?,?,?)`,
      [canonicalTxnId, rawTxnId, confidence, reason, method],
    );
  } catch { /* ignore duplicate */ }
}

function rowToTxn(r: Record<string, unknown>): Transaction {
  return {
    id: r.id as number,
    primaryRawId: r.primary_raw_id as number,
    txnTime: r.txn_time as string,
    amountCents: Math.abs(r.amount_cents as number),
    counterparty: (r.counterparty as string) || undefined,
    description: (r.description as string) || undefined,
    paymentAccountId: (r.payment_account_id as number) || undefined,
    direction: r.direction as 'expense' | 'income',
    isGroupPayment: Boolean(r.is_group_payment),
    inclusion: (r.inclusion as InclusionState) || 'auto',
    inclusionNote: (r.inclusion_note as string) || undefined,
    manualCategoryId: (r.manual_category_id as number) || undefined,
    notes: (r.notes as string) || undefined,
    accountName: (r.account_name as string) || undefined,
    source: (r.source as string) || undefined,
  };
}

// ── Categories ────────────────────────────────────────────────────────────────

export async function createCategory(
  name: string, icon: string,
  monthlyBudgetCents?: number, yearlyBudgetCents?: number,
): Promise<number> {
  const res = await dbRun(
    'INSERT INTO manual_categories(name, icon, monthly_budget_cents, yearly_budget_cents) VALUES(?,?,?,?)',
    [name, icon, monthlyBudgetCents ?? null, yearlyBudgetCents ?? null],
  );
  return res.lastInsertRowId;
}

export async function listCategories(): Promise<ManualCategory[]> {
  const rows = await dbAll<Record<string, unknown>>(
    'SELECT * FROM manual_categories WHERE is_active=1 ORDER BY name',
  );
  return rows.map(rowToCategory);
}

export async function getCategoryByName(name: string): Promise<ManualCategory | null> {
  const row = await dbGet<Record<string, unknown>>(
    'SELECT * FROM manual_categories WHERE name=? AND is_active=1', [name],
  );
  return row ? rowToCategory(row) : null;
}

export async function getCategoryById(id: number): Promise<ManualCategory | null> {
  const row = await dbGet<Record<string, unknown>>(
    'SELECT * FROM manual_categories WHERE id=? AND is_active=1', [id],
  );
  return row ? rowToCategory(row) : null;
}

export async function updateCategoryBudget(
  id: number, monthly?: number, yearly?: number,
): Promise<void> {
  await dbRun(
    'UPDATE manual_categories SET monthly_budget_cents=?, yearly_budget_cents=? WHERE id=?',
    [monthly ?? null, yearly ?? null, id],
  );
}

export async function deactivateCategory(id: number): Promise<void> {
  await dbRun('UPDATE manual_categories SET is_active=0 WHERE id=?', [id]);
}

function rowToCategory(r: Record<string, unknown>): ManualCategory {
  return {
    id: r.id as number,
    name: r.name as string,
    icon: (r.icon as string) || '',
    monthlyBudgetCents: (r.monthly_budget_cents as number) || undefined,
    yearlyBudgetCents: (r.yearly_budget_cents as number) || undefined,
    isActive: Boolean(r.is_active),
  };
}

// ── Manual Entries ────────────────────────────────────────────────────────────

export async function createEntry(
  categoryId: number, txnTime: string, amountCents: number,
  description?: string, linkedTxnId?: number,
): Promise<number> {
  const res = await dbRun(
    'INSERT INTO manual_entries(category_id, txn_time, amount_cents, description, linked_txn_id) VALUES(?,?,?,?,?)',
    [categoryId, txnTime, amountCents, description ?? null, linkedTxnId ?? null],
  );
  return res.lastInsertRowId;
}

export async function listEntries(
  categoryId?: number, start?: string, end?: string,
): Promise<ManualEntry[]> {
  let sql = 'SELECT * FROM manual_entries WHERE 1=1';
  const params: unknown[] = [];
  if (categoryId) { sql += ' AND category_id=?'; params.push(categoryId); }
  if (start) { sql += ' AND txn_time >= ?'; params.push(start); }
  if (end) { sql += ' AND txn_time <= ?'; params.push(end + 'T23:59:59'); }
  sql += ' ORDER BY txn_time DESC';
  const rows = await dbAll<Record<string, unknown>>(sql, params);
  return rows.map(r => ({
    id: r.id as number,
    categoryId: r.category_id as number,
    txnTime: r.txn_time as string,
    amountCents: r.amount_cents as number,
    description: (r.description as string) || undefined,
    linkedTxnId: (r.linked_txn_id as number) || undefined,
    createdAt: r.created_at as string,
  }));
}

export async function deleteEntry(id: number): Promise<boolean> {
  const res = await dbRun('DELETE FROM manual_entries WHERE id=?', [id]);
  return res.changes > 0;
}

export async function sumEntriesInPeriod(
  categoryId: number, start: string, end: string,
): Promise<number> {
  const row = await dbGet<{ total: number }>(
    `SELECT COALESCE(SUM(amount_cents),0) as total FROM manual_entries
     WHERE category_id=? AND txn_time >= ? AND txn_time <= ?`,
    [categoryId, start, end + 'T23:59:59'],
  );
  return row?.total ?? 0;
}

// ── DB-level stats ────────────────────────────────────────────────────────────

export async function getDbStats(): Promise<Record<string, number>> {
  const tables = ['accounts', 'imported_files', 'raw_transactions', 'transactions',
                  'manual_categories', 'manual_entries'];
  const stats: Record<string, number> = {};
  for (const t of tables) {
    const r = await dbGet<{ cnt: number }>(`SELECT COUNT(*) as cnt FROM ${t}`);
    stats[t] = r?.cnt ?? 0;
  }
  return stats;
}
