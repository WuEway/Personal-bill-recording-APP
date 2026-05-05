import {
  listRawInPeriod, listTransactionsInPeriod, transactionExistsForRaw,
  createTransaction, addDedupLink, markInternalTransfer, getAccountById,
} from '../db/repositories';
import type { RawTransaction, Transaction } from '../models';

export interface DedupeStats {
  created: number;
  bankLinkedAsShadow: number;
  bankStandalone: number;
}

function isBankShadow(raw: RawTransaction): 'wechat' | 'alipay' | null {
  if (!raw.source.startsWith('bank_')) return null;
  const text = `${raw.counterparty ?? ''} ${raw.description ?? ''}`;
  if (text.includes('财付通') || text.includes('微信')) return 'wechat';
  if (text.includes('支付宝') || text.includes('蚂蚁')) return 'alipay';
  return null;
}

function addDays(dateStr: string, days: number): string {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export async function runDedupe(periodStart: string, periodEnd: string): Promise<DedupeStats> {
  const expandedStart = addDays(periodStart, -3);
  const expandedEnd = addDays(periodEnd, 3);

  const stats: DedupeStats = { created: 0, bankLinkedAsShadow: 0, bankStandalone: 0 };

  // Step 1: Create canonical transactions for app sources (wechat/alipay)
  const appRaws = await listRawInPeriod(expandedStart, expandedEnd);
  for (const raw of appRaws) {
    if (raw.isInternalTransfer || raw.direction === 'transfer') continue;
    if (raw.source.startsWith('bank_')) continue;
    if (await transactionExistsForRaw(raw.id)) continue;

    await createTransaction(
      raw.id, raw.txnTime, Math.abs(raw.amountCents),
      raw.counterparty, raw.description, raw.paymentAccountId,
      raw.direction as 'expense' | 'income',
      raw.isGroupPayment,
    );
    stats.created++;
  }

  // Step 2: Handle bank records — match shadows or create standalone
  const bankRaws = appRaws.filter(r =>
    r.source.startsWith('bank_') && !r.isInternalTransfer && r.direction !== 'transfer',
  );

  // Build lookup index: amount → canonical transactions
  const appTxns = await listTransactionsInPeriod(expandedStart, expandedEnd);
  const amountIndex = new Map<number, Transaction[]>();
  for (const t of appTxns) {
    const key = t.amountCents;
    if (!amountIndex.has(key)) amountIndex.set(key, []);
    amountIndex.get(key)!.push(t);
  }

  for (const bankRaw of bankRaws) {
    if (await transactionExistsForRaw(bankRaw.id)) continue;
    const shadowApp = isBankShadow(bankRaw);
    let matched = false;

    if (shadowApp) {
      const candidates = amountIndex.get(Math.abs(bankRaw.amountCents)) ?? [];
      for (const cand of candidates) {
        if (cand.direction !== 'expense' && cand.direction !== bankRaw.direction) continue;

        const candDate = cand.txnTime.slice(0, 10);
        const bankDate = bankRaw.txnTime.slice(0, 10);
        const delta = Math.abs(
          (new Date(candDate).getTime() - new Date(bankDate).getTime()) / 86400000,
        );
        if (delta > 2) continue;

        // Account card matching
        const bankAcc = bankRaw.paymentAccountId
          ? await getAccountById(bankRaw.paymentAccountId) : null;
        const candAcc = cand.paymentAccountId
          ? await getAccountById(cand.paymentAccountId) : null;

        if (bankAcc?.last4 && candAcc?.last4 && bankAcc.last4 !== candAcc.last4) continue;

        const confidence = delta === 0 ? 1.0 : delta === 1 ? 0.95 : 0.85;
        const reason = `amount=${cand.amountCents / 100},last4=${bankAcc?.last4 ?? '?'},delta=${delta}d`;
        await addDedupLink(cand.id, bankRaw.id, confidence, reason, 'exact');
        await markInternalTransfer(bankRaw.id, `shadow_of_txn_${cand.id}`);
        stats.bankLinkedAsShadow++;
        matched = true;
        break;
      }
    }

    if (!matched) {
      await createTransaction(
        bankRaw.id, bankRaw.txnTime, Math.abs(bankRaw.amountCents),
        bankRaw.counterparty, bankRaw.description, bankRaw.paymentAccountId,
        bankRaw.direction as 'expense' | 'income',
        bankRaw.isGroupPayment,
      );
      stats.bankStandalone++;
    }
  }

  return stats;
}
