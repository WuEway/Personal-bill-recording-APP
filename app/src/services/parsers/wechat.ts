import * as XLSX from 'xlsx';
import type { RawTransactionDraft } from '../../models';

const EXPECTED_HEADERS = ['交易时间', '交易类型', '交易对方', '商品', '收/支',
                          '金额(元)', '支付方式', '当前状态', '交易单号', '商户单号', '备注'];

function parseAmount(val: unknown): number {
  if (typeof val === 'number') return val;
  const s = String(val ?? '').replace(/¥|,/g, '').trim();
  return parseFloat(s) || 0;
}

function parseTime(val: unknown): string {
  if (val instanceof Date) return val.toISOString().replace('Z', '');
  const s = String(val ?? '').trim();
  // "2026-04-15 12:00:00" or "2026/04/15 12:00:00"
  const norm = s.replace(/\//g, '-');
  try {
    const d = new Date(norm);
    if (!isNaN(d.getTime())) return d.toISOString().replace('Z', '');
  } catch { /**/ }
  return new Date().toISOString();
}

export function parseWechatXlsx(buffer: ArrayBuffer): RawTransactionDraft[] {
  const wb = XLSX.read(buffer, { type: 'buffer', cellDates: true });
  const ws = wb.Sheets[wb.SheetNames[0]];
  const rows: unknown[][] = XLSX.utils.sheet_to_json(ws, { header: 1, defval: null }) as unknown[][];

  // Find header row
  let dataStart = -1;
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i] as unknown[];
    if (row && String(row[0] ?? '').trim() === '交易时间') {
      dataStart = i + 1;
      break;
    }
  }
  if (dataStart === -1) throw new Error('找不到微信账单表头行（"交易时间"）');

  const drafts: RawTransactionDraft[] = [];
  for (let i = dataStart; i < rows.length; i++) {
    const row = rows[i] as unknown[];
    if (!row || !row[0]) continue;

    const [timeVal, txnType, party, item, sign, amountVal,
           payment, , txnId, merchantId, note] = row;

    const signStr = String(sign ?? '').trim();
    const amount = parseAmount(amountVal);

    let direction: 'expense' | 'income' | 'transfer';
    let amountCents: number;

    if (signStr === '支出') {
      direction = 'expense';
      amountCents = -Math.round(Math.abs(amount) * 100);
    } else if (signStr === '收入') {
      direction = 'income';
      amountCents = Math.round(Math.abs(amount) * 100);
    } else {
      direction = 'transfer';
      amountCents = Math.round(amount * 100);
    }

    const isGroupPayment = String(txnType ?? '').trim() === '群收款';

    drafts.push({
      source: 'wechat',
      txnTime: parseTime(timeVal),
      amountCents,
      currency: 'CNY',
      counterparty: String(party ?? '').trim() || undefined,
      description: String(item ?? '').trim() || undefined,
      paymentMethodRaw: String(payment ?? '').trim() || undefined,
      txnTypeRaw: String(txnType ?? '').trim() || undefined,
      direction,
      externalTxnId: String(txnId ?? '').trim() || undefined,
      externalMerchantId: String(merchantId ?? '').trim() || undefined,
      isGroupPayment,
      rawJson: { sign: signStr, note: String(note ?? '') },
    });
  }
  return drafts;
}

/** Detect period from parsed drafts */
export function detectPeriod(drafts: RawTransactionDraft[]): { start: string; end: string } | null {
  if (!drafts.length) return null;
  const dates = drafts.map(d => d.txnTime.slice(0, 10)).sort();
  return { start: dates[0], end: dates[dates.length - 1] };
}
