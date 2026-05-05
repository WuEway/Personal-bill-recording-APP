import { getOrCreateAccount } from '../db/repositories';
import type { Account } from '../models';

const BANK_PATTERN = /^(.+?)(储蓄卡|信用卡)\((\d+)\)$/;

const INSTITUTION_MAP: Record<string, string> = {
  '工商': '工商银行', 'ICBC': '工商银行',
  '建设': '建设银行', 'CCB': '建设银行',
  '平安': '平安银行', 'PINGAN': '平安银行',
  '招商': '招商银行', 'CMB': '招商银行',
  '中国银行': '中国银行', 'BOC': '中国银行',
  '农业': '农业银行', 'ABC': '农业银行',
  '交通': '交通银行', '光大': '光大银行',
  '民生': '民生银行', '广发': '广发银行',
  '兴业': '兴业银行', '浦发': '浦发银行',
};

function normalizeInstitution(raw: string): string {
  for (const [k, v] of Object.entries(INSTITUTION_MAP)) {
    if (raw.includes(k)) return v;
  }
  return raw.trim();
}

export async function resolveAccount(
  paymentMethodRaw: string | undefined,
  _source: string,
): Promise<number | undefined> {
  if (!paymentMethodRaw) return undefined;

  if (['零钱', '/', '微信零钱'].includes(paymentMethodRaw)) {
    const acc = await getOrCreateAccount('wechat_balance', '微信零钱', '微信支付');
    return acc.id;
  }
  if (paymentMethodRaw === '__SHADOW_WECHAT__') {
    const acc = await getOrCreateAccount('wechat_balance', '微信支付（影子）', '微信支付');
    return acc.id;
  }
  if (paymentMethodRaw === '__SHADOW_ALIPAY__') {
    const acc = await getOrCreateAccount('alipay_balance', '支付宝（影子）', '支付宝');
    return acc.id;
  }

  const m = BANK_PATTERN.exec(paymentMethodRaw);
  if (m) {
    const [, instRaw, kind, last4] = m;
    const institution = normalizeInstitution(instRaw);
    const type = kind === '信用卡' ? 'bank_credit' : 'bank_debit';
    const acc = await getOrCreateAccount(type, paymentMethodRaw, institution, last4, kind === '信用卡');
    return acc.id;
  }

  if (paymentMethodRaw.includes('余额宝')) {
    const acc = await getOrCreateAccount('yuebao', '余额宝', '支付宝');
    return acc.id;
  }
  if (paymentMethodRaw.includes('花呗')) {
    const acc = await getOrCreateAccount('huabei', '花呗', '支付宝');
    return acc.id;
  }
  if (paymentMethodRaw.includes('零钱通')) {
    const acc = await getOrCreateAccount('lingqiantong', '零钱通', '微信支付');
    return acc.id;
  }
  if (paymentMethodRaw.includes('余额') && !paymentMethodRaw.includes('银行')) {
    const acc = await getOrCreateAccount('alipay_balance', '支付宝余额', '支付宝');
    return acc.id;
  }

  const acc = await getOrCreateAccount('unknown', paymentMethodRaw, 'unknown');
  return acc.id;
}
