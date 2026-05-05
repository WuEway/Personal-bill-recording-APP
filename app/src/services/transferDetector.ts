import type { RawTransaction } from '../models';

type TransferRule = {
  name: string;
  match: (t: RawTransaction) => boolean;
  reason: string;
};

const BASE_RULES: TransferRule[] = [
  { name: 'cc_repayment',
    match: t => !!(t.txnTypeRaw?.includes('信用卡还款') ||
                  (t.counterparty?.includes('信用卡') && t.description?.includes('还款'))),
    reason: 'cc_repayment' },
  { name: 'huabei_repay',
    match: t => !!(t.counterparty?.includes('花呗') && t.description?.includes('还款')),
    reason: 'huabei_repayment' },
  { name: 'meituan_repay',
    match: t => !!(t.counterparty === '美团' && t.description?.includes('美团月付') && t.description.includes('还款')),
    reason: 'meituan_yuefu_repayment' },
  { name: 'yuebao_in',
    match: t => t.counterparty === '余额宝' && t.amountCents < 0,
    reason: 'yuebao_purchase' },
  { name: 'yuebao_out',
    match: t => !!(t.description?.includes('余额宝') && t.amountCents > 0),
    reason: 'yuebao_redeem' },
  { name: 'lqt_in',
    match: t => !!(t.counterparty?.includes('零钱通') && t.amountCents < 0),
    reason: 'lqt_purchase' },
  { name: 'lqt_out',
    match: t => !!(t.description?.includes('零钱通') && t.amountCents > 0),
    reason: 'lqt_redeem' },
  { name: 'topup',
    match: t => !!(t.txnTypeRaw?.includes('充值') || t.txnTypeRaw?.includes('储蓄卡入账')),
    reason: 'topup' },
  { name: 'withdrawal',
    match: t => !!(t.txnTypeRaw?.includes('提现')),
    reason: 'withdrawal' },
  { name: 'investment',
    match: t => !!(['基金', '理财', '股票', '债券', '定期'].some(kw => t.txnTypeRaw?.includes(kw))),
    reason: 'investment' },
  { name: 'source_transfer',
    match: t => t.direction === 'transfer',
    reason: 'unknown_transfer' },
];

export function detectTransfer(txn: RawTransaction, userName?: string): string | null {
  const rules = [...BASE_RULES];
  if (userName) {
    rules.unshift({
      name: 'self_transfer',
      match: t => t.counterparty === userName,
      reason: 'self_transfer',
    });
  }
  for (const rule of rules) {
    try { if (rule.match(txn)) return rule.reason; } catch { /* skip */ }
  }
  return null;
}
