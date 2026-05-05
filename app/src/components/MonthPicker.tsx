import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface Props {
  value: string; // 'YYYY-MM'
  onChange: (m: string) => void;
}

export function MonthPicker({ value, onChange }: Props) {
  const [y, m] = value.split('-').map(Number);

  const prev = () => {
    const nm = m === 1 ? 12 : m - 1;
    const ny = m === 1 ? y - 1 : y;
    onChange(`${ny}-${String(nm).padStart(2, '0')}`);
  };
  const next = () => {
    const nm = m === 12 ? 1 : m + 1;
    const ny = m === 12 ? y + 1 : y;
    const candidate = `${ny}-${String(nm).padStart(2, '0')}`;
    // Don't allow future months
    if (candidate <= new Date().toISOString().slice(0, 7)) onChange(candidate);
  };

  return (
    <View style={styles.row}>
      <TouchableOpacity onPress={prev} style={styles.btn}>
        <Ionicons name="chevron-back" size={20} color="#6b7280" />
      </TouchableOpacity>
      <Text style={styles.label}>{y}年{m}月</Text>
      <TouchableOpacity onPress={next} style={styles.btn}>
        <Ionicons name="chevron-forward" size={20} color="#6b7280" />
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 4 },
  btn: { padding: 8 },
  label: { fontSize: 17, fontWeight: '600', color: '#111827', minWidth: 90, textAlign: 'center' },
});
