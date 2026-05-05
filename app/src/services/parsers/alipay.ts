import type { RawTransactionDraft } from '../../models';

/**
 * Parse Alipay CSV.
 * Encoding: GBK (React Native can't decode GBK natively).
 * The file arrives as a string — caller must handle encoding (read as latin1 + recode,
 * or use Expo FileSystem with encoding fallback). We receive already-decoded text.
 */
export function parseAlipayText(text: string): RawTransactionDraft[] {
  const lines = text.split('\n');

  // Find the header line
  let headerIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i].trimStart().replace(/^﻿/, '');
    if (l.startsWith('交易时间,') || l.startsWith('交易时间\t')) {
      headerIdx = i;
      break;
    }
  }
  if (headerIdx === -1) throw new Error('找不到支付宝账单表头行（"交易时间"）');

  const drafts: RawTransactionDraft[] = [];
  for (let i = headerIdx + 1; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;

    const cols = splitCsvLine(line);
    if (cols.length < 11) continue;

    const [timeStr, category, party, , item, signStr, amountStr,
           payment, status, txnId, merchantId, note = ''] = cols;

    if (!timeStr || timeStr === '交易时间') continue;

    let amount = parseFloat((amountStr ?? '').replace(/,/g, '').trim()) || 0;
    const sign = (signStr ?? '').trim();

    let direction: 'expense' | 'income' | 'transfer';
    let amountCents: number;

    if (sign === '支出') {
      direction = 'expense';
      amountCents = -Math.round(Math.abs(amount) * 100);
    } else if (sign === '收入') {
      direction = 'income';
      amountCents = Math.round(Math.abs(amount) * 100);
    } else {
      direction = 'transfer'; // 不计收支
      amountCents = Math.round(amount * 100);
    }

    // ¥0.00 rows (医保等) → treat as transfer
    if (amount === 0) {
      direction = 'transfer';
      amountCents = 0;
    }

    const primaryPayment = (payment ?? '').split('&')[0].trim() || undefined;

    drafts.push({
      source: 'alipay',
      txnTime: parseAlipayTime(timeStr),
      amountCents,
      currency: 'CNY',
      counterparty: (party ?? '').trim() || undefined,
      description: (item ?? '').trim() || undefined,
      paymentMethodRaw: primaryPayment,
      txnTypeRaw: (category ?? '').trim() || undefined,
      direction,
      externalTxnId: (txnId ?? '').trim().replace(/\t$/, '') || undefined,
      externalMerchantId: (merchantId ?? '').trim().replace(/\t$/, '') || undefined,
      isGroupPayment: false,
      rawJson: { fullPayment: payment, note, status },
    });
  }
  return drafts;
}

function parseAlipayTime(s: string): string {
  const norm = s.trim().replace(/\//g, '-');
  try {
    const d = new Date(norm);
    if (!isNaN(d.getTime())) return d.toISOString().replace('Z', '');
  } catch { /**/ }
  return new Date().toISOString();
}

/** Simple CSV splitter (handles quoted fields) */
function splitCsvLine(line: string): string[] {
  const result: string[] = [];
  let current = '';
  let inQuote = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') { inQuote = !inQuote; continue; }
    if (ch === ',' && !inQuote) { result.push(current); current = ''; continue; }
    current += ch;
  }
  result.push(current);
  return result;
}
