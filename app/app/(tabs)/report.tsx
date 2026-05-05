import React, { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, Share, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Card } from '../../src/components/Card';
import { ProgressBar } from '../../src/components/ProgressBar';
import { MonthPicker } from '../../src/components/MonthPicker';
import { useStore } from '../../src/hooks/useStore';
import { fmtAmount, fmtAmountShort, fmtPct } from '../../src/utils/format';

export default function ReportScreen() {
  const { selectedMonth, setSelectedMonth, total, categoryProgresses, expenseTxns, incomeTxns, isLoading, refresh } = useStore();

  useEffect(() => { refresh(); }, [selectedMonth]);

  async function exportMarkdown() {
    const lines: string[] = [
      `# MZ 记账 月度报告 ${selectedMonth}`,
      '',
      '## 概览',
      `| 项目 | 金额 |`,
      `|---|---|`,
      `| 当月总支出 | ${total ? fmtAmount(total.totalExpenseCents) : '—'} |`,
      `| 原始支出 | ${total ? fmtAmount(total.rawExpenseCents) : '—'} |`,
      `| 收入抵充 | ${total ? fmtAmount(total.offsetIncomeCents) : '—'} |`,
      `| 当月收入 | ${total ? fmtAmount(total.totalIncomeCents) : '—'} |`,
      `| 支出笔数 | ${expenseTxns.length} 笔 |`,
      `| 收入笔数 | ${incomeTxns.length} 笔 |`,
      '',
      '## 重点类目',
      '',
    ];

    for (const p of categoryProgresses) {
      lines.push(`### ${p.icon} ${p.name}`);
      lines.push(`- 本月支出：${fmtAmount(p.monthSpentCents)}`);
      if (p.monthlyBudgetCents) {
        lines.push(`- 月度预算：${fmtAmount(p.monthlyBudgetCents)}（已用 ${fmtPct(p.monthlyPct)}）`);
      }
      if (p.yearlyBudgetCents) {
        lines.push(`- 年度预算：${fmtAmount(p.yearlyBudgetCents)}（已用 ${fmtPct(p.yearlyPct)}）`);
      }
      lines.push('');
    }

    const text = lines.join('\n');
    try {
      await Share.share({ message: text, title: `MZ报告_${selectedMonth}.md` });
    } catch (e) {
      Alert.alert('导出失败', String(e));
    }
  }

  async function exportJson() {
    const data = {
      month: selectedMonth,
      generatedAt: new Date().toISOString(),
      total,
      expenseCount: expenseTxns.length,
      incomeCount: incomeTxns.length,
      categoryProgresses,
    };
    try {
      await Share.share({
        message: JSON.stringify(data, null, 2),
        title: `MZ报告_${selectedMonth}.json`,
      });
    } catch (e) {
      Alert.alert('导出失败', String(e));
    }
  }

  const hasData = !!total;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView style={styles.scroll}>
        <View style={styles.header}>
          <Text style={styles.title}>月度报告</Text>
          <MonthPicker value={selectedMonth} onChange={setSelectedMonth} />
        </View>

        {/* Summary card */}
        <Card>
          <Text style={styles.sectionTitle}>📊 本月概览</Text>
          {!hasData ? (
            <Text style={styles.empty}>暂无数据</Text>
          ) : (
            <>
              <SummaryRow label="当月净支出" value={fmtAmount(total!.totalExpenseCents)} bold />
              <SummaryRow label="原始支出" value={fmtAmount(total!.rawExpenseCents)} />
              <SummaryRow label="收入抵充" value={`-${fmtAmount(total!.offsetIncomeCents)}`} color="#22c55e" />
              <SummaryRow label="当月收入" value={fmtAmount(total!.totalIncomeCents)} color="#22c55e" />
              <View style={styles.divider} />
              <SummaryRow label="支出笔数" value={`${expenseTxns.length} 笔`} />
              <SummaryRow label="收入笔数" value={`${incomeTxns.length} 笔`} />
            </>
          )}
        </Card>

        {/* Category breakdown */}
        {categoryProgresses.length > 0 && (
          <Card>
            <Text style={styles.sectionTitle}>📌 类目明细</Text>
            {categoryProgresses.map(p => (
              <View key={p.categoryId} style={styles.catRow}>
                <View style={styles.catHeader}>
                  <Text style={styles.catName}>{p.icon} {p.name}</Text>
                  <Text style={styles.catAmount}>{fmtAmountShort(p.monthSpentCents)}</Text>
                </View>
                {p.monthlyBudgetCents && p.monthlyPct !== undefined && (
                  <>
                    <ProgressBar pct={p.monthlyPct} height={4} />
                    <View style={styles.catBudgetRow}>
                      <Text style={styles.catBudgetText}>
                        月预算 {fmtAmount(p.monthlyBudgetCents)} · 已用 {fmtPct(p.monthlyPct)}
                      </Text>
                    </View>
                  </>
                )}
                {p.yearlyBudgetCents && (
                  <Text style={styles.yearBudget}>
                    年预算 {fmtAmount(p.yearlyBudgetCents)} · 已用 {fmtPct(p.yearlyPct)}（{fmtAmountShort(p.yearSpentCents)}）
                  </Text>
                )}
                {p.alertText.startsWith('⚠️') && (
                  <Text style={styles.alertText}>{p.alertText}</Text>
                )}
              </View>
            ))}
          </Card>
        )}

        {/* Export buttons */}
        <Card>
          <Text style={styles.sectionTitle}>📤 导出报告</Text>
          <View style={styles.exportRow}>
            <TouchableOpacity style={styles.exportBtn} onPress={exportMarkdown}>
              <Ionicons name="document-text-outline" size={18} color="#3b82f6" />
              <Text style={styles.exportBtnText}>Markdown</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.exportBtn} onPress={exportJson}>
              <Ionicons name="code-outline" size={18} color="#3b82f6" />
              <Text style={styles.exportBtnText}>JSON</Text>
            </TouchableOpacity>
          </View>
        </Card>

        <View style={{ height: 32 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function SummaryRow({
  label, value, bold, color,
}: { label: string; value: string; bold?: boolean; color?: string }) {
  return (
    <View style={styles.summaryRow}>
      <Text style={styles.summaryLabel}>{label}</Text>
      <Text style={[styles.summaryValue, bold && styles.summaryBold, color ? { color } : null]}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f3f4f6' },
  scroll: { flex: 1 },
  header: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4 },
  title: { fontSize: 22, fontWeight: '700', color: '#111827', marginBottom: 4 },
  sectionTitle: { fontSize: 15, fontWeight: '700', color: '#111827', marginBottom: 12 },
  empty: { color: '#9ca3af', textAlign: 'center', paddingVertical: 12 },
  summaryRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 6 },
  summaryLabel: { fontSize: 14, color: '#6b7280' },
  summaryValue: { fontSize: 14, color: '#374151', fontWeight: '500' },
  summaryBold: { fontSize: 18, fontWeight: '700', color: '#111827' },
  divider: { height: 1, backgroundColor: '#f3f4f6', marginVertical: 6 },
  catRow: { marginBottom: 16 },
  catHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  catName: { fontSize: 14, fontWeight: '500', color: '#374151' },
  catAmount: { fontSize: 14, fontWeight: '600', color: '#111827' },
  catBudgetRow: { marginTop: 4 },
  catBudgetText: { fontSize: 12, color: '#9ca3af' },
  yearBudget: { fontSize: 12, color: '#9ca3af', marginTop: 2 },
  alertText: { fontSize: 12, color: '#f59e0b', marginTop: 4 },
  exportRow: { flexDirection: 'row', gap: 12 },
  exportBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, borderWidth: 1, borderColor: '#3b82f6', borderRadius: 8, paddingVertical: 10 },
  exportBtnText: { fontSize: 14, color: '#3b82f6', fontWeight: '500' },
});
