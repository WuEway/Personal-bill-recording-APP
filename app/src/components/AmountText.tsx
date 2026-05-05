import React from 'react';
import { Text, type TextStyle } from 'react-native';
import { fmtAmount } from '../utils/format';

interface Props {
  cents: number;
  style?: TextStyle;
  colored?: boolean; // green = income, red = expense
  direction?: 'expense' | 'income';
}

export function AmountText({ cents, style, colored, direction }: Props) {
  const color = colored
    ? direction === 'income' ? '#22c55e' : '#ef4444'
    : undefined;
  return (
    <Text style={[{ fontVariant: ['tabular-nums'] }, color ? { color } : null, style]}>
      {fmtAmount(cents)}
    </Text>
  );
}
