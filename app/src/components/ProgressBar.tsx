import React from 'react';
import { View, StyleSheet } from 'react-native';

interface Props {
  pct: number; // 0–1+
  color?: string;
  height?: number;
}

export function ProgressBar({ pct, color, height = 6 }: Props) {
  const fill = Math.min(pct, 1);
  const barColor = pct >= 1 ? '#ef4444' : pct >= 0.8 ? '#f59e0b' : (color ?? '#3b82f6');
  return (
    <View style={[styles.track, { height }]}>
      <View style={[styles.fill, { width: `${fill * 100}%`, backgroundColor: barColor, height }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  track: { backgroundColor: '#e5e7eb', borderRadius: 99, overflow: 'hidden', width: '100%' },
  fill: { borderRadius: 99 },
});
