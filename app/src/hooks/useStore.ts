import { create } from 'zustand';
import { currentMonth, monthRange } from '../utils/format';
import { computeTotal } from '../services/inclusionManager';
import { getAllProgress } from '../services/categoryService';
import { listTransactionsInPeriod, listImportedFiles } from '../db/repositories';
import type { CategoryProgress, ImportedFile, MonthlyTotal, Transaction } from '../models';

interface AppState {
  // Month selector
  selectedMonth: string;
  setSelectedMonth: (m: string) => void;

  // Data
  total: MonthlyTotal | null;
  expenseTxns: Transaction[];
  incomeTxns: Transaction[];
  groupTxns: Transaction[];
  categoryProgresses: CategoryProgress[];
  importedFiles: ImportedFile[];
  isLoading: boolean;

  // Actions
  refresh: () => Promise<void>;
  refreshFiles: () => Promise<void>;
}

export const useStore = create<AppState>((set, get) => ({
  selectedMonth: currentMonth(),
  setSelectedMonth: (m) => { set({ selectedMonth: m }); get().refresh(); },

  total: null,
  expenseTxns: [],
  incomeTxns: [],
  groupTxns: [],
  categoryProgresses: [],
  importedFiles: [],
  isLoading: false,

  refresh: async () => {
    set({ isLoading: true });
    try {
      const { start, end } = monthRange(get().selectedMonth);
      const [total, all, progresses] = await Promise.all([
        computeTotal(start, end),
        listTransactionsInPeriod(start, end),
        getAllProgress(),
      ]);
      set({
        total,
        expenseTxns: all.filter(t => t.direction === 'expense' && !t.isGroupPayment),
        incomeTxns: all.filter(t => t.direction === 'income' && !t.isGroupPayment),
        groupTxns: all.filter(t => t.isGroupPayment),
        categoryProgresses: progresses,
      });
    } finally {
      set({ isLoading: false });
    }
  },

  refreshFiles: async () => {
    const files = await listImportedFiles();
    set({ importedFiles: files });
  },
}));
