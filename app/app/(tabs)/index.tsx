import React from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useStore } from '../../src/hooks/useStore';
import { Card } from '../../src/components/Card';
import { MonthPicker } from '../../src/components/MonthPicker';
import { ProgressBar } from '../../src/components/ProgressBar';
import { fmtAmount, fmtAmountShort } from '../../src/utils/format';

export default function DashboardScreen() {
  const { selectedMonth, setSelectedMonth, total, categoryProgresses, refresh, isLoading } = useStore();

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView
        style={styles.scroll}
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refresh} />}
      >
        {/* Month picker */}
        <View style={styles.header}>
          <Text style={styles.appName}>MZ 记账</Text>
          <MonthPicker value={selectedMonth} onChange={setSelectedMonth} />
        </View>

        {/* Total card */}
        <Card style={styles.totalCard}>
          <Text style={styles.totalLabel}>当月总支出</Text>
          <Text style={styles.totalAmount}>
            {total ? fmtAmount(total.totalExpenseCents) : '¥—'}
          </Text>
          {total && (
            <View style={styles.totalRow}>
              <View style={styles.totalItem}>
                <Text style={styles.subLabel}>原始支出</Text>
                <Text style={styles.subValue}>{fmtAmount(total.rawExpenseCents)}</Text>
              </View>
              <View style={styles.divider} />
              <View style={styles.totalItem}>
                <Text style={styles.subLabel}>收入抵充</Text>
                <Text style={[styles.subValue, { color: '#22c55e' }]}>
                  -{fmtAmount(total.offsetIncomeCents)}
                </Text>
              </View>
              <View style={styles.divider} />
              <View style={styles.totalItem}>
                <Text style={styles.subLabel}>当月收入</Text>
                <Text style={[styles.subValue, { color: '#22c55e' }]}>
                  {fmtAmount(total.totalIncomeCents)}
                </Text>
              </View>
            </View>
          )}
        </Card>

        {/* Category progresses */}
        {categoryProgresses.length > 0 && (
          <Card>
            <Text style={styles.sectionTitle}>📌 重点类目</Text>
            {categoryProgresses.map(p => (
              <View key={p.categoryId} style={styles.catRow}>
                <View style={styles.catHeader}>
                  <Text style={styles.catName}>{p.icon} {p.name}</Text>
                  <Text style={styles.catAmount}>
                    {fmtAmountShort(p.monthSpentCents)}
                    {p.monthlyBudgetCents ? ` / ${fmtAmountShort(p.monthlyBudgetCents)}` : ''}
                  </Text>
                </View>
                {p.monthlyBudgetCents && p.monthlyPct !== undefined && (
                  <ProgressBar pct={p.monthlyPct} />
                )}
                {p.alertText.startsWith('⚠️') && (
                  <Text style={styles.alertText}>{p.alertText}</Text>
                )}
              </View>
            ))}
          </Card>
        )}

        {/* Quick tips */}
        {!total && (
          <Card>
            <Text style={styles.emptyTitle}>开始使用</Text>
            <Text style={styles.emptyText}>
              前往「导入」页面上传微信或支付宝账单，
              系统将自动解析并去重，给出本月真实支出。
            </Text>
          </Card>
        )}

        <View style={{ height: 24 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f3f4f6' },
  scroll: { flex: 1 },
  header: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 4 },
  appName: { fontSize: 13, color: '#9ca3af', fontWeight: '500', textAlign: 'center' },
  totalCard: { marginTop: 4 },
  totalLabel: { fontSize: 13, color: '#6b7280', marginBottom: 4 },
  totalAmount: { fontSize: 38, fontWeight: '700', color: '#111827', letterSpacing: -1 },
  totalRow: { flexDirection: 'row', marginTop: 16, paddingTop: 16, borderTopWidth: 1, borderTopColor: '#f3f4f6' },
  totalItem: { flex: 1, alignItems: 'center' },
  subLabel: { fontSize: 12, color: '#9ca3af', marginBottom: 4 },
  subValue: { fontSize: 14, fontWeight: '600', color: '#374151' },
  divider: { width: 1, backgroundColor: '#e5e7eb' },
  sectionTitle: { fontSize: 15, fontWeight: '700', color: '#111827', marginBottom: 12 },
  catRow: { marginBottom: 14 },
  catHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 6 },
  catName: { fontSize: 14, fontWeight: '500', color: '#374151' },
  catAmount: { fontSize: 13, color: '#6b7280' },
  alertText: { fontSize: 12, color: '#f59e0b', marginTop: 4 },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: '#111827', marginBottom: 8 },
  emptyText: { fontSize: 14, color: '#6b7280', lineHeight: 22 },
});
