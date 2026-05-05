import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet,
  ActivityIndicator, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Card } from '../../src/components/Card';
import { pickAndImport } from '../../src/services/importService';
import { runDedupe } from '../../src/services/dedupeEngine';
import { useStore } from '../../src/hooks/useStore';
import { monthRange } from '../../src/utils/format';
import type { ImportedFile } from '../../src/models';

const SOURCE_INFO = [
  { key: 'wechat', label: '微信支付账单', icon: '💬', ext: '.xlsx / .csv', hint: '微信→我→服务→钱包→账单→常见问题→下载账单' },
  { key: 'alipay', label: '支付宝交易明细', icon: '🔵', ext: '.csv', hint: '支付宝→账单→右上角→开具交易流水证明' },
];

export default function ImportScreen() {
  const { refresh, refreshFiles, importedFiles, selectedMonth } = useStore();
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');

  useEffect(() => { refreshFiles(); }, []);

  async function handleImport(sourceHint: 'wechat' | 'alipay') {
    setLoading(true);
    setStatus('');
    try {
      const { cancelled, results } = await pickAndImport(sourceHint);
      if (cancelled) { setStatus('已取消'); return; }

      const r = results[0];
      if (!r) return;

      if (r.skippedDuplicate) {
        setStatus('⚠️ 该文件已导入过，跳过。');
        return;
      }
      if (r.error) {
        setStatus(`❌ ${r.error}`);
        return;
      }

      setStatus(`✅ 导入完成：解析 ${r.rowsParsed} 行，入库 ${r.rowsInserted} 条，内部转账 ${r.internalTransfersDetected} 笔`);

      // Auto-run dedupe for the selected month
      setLoading(true);
      const { start, end } = monthRange(selectedMonth);
      await runDedupe(start, end);

      await Promise.all([refresh(), refreshFiles()]);
    } catch (e) {
      setStatus(`❌ 错误：${String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleDedupe() {
    setLoading(true);
    try {
      const { start, end } = monthRange(selectedMonth);
      const stats = await runDedupe(start, end);
      setStatus(`✅ 去重完成：新建 ${stats.created} 笔，银行影子关联 ${stats.bankLinkedAsShadow} 笔`);
      await refresh();
    } catch (e) {
      setStatus(`❌ ${String(e)}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView style={styles.scroll}>
        <Text style={styles.title}>导入账单</Text>

        {/* Source buttons */}
        {SOURCE_INFO.map(s => (
          <Card key={s.key} style={styles.sourceCard}>
            <View style={styles.sourceHeader}>
              <Text style={styles.sourceIcon}>{s.icon}</Text>
              <View style={{ flex: 1 }}>
                <Text style={styles.sourceName}>{s.label}</Text>
                <Text style={styles.sourceExt}>{s.ext}</Text>
              </View>
              <TouchableOpacity
                style={styles.importBtn}
                onPress={() => handleImport(s.key as 'wechat' | 'alipay')}
                disabled={loading}
              >
                <Ionicons name="add" size={18} color="#fff" />
                <Text style={styles.importBtnText}>选择文件</Text>
              </TouchableOpacity>
            </View>
            <Text style={styles.hint}>{s.hint}</Text>
          </Card>
        ))}

        {/* Status */}
        {loading && <ActivityIndicator style={{ margin: 16 }} color="#3b82f6" />}
        {!!status && (
          <Card>
            <Text style={styles.statusText}>{status}</Text>
          </Card>
        )}

        {/* Re-dedupe button */}
        <TouchableOpacity style={styles.dedupeBtn} onPress={handleDedupe} disabled={loading}>
          <Ionicons name="git-merge" size={16} color="#3b82f6" />
          <Text style={styles.dedupeBtnText}>重新执行去重（{selectedMonth}）</Text>
        </TouchableOpacity>

        {/* Import history */}
        {importedFiles.length > 0 && (
          <Card>
            <Text style={styles.sectionTitle}>导入历史</Text>
            {importedFiles.map(f => <FileRow key={f.id} file={f} />)}
          </Card>
        )}

        <View style={{ height: 32 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function FileRow({ file }: { file: ImportedFile }) {
  const sourceLabel: Record<string, string> = { wechat: '微信', alipay: '支付宝', bank_pingan: '平安', bank_icbc: '工行' };
  return (
    <View style={styles.fileRow}>
      <View style={{ flex: 1 }}>
        <Text style={styles.fileName} numberOfLines={1}>{file.filePath}</Text>
        <Text style={styles.fileMeta}>
          {sourceLabel[file.source] ?? file.source} · {file.rowCount} 条
          {file.periodStart ? ` · ${file.periodStart}→${file.periodEnd}` : ''}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f3f4f6' },
  scroll: { flex: 1 },
  title: { fontSize: 22, fontWeight: '700', color: '#111827', padding: 16, paddingBottom: 8 },
  sourceCard: { marginBottom: 0 },
  sourceHeader: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  sourceIcon: { fontSize: 28, width: 40 },
  sourceName: { fontSize: 15, fontWeight: '600', color: '#111827' },
  sourceExt: { fontSize: 12, color: '#9ca3af', marginTop: 2 },
  importBtn: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#3b82f6', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, gap: 4 },
  importBtnText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  hint: { fontSize: 12, color: '#6b7280', marginTop: 10, lineHeight: 18 },
  statusText: { fontSize: 14, color: '#374151', lineHeight: 22 },
  dedupeBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, margin: 16, padding: 12, backgroundColor: '#eff6ff', borderRadius: 10 },
  dedupeBtnText: { fontSize: 14, color: '#3b82f6', fontWeight: '500' },
  sectionTitle: { fontSize: 15, fontWeight: '700', color: '#111827', marginBottom: 10 },
  fileRow: { flexDirection: 'row', paddingVertical: 8, borderTopWidth: 1, borderTopColor: '#f3f4f6' },
  fileName: { fontSize: 13, color: '#374151' },
  fileMeta: { fontSize: 12, color: '#9ca3af', marginTop: 2 },
});
