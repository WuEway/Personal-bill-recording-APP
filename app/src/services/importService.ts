import * as FileSystem from 'expo-file-system';
import * as DocumentPicker from 'expo-document-picker';

import {
  fileExistsByHash, createImportedFile, updateFileRowCount,
  insertRaw, listRawByFileId, markInternalTransfer,
} from '../db/repositories';
import { resolveAccount } from './accountResolver';
import { detectTransfer } from './transferDetector';
import { parseWechatXlsx, detectPeriod as wechatPeriod } from './parsers/wechat';
import { parseAlipayText } from './parsers/alipay';
import { fileHash } from '../utils/format';
import type { ImportResult, RawTransactionDraft } from '../models';
import { getConfig } from '../db/database';

export type SupportedSource = 'wechat' | 'alipay' | 'auto';

export interface PickAndImportResult {
  cancelled: boolean;
  results: ImportResult[];
}

/**
 * Open document picker and import the selected file.
 */
export async function pickAndImport(sourceHint: SupportedSource = 'auto'): Promise<PickAndImportResult> {
  const picked = await DocumentPicker.getDocumentAsync({
    type: ['*/*'],
    copyToCacheDirectory: true,
    multiple: false,
  });

  if (picked.canceled) return { cancelled: true, results: [] };

  const asset = picked.assets[0];
  if (!asset?.uri) return { cancelled: false, results: [{ rowsParsed: 0, rowsInserted: 0, rowsDuplicate: 0, internalTransfersDetected: 0, source: '', error: '无法读取文件' }] };

  const results = await importFile(asset.uri, asset.name ?? 'unknown', sourceHint);
  return { cancelled: false, results };
}

export async function importFile(
  uri: string,
  fileName: string,
  sourceHint: SupportedSource = 'auto',
): Promise<ImportResult[]> {
  const ext = fileName.split('.').pop()?.toLowerCase() ?? '';
  const userName = await getConfig('user_name') ?? undefined;

  // Read file content
  let buffer: ArrayBuffer | null = null;
  let textContent: string | null = null;

  try {
    if (ext === 'xlsx' || ext === 'xls') {
      const b64 = await FileSystem.readAsStringAsync(uri, { encoding: FileSystem.EncodingType.Base64 });
      // Convert base64 to ArrayBuffer
      buffer = base64ToArrayBuffer(b64);
    } else {
      // Try UTF-8 first, then latin1 for GBK files
      try {
        textContent = await FileSystem.readAsStringAsync(uri, { encoding: FileSystem.EncodingType.UTF8 });
      } catch {
        textContent = await FileSystem.readAsStringAsync(uri, { encoding: FileSystem.EncodingType.Base64 });
        textContent = atob(textContent); // latin1 decode
      }
    }
  } catch (e) {
    return [{ rowsParsed: 0, rowsInserted: 0, rowsDuplicate: 0, internalTransfersDetected: 0, source: '', error: `读取文件失败: ${String(e)}` }];
  }

  // Compute hash for dedup
  const hashInput = buffer
    ? String(buffer.byteLength) + fileName
    : (textContent ?? '');
  const hash = await fileHash(hashInput + fileName);

  if (await fileExistsByHash(hash)) {
    return [{ skippedDuplicate: true, rowsParsed: 0, rowsInserted: 0, rowsDuplicate: 0, internalTransfersDetected: 0, source: '' }];
  }

  // Detect source and parse
  const source = detectSource(fileName, sourceHint);
  let drafts: RawTransactionDraft[] = [];

  try {
    if (source === 'wechat' && buffer) {
      drafts = parseWechatXlsx(buffer);
    } else if (source === 'wechat' && textContent) {
      // WeChat CSV
      drafts = parseWechatCsv(textContent);
    } else if (source === 'alipay' && textContent) {
      drafts = parseAlipayText(textContent);
    } else {
      return [{ rowsParsed: 0, rowsInserted: 0, rowsDuplicate: 0, internalTransfersDetected: 0, source, error: `不支持的文件格式或来源（${ext}）。请使用微信/支付宝账单文件。` }];
    }
  } catch (e) {
    return [{ rowsParsed: 0, rowsInserted: 0, rowsDuplicate: 0, internalTransfersDetected: 0, source, error: `解析失败: ${String(e)}` }];
  }

  // Detect period
  const dates = drafts.map(d => d.txnTime.slice(0, 10)).filter(Boolean).sort();
  const periodStart = dates[0];
  const periodEnd = dates[dates.length - 1];

  const fileId = await createImportedFile(source, fileName, hash, ext, false, periodStart, periodEnd);
  const result: ImportResult = {
    fileId,
    rowsParsed: drafts.length,
    rowsInserted: 0,
    rowsDuplicate: 0,
    internalTransfersDetected: 0,
    source,
    periodStart,
    periodEnd,
  };

  for (const draft of drafts) {
    const accountId = await resolveAccount(draft.paymentMethodRaw, draft.source);
    const rawId = await insertRaw(draft, fileId, accountId);
    if (rawId === null) { result.rowsDuplicate++; continue; }
    result.rowsInserted++;
  }

  await updateFileRowCount(fileId, result.rowsInserted);

  // Run transfer detection
  const raws = await listRawByFileId(fileId);
  for (const raw of raws) {
    const reason = detectTransfer(raw, userName);
    if (reason) {
      await markInternalTransfer(raw.id, reason);
      result.internalTransfersDetected++;
    }
  }

  return [result];
}

function detectSource(fileName: string, hint: SupportedSource): string {
  if (hint !== 'auto') return hint;
  const lower = fileName.toLowerCase();
  if (lower.includes('微信') || lower.includes('wechat')) return 'wechat';
  if (lower.includes('支付宝') || lower.includes('alipay')) return 'alipay';
  // guess by extension
  if (lower.endsWith('.xlsx')) return 'wechat';
  if (lower.endsWith('.csv')) return 'alipay';
  return 'unknown';
}

function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

// Minimal WeChat CSV parser (same logic as xlsx but from text)
function parseWechatCsv(text: string): RawTransactionDraft[] {
  const { parseAlipayText: _ } = require('./parsers/alipay');
  // Reuse alipay CSV structure detection — WeChat CSV is similar
  const lines = text.split('\n');
  let headerIdx = -1;
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes('交易时间') && lines[i].includes('交易类型')) { headerIdx = i; break; }
  }
  if (headerIdx === -1) return [];

  const result: RawTransactionDraft[] = [];
  for (let i = headerIdx + 1; i < lines.length; i++) {
    const cols = lines[i].split(',');
    if (cols.length < 6 || !cols[0]?.trim()) continue;
    const [timeStr, txnType, party, item, sign, amountStr, payment, , txnId, merchantId, note = ''] = cols;
    const amount = parseFloat((amountStr ?? '').replace(/¥|,/g, '')) || 0;
    const signStr = (sign ?? '').trim();
    let direction: 'expense' | 'income' | 'transfer' = 'transfer';
    let amountCents = 0;
    if (signStr === '支出') { direction = 'expense'; amountCents = -Math.round(Math.abs(amount) * 100); }
    else if (signStr === '收入') { direction = 'income'; amountCents = Math.round(Math.abs(amount) * 100); }
    else { direction = 'transfer'; amountCents = Math.round(amount * 100); }

    result.push({
      source: 'wechat',
      txnTime: (() => { try { return new Date(timeStr.trim().replace(/\//g, '-')).toISOString(); } catch { return new Date().toISOString(); } })(),
      amountCents,
      currency: 'CNY',
      counterparty: (party ?? '').trim() || undefined,
      description: (item ?? '').trim() || undefined,
      paymentMethodRaw: (payment ?? '').trim() || undefined,
      txnTypeRaw: (txnType ?? '').trim() || undefined,
      direction,
      externalTxnId: (txnId ?? '').trim() || undefined,
      externalMerchantId: (merchantId ?? '').trim() || undefined,
      isGroupPayment: (txnType ?? '').trim() === '群收款',
      rawJson: { sign: signStr, note: (note ?? '').trim() },
    });
  }
  return result;
}
