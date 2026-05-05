import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet,
  TextInput, Alert, Modal, KeyboardAvoidingView, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { Card } from '../../src/components/Card';
import { ProgressBar } from '../../src/components/ProgressBar';
import {
  listCategories, deactivateCategory, updateCategoryBudget, createCategory,
} from '../../src/db/repositories';
import { getAllProgress } from '../../src/services/categoryService';
import { fmtAmount } from '../../src/utils/format';
import type { CategoryProgress, ManualCategory } from '../../src/models';

export default function CategoriesScreen() {
  const [progresses, setProgresses] = useState<CategoryProgress[]>([]);
  const [categories, setCategories] = useState<ManualCategory[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [editTarget, setEditTarget] = useState<ManualCategory | null>(null);

  const load = useCallback(async () => {
    const [cats, progs] = await Promise.all([listCategories(), getAllProgress()]);
    setCategories(cats);
    setProgresses(progs);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleDeactivate(cat: ManualCategory) {
    Alert.alert('删除类目', `确认删除「${cat.name}」？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除', style: 'destructive', onPress: async () => {
          await deactivateCategory(cat.id);
          await load();
        },
      },
    ]);
  }

  const progressMap = Object.fromEntries(progresses.map(p => [p.categoryId, p]));

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView style={styles.scroll}>
        <View style={styles.headerRow}>
          <Text style={styles.title}>类目管理</Text>
          <TouchableOpacity style={styles.addBtn} onPress={() => setShowAdd(true)}>
            <Ionicons name="add" size={18} color="#fff" />
            <Text style={styles.addBtnText}>新增</Text>
          </TouchableOpacity>
        </View>

        {categories.length === 0 ? (
          <Card><Text style={styles.empty}>暂无类目，点击「新增」添加</Text></Card>
        ) : (
          <Card style={styles.listCard}>
            {categories.map((cat, i) => {
              const prog = progressMap[cat.id];
              return (
                <View key={cat.id} style={[styles.catRow, i < categories.length - 1 && styles.catBorder]}>
                  <View style={styles.catLeft}>
                    <Text style={styles.catIcon}>{cat.icon}</Text>
                    <View style={{ flex: 1 }}>
                      <View style={styles.catNameRow}>
                        <Text style={styles.catName}>{cat.name}</Text>
                        {prog && <Text style={styles.catSpent}>{fmtAmount(prog.monthSpentCents)}</Text>}
                      </View>
                      {cat.monthlyBudgetCents && prog?.monthlyPct !== undefined && (
                        <View style={styles.progressWrap}>
                          <ProgressBar pct={prog.monthlyPct} height={4} />
                          <Text style={styles.budgetText}>
                            {fmtAmount(prog.monthSpentCents)} / {fmtAmount(cat.monthlyBudgetCents)}
                          </Text>
                        </View>
                      )}
                      {!cat.monthlyBudgetCents && (
                        <Text style={styles.noBudget}>未设预算</Text>
                      )}
                    </View>
                  </View>
                  <View style={styles.catActions}>
                    <TouchableOpacity onPress={() => setEditTarget(cat)} style={styles.actionBtn}>
                      <Ionicons name="pencil-outline" size={16} color="#3b82f6" />
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => handleDeactivate(cat)} style={styles.actionBtn}>
                      <Ionicons name="trash-outline" size={16} color="#ef4444" />
                    </TouchableOpacity>
                  </View>
                </View>
              );
            })}
          </Card>
        )}

        <View style={{ height: 32 }} />
      </ScrollView>

      {/* Add category modal */}
      <CategoryModal
        visible={showAdd}
        onClose={() => setShowAdd(false)}
        onSave={async (name, icon, monthly, yearly) => {
          if (!name.trim()) return;
          await createCategory(
            name.trim(), icon.trim(),
            monthly ? Math.round(monthly * 100) : undefined,
            yearly ? Math.round(yearly * 100) : undefined,
          );
          setShowAdd(false);
          await load();
        }}
      />

      {/* Edit budget modal */}
      {editTarget && (
        <CategoryModal
          visible={true}
          initial={editTarget}
          onClose={() => setEditTarget(null)}
          onSave={async (_name, _icon, monthly, yearly) => {
            await updateCategoryBudget(
              editTarget.id,
              monthly ? Math.round(monthly * 100) : undefined,
              yearly ? Math.round(yearly * 100) : undefined,
            );
            setEditTarget(null);
            await load();
          }}
        />
      )}
    </SafeAreaView>
  );
}

interface ModalProps {
  visible: boolean;
  initial?: ManualCategory;
  onClose: () => void;
  onSave: (name: string, icon: string, monthly?: number, yearly?: number) => Promise<void>;
}

function CategoryModal({ visible, initial, onClose, onSave }: ModalProps) {
  const [name, setName] = useState(initial?.name ?? '');
  const [icon, setIcon] = useState(initial?.icon ?? '');
  const [monthly, setMonthly] = useState(
    initial?.monthlyBudgetCents ? String(initial.monthlyBudgetCents / 100) : '',
  );
  const [yearly, setYearly] = useState(
    initial?.yearlyBudgetCents ? String(initial.yearlyBudgetCents / 100) : '',
  );
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      await onSave(
        name, icon,
        monthly ? parseFloat(monthly) : undefined,
        yearly ? parseFloat(yearly) : undefined,
      );
    } catch (e) {
      Alert.alert('错误', String(e));
    } finally {
      setSaving(false);
    }
  }

  const isEdit = !!initial;

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <SafeAreaView style={styles.modalSafe} edges={['top']}>
          <View style={styles.modalHeader}>
            <TouchableOpacity onPress={onClose}>
              <Text style={styles.modalCancel}>取消</Text>
            </TouchableOpacity>
            <Text style={styles.modalTitle}>{isEdit ? '编辑预算' : '新增类目'}</Text>
            <TouchableOpacity onPress={handleSave} disabled={saving}>
              <Text style={[styles.modalSave, saving && { opacity: 0.5 }]}>保存</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.modalScroll} keyboardShouldPersistTaps="handled">
            {!isEdit && (
              <>
                <Field label="类目名称" value={name} onChange={setName} placeholder="例：旅游" />
                <Field label="图标 Emoji" value={icon} onChange={setIcon} placeholder="例：✈️" />
              </>
            )}
            {isEdit && (
              <View style={styles.editNameRow}>
                <Text style={styles.editIcon}>{initial?.icon}</Text>
                <Text style={styles.editName}>{initial?.name}</Text>
              </View>
            )}
            <Field
              label="月度预算 (元)" value={monthly} onChange={setMonthly}
              placeholder="留空=不限" keyboardType="numeric"
            />
            <Field
              label="年度预算 (元)" value={yearly} onChange={setYearly}
              placeholder="留空=不限" keyboardType="numeric"
            />
          </ScrollView>
        </SafeAreaView>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function Field({
  label, value, onChange, placeholder, keyboardType,
}: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; keyboardType?: 'default' | 'numeric';
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        style={styles.fieldInput}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor="#9ca3af"
        keyboardType={keyboardType ?? 'default'}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f3f4f6' },
  scroll: { flex: 1 },
  headerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 12 },
  title: { fontSize: 22, fontWeight: '700', color: '#111827' },
  addBtn: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#3b82f6', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7, gap: 4 },
  addBtnText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  listCard: { padding: 0 },
  catRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 12 },
  catBorder: { borderBottomWidth: 1, borderBottomColor: '#f3f4f6' },
  catLeft: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 10 },
  catIcon: { fontSize: 24, width: 32 },
  catNameRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  catName: { fontSize: 15, fontWeight: '500', color: '#111827' },
  catSpent: { fontSize: 13, color: '#6b7280' },
  progressWrap: { marginTop: 6, gap: 4 },
  budgetText: { fontSize: 11, color: '#9ca3af' },
  noBudget: { fontSize: 12, color: '#d1d5db', marginTop: 2 },
  catActions: { flexDirection: 'row', gap: 4 },
  actionBtn: { padding: 6 },
  empty: { color: '#9ca3af', textAlign: 'center', padding: 24 },

  modalSafe: { flex: 1, backgroundColor: '#fff' },
  modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: '#e5e7eb' },
  modalTitle: { fontSize: 16, fontWeight: '600', color: '#111827' },
  modalCancel: { fontSize: 16, color: '#6b7280' },
  modalSave: { fontSize: 16, color: '#3b82f6', fontWeight: '600' },
  modalScroll: { padding: 16 },
  editNameRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 20, paddingBottom: 16, borderBottomWidth: 1, borderBottomColor: '#f3f4f6' },
  editIcon: { fontSize: 32 },
  editName: { fontSize: 20, fontWeight: '600', color: '#111827' },
  field: { marginBottom: 16 },
  fieldLabel: { fontSize: 13, color: '#6b7280', marginBottom: 6, fontWeight: '500' },
  fieldInput: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, fontSize: 15, color: '#111827', backgroundColor: '#fafafa' },
});
