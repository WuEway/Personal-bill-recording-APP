import {
  createCategory, listCategories, getCategoryByName, getCategoryById,
  updateCategoryBudget, deactivateCategory, createEntry, listEntries,
  deleteEntry, sumEntriesInPeriod, updateTxnCategory,
} from '../db/repositories';
import type { CategoryProgress, ManualCategory, ManualEntry } from '../models';
import { fmtAmount } from '../utils/format';

export const DEFAULT_CATEGORIES = [
  { name: '恋爱', icon: '💑' },
  { name: '衣服', icon: '👕' },
  { name: '培训学习', icon: '📚' },
  { name: '旅游', icon: '✈️' },
  { name: '医疗', icon: '🏥' },
  { name: '数码', icon: '📱' },
  { name: '宠物', icon: '🐱' },
  { name: '健身美容', icon: '💪' },
  { name: '演唱会追星', icon: '🎤' },
  { name: '游戏氪金', icon: '🎮' },
  { name: '手办收藏', icon: '🎎' },
  { name: '人情往来', icon: '🎁' },
  { name: '朋友聚餐', icon: '🍻' },
];

export async function addCategory(
  name: string, icon = '',
  monthlyBudget?: number, yearlyBudget?: number,
): Promise<number> {
  const existing = await getCategoryByName(name);
  if (existing) throw new Error(`类目 "${name}" 已存在`);
  return createCategory(
    name, icon,
    monthlyBudget ? Math.round(monthlyBudget * 100) : undefined,
    yearlyBudget ? Math.round(yearlyBudget * 100) : undefined,
  );
}

export { listCategories, getCategoryById, deactivateCategory };

export async function setBudget(
  name: string, monthly?: number, yearly?: number,
): Promise<void> {
  const cat = await getCategoryByName(name);
  if (!cat) throw new Error(`类目 "${name}" 不存在`);
  await updateCategoryBudget(
    cat.id,
    monthly !== undefined ? Math.round(monthly * 100) : undefined,
    yearly !== undefined ? Math.round(yearly * 100) : undefined,
  );
}

export async function addEntry(
  categoryName: string, amount: number, description: string,
  txnTime: string, linkedTxnId?: number,
): Promise<number> {
  const cat = await getCategoryByName(categoryName);
  if (!cat) throw new Error(`类目 "${categoryName}" 不存在`);
  const id = await createEntry(cat.id, txnTime, Math.round(amount * 100), description, linkedTxnId);
  if (linkedTxnId) await updateTxnCategory(linkedTxnId, cat.id);
  return id;
}

export { listEntries, deleteEntry };

export async function getCategoryProgress(
  cat: ManualCategory,
  refDate: Date = new Date(),
): Promise<CategoryProgress> {
  const year = refDate.getFullYear();
  const month = refDate.getMonth() + 1;

  const monthStart = `${year}-${String(month).padStart(2, '0')}-01`;
  const monthEnd = new Date(year, month, 0); // last day of month
  const monthEndStr = monthEnd.toISOString().slice(0, 10);

  const yearStart = `${year}-01-01`;
  const yearEnd = `${year}-12-31`;

  const monthCents = await sumEntriesInPeriod(cat.id, monthStart, monthEndStr);
  const yearCents = await sumEntriesInPeriod(cat.id, yearStart, yearEnd);

  const monthlyPct = cat.monthlyBudgetCents ? monthCents / cat.monthlyBudgetCents : undefined;
  const yearlyPct = cat.yearlyBudgetCents ? yearCents / cat.yearlyBudgetCents : undefined;

  const alert = makeAlert(cat, monthCents, yearCents, monthlyPct, yearlyPct);

  return {
    categoryId: cat.id,
    name: cat.name,
    icon: cat.icon,
    monthSpentCents: monthCents,
    monthlyBudgetCents: cat.monthlyBudgetCents,
    monthlyPct,
    yearSpentCents: yearCents,
    yearlyBudgetCents: cat.yearlyBudgetCents,
    yearlyPct,
    alertText: alert,
  };
}

export async function getAllProgress(refDate?: Date): Promise<CategoryProgress[]> {
  const cats = await listCategories();
  return Promise.all(cats.map(c => getCategoryProgress(c, refDate)));
}

function makeAlert(
  cat: ManualCategory,
  monthCents: number, yearCents: number,
  monthlyPct?: number, yearlyPct?: number,
): string {
  const parts: string[] = [];
  if (cat.monthlyBudgetCents && monthlyPct !== undefined) {
    if (monthlyPct >= 1) parts.push(`⚠️本月${cat.name}已超${((monthlyPct - 1) * 100).toFixed(0)}%`);
    else if (monthlyPct >= 0.8) parts.push(`⚠️本月${cat.name}已用${(monthlyPct * 100).toFixed(0)}%（${fmtAmount(monthCents)}/${fmtAmount(cat.monthlyBudgetCents)}）`);
    else parts.push(`本月${cat.name} ${fmtAmount(monthCents)}/${fmtAmount(cat.monthlyBudgetCents)}（${(monthlyPct * 100).toFixed(0)}%）`);
  }
  if (cat.yearlyBudgetCents && yearlyPct !== undefined) {
    parts.push(`年度 ${fmtAmount(yearCents)}/${fmtAmount(cat.yearlyBudgetCents)}（${(yearlyPct * 100).toFixed(0)}%）`);
  }
  return parts.length ? parts.join(' · ') : `${cat.name}: ${fmtAmount(monthCents)}`;
}
