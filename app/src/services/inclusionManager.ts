import { updateInclusion, listTransactionsInPeriod, getTransactionById } from '../db/repositories';
import type { InclusionState, MonthlyTotal, Transaction } from '../models';

export function effectiveInclusion(t: Transaction): 'expense' | 'offset' | 'excluded' {
  if (t.inclusion === 'excluded') return 'excluded';
  if (t.inclusion === 'offset' && t.direction === 'income') return 'offset';
  if (t.inclusion === 'included') return t.direction === 'expense' ? 'expense' : 'excluded';
  // auto:
  if (t.direction === 'expense' && !t.isGroupPayment) return 'expense';
  return 'excluded';
}

export function countsInTotal(t: Transaction): boolean {
  return effectiveInclusion(t) !== 'excluded';
}

export async function setInclusion(
  txnId: number, state: InclusionState, note = '',
): Promise<void> {
  const txn = await getTransactionById(txnId);
  if (!txn) throw new Error(`Transaction ${txnId} not found`);
  if (state === 'offset' && txn.direction !== 'income') {
    throw new Error("'offset' 只能设置在收入交易上");
  }
  await updateInclusion(txnId, state, note);
}

export async function computeTotal(start: string, end: string): Promise<MonthlyTotal> {
  const txns = await listTransactionsInPeriod(start, end);
  let rawExpense = 0, offsetIncome = 0, totalIncome = 0, excludedCount = 0;

  for (const t of txns) {
    const eff = effectiveInclusion(t);
    if (eff === 'expense') rawExpense += t.amountCents;
    else if (eff === 'offset') offsetIncome += t.amountCents;
    else if (eff === 'excluded') excludedCount++;
    if (t.direction === 'income' && t.inclusion !== 'excluded') totalIncome += t.amountCents;
  }

  return {
    totalExpenseCents: rawExpense - offsetIncome,
    rawExpenseCents: rawExpense,
    offsetIncomeCents: offsetIncome,
    totalIncomeCents: totalIncome,
    excludedCount,
  };
}
