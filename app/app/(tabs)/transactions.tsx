import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet,
  RefreshControl, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Card } from '../../src/components/Card';
import { useStore } from '../../src/hooks/useStore';
import { MonthPicker } from '../../src/components/MonthPicker';
import { setInclusion } from '../../src/services/inclusionManager';
import { fmtAmount, fmtDate } from '../../src/utils/format';
import type { InclusionState, Transaction } from '../../src/models';

type Tab = 'expense' | 'income' | 'group';

const INCLUSION_LABELS: Record<InclusionState, string> = {
  auto: '自动',
  included: '计入',
  excluded: '排除',
  offset: '抵充',
};

const INCLUSION_COLORS: Record<InclusionState, string> = {
  auto: '#9ca3af',
  included: '#22c55e',
  excluded: '#ef4444',
  offset: '#f59e0b',
};

const SOURCE_LABEL: Record<string, string> = {
  wechat: '微信', alipay: '支付宝', bank_pingan: '平安银行', bank_icbc: '工行',
};

export default function TransactionsScreen() {
  const { selectedMonth, setSelectedMonth, expenseTxns, incomeTxns, groupTxns, isLoading, refresh } = useStore();
  const [tab, setTab] = useState<Tab>('expense');

  const txns = tab === 'expense' ? expenseTxns : tab === 'income' ? incomeTxns : groupTxns;

  async function cycleInclusion(t: Transaction) {
    const cycles: Record<InclusionState, InclusionState> =
      t.direction === 'income'
        ? { auto: 'excluded', included: 'excluded', excluded: 'offset', offset: 'auto' }
        : { auto: 'excluded', included: 'auto', excluded: 'included', offset: 'auto' };
    const next = cycles[t.inclusion];
    try {
      await setInclusion(t.id, next);
      await refresh();
    } catch (e) {
      Alert.alert('错误', String(e));
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>账单明细</Text>
        <MonthPicker value={selectedMonth} onChange={setSelectedMonth} />
      </View>

      {/* Tabs */}
      <View style={styles.tabBar}>
        {(['expense', 'income', 'group'] as Tab[]).map(k => (
          <TouchableOpacity
            key={k}
            style={[styles.tabItem, tab === k && styles.tabActive]}
            onPress={() => setTab(k)}
          >
            <Text style={[styles.tabText, tab === k && styles.tabTextActive]}>
              {k === 'expense' ? `支出 (${expenseTxns.length})` : k === 'income' ? `收入 (${incomeTxns.length})` : `群聊 (${groupTxns.length})`}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <ScrollView
        style={styles.scroll}
        refreshControl={<RefreshControl refreshing={isLoading} onRefresh={refresh} />}
      >
        {txns.length === 0 ? (
          <Card><Text style={styles.empty}>暂无数据</Text></Card>
        ) : (
          <Card style={styles.listCard}>
            {txns.map((t, i) => (
              <TxnRow key={t.id} txn={t} last={i === txns.length - 1} onToggle={() => cycleInclusion(t)} />
            ))}
          </Card>
        )}
        <View style={{ height: 32 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function TxnRow({ txn, last, onToggle }: { txn: Transaction; last: boolean; onToggle: () => void }) {
  const amtColor = txn.direction === 'income' ? '#22c55e' : '#111827';
  const inclColor = INCLUSION_COLORS[txn.inclusion];

  return (
    <View style={[styles.row, !last && styles.rowBorder]}>
      <View style={styles.rowLeft}>
        <Text style={styles.rowCounterparty} numberOfLines={1}>
          {txn.counterparty || txn.description || '—'}
        </Text>
        <Text style={styles.rowMeta}>
          {fmtDate(txn.txnTime)}
          {txn.source ? ` · ${SOURCE_LABEL[txn.source] ?? txn.source}` : ''}
          {txn.accountName ? ` · ${txn.accountName}` : ''}
        </Text>
        {txn.description && txn.counterparty ? (
          <Text style={styles.rowDesc} numberOfLines={1}>{txn.description}</Text>
        ) : null}
      </View>

      <View style={styles.rowRight}>
        <Text style={[styles.rowAmount, { color: amtColor }]}>
          {txn.direction === 'income' ? '+' : ''}{fmtAmount(txn.amountCents)}
        </Text>
        <TouchableOpacity
          style={[styles.inclBadge, { borderColor: inclColor }]}
          onPress={onToggle}
        >
          <Text style={[styles.inclText, { color: inclColor }]}>
            {INCLUSION_LABELS[txn.inclusion]}
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f3f4f6' },
  header: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 0 },
  title: { fontSize: 22, fontWeight: '700', color: '#111827', marginBottom: 4 },
  tabBar: { flexDirection: 'row', backgroundColor: '#fff', borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  tabItem: { flex: 1, paddingVertical: 10, alignItems: 'center' },
  tabActive: { borderBottomWidth: 2, borderBottomColor: '#3b82f6' },
  tabText: { fontSize: 13, color: '#9ca3af', fontWeight: '500' },
  tabTextActive: { color: '#3b82f6' },
  scroll: { flex: 1 },
  listCard: { padding: 0 },
  row: { flexDirection: 'row', alignItems: 'flex-start', paddingHorizontal: 14, paddingVertical: 12 },
  rowBorder: { borderBottomWidth: 1, borderBottomColor: '#f3f4f6' },
  rowLeft: { flex: 1, marginRight: 8 },
  rowCounterparty: { fontSize: 14, fontWeight: '500', color: '#111827' },
  rowMeta: { fontSize: 12, color: '#9ca3af', marginTop: 2 },
  rowDesc: { fontSize: 12, color: '#6b7280', marginTop: 2 },
  rowRight: { alignItems: 'flex-end', gap: 6 },
  rowAmount: { fontSize: 14, fontWeight: '600' },
  inclBadge: { borderWidth: 1, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 },
  inclText: { fontSize: 11, fontWeight: '500' },
  empty: { color: '#9ca3af', textAlign: 'center', padding: 24 },
});
