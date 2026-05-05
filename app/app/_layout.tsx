import React, { useEffect, useState } from 'react';
import { View, Text, ActivityIndicator, StyleSheet } from 'react-native';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { initDb } from '../src/db/database';
import { useStore } from '../src/hooks/useStore';

export default function RootLayout() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const refresh = useStore(s => s.refresh);

  useEffect(() => {
    initDb()
      .then(() => refresh())
      .then(() => setReady(true))
      .catch(e => setError(String(e)));
  }, []);

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.err}>初始化失败：{error}</Text>
      </View>
    );
  }
  if (!ready) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#3b82f6" />
        <Text style={styles.loading}>加载中…</Text>
      </View>
    );
  }

  return (
    <SafeAreaProvider>
      <StatusBar style="auto" />
      <Stack screenOptions={{ headerShown: false }} />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#f9fafb' },
  loading: { marginTop: 12, color: '#6b7280', fontSize: 14 },
  err: { color: '#ef4444', textAlign: 'center', padding: 24 },
});
