// ── Core domain types ────────────────────────────────────────────────────────

export type Direction = 'expense' | 'income' | 'transfer';
export type InclusionState = 'auto' | 'included' | 'excluded' | 'offset';
export type AccountType =
  | 'bank_debit' | 'bank_credit'
  | 'wechat_balance' | 'alipay_balance'
  | 'huabei' | 'meituan_yuefu' | 'yuebao' | 'lingqiantong' | 'unknown';

export interface Account {
  id: number;
  type: AccountType;
  name: string;
  institution?: string;
  last4?: string;
  isCredit: boolean;
}

export interface ImportedFile {
  id: number;
  source: string;
  filePath: string;
  fileHash: string;
  fileFormat: string;
  isEncrypted: boolean;
  periodStart?: string;
  periodEnd?: string;
  rowCount: number;
  importedAt: string;
}

export interface RawTransaction {
  id: number;
  source: string;
  sourceFileId: number;
  txnTime: string;       // ISO string
  amountCents: number;   // positive = income, negative = expense (stored as-is)
  currency: string;
  counterparty?: string;
  description?: string;
  paymentAccountId?: number;
  txnTypeRaw?: string;
  direction: Direction;
  externalTxnId?: string;
  externalMerchantId?: string;
  rawJson: string;
  isInternalTransfer: boolean;
  transferReason?: string;
  isGroupPayment: boolean;
  isRefund: boolean;
}

export interface Transaction {
  id: number;
  primaryRawId: number;
  txnTime: string;
  amountCents: number;   // always positive for display
  counterparty?: string;
  description?: string;
  paymentAccountId?: number;
  direction: 'expense' | 'income';
  isGroupPayment: boolean;
  inclusion: InclusionState;
  inclusionNote?: string;
  manualCategoryId?: number;
  notes?: string;
  // joined
  accountName?: string;
  source?: string;
}

export interface ManualCategory {
  id: number;
  name: string;
  icon: string;
  monthlyBudgetCents?: number;
  yearlyBudgetCents?: number;
  isActive: boolean;
}

export interface ManualEntry {
  id: number;
  categoryId: number;
  txnTime: string;
  amountCents: number;
  description?: string;
  linkedTxnId?: number;
  createdAt: string;
}

export interface CategoryProgress {
  categoryId: number;
  name: string;
  icon: string;
  monthSpentCents: number;
  monthlyBudgetCents?: number;
  monthlyPct?: number;
  yearSpentCents: number;
  yearlyBudgetCents?: number;
  yearlyPct?: number;
  alertText: string;
}

export interface MissingAccount {
  institution: string;
  last4?: string;
  type: string;
  evidence: string[];
  priority: 'high' | 'medium' | 'low';
}

export interface MonthlyTotal {
  totalExpenseCents: number;
  rawExpenseCents: number;
  offsetIncomeCents: number;
  totalIncomeCents: number;
  excludedCount: number;
}

// Draft used during parsing before DB insert
export interface RawTransactionDraft {
  source: string;
  txnTime: string;
  amountCents: number;
  currency: string;
  counterparty?: string;
  description?: string;
  paymentMethodRaw?: string;
  txnTypeRaw?: string;
  direction: Direction;
  externalTxnId?: string;
  externalMerchantId?: string;
  isGroupPayment: boolean;
  rawJson: Record<string, unknown>;
}

export interface ImportResult {
  skippedDuplicate?: boolean;
  fileId?: number;
  rowsParsed: number;
  rowsInserted: number;
  rowsDuplicate: number;
  internalTransfersDetected: number;
  source: string;
  periodStart?: string;
  periodEnd?: string;
  error?: string;
}
