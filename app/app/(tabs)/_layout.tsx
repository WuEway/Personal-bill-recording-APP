import React from 'react';
import { Tabs } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

function tabIcon(name: IconName, focused: boolean) {
  return <Ionicons name={focused ? name : `${name}-outline` as IconName} size={24} color={focused ? '#3b82f6' : '#9ca3af'} />;
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: {
          backgroundColor: '#ffffff',
          borderTopColor: '#e5e7eb',
          height: 60,
          paddingBottom: 8,
        },
        tabBarActiveTintColor: '#3b82f6',
        tabBarInactiveTintColor: '#9ca3af',
        tabBarLabelStyle: { fontSize: 11, fontWeight: '500' },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: '总览', tabBarIcon: ({ focused }) => tabIcon('home', focused) }}
      />
      <Tabs.Screen
        name="import"
        options={{ title: '导入', tabBarIcon: ({ focused }) => tabIcon('cloud-upload', focused) }}
      />
      <Tabs.Screen
        name="transactions"
        options={{ title: '账单', tabBarIcon: ({ focused }) => tabIcon('list', focused) }}
      />
      <Tabs.Screen
        name="categories"
        options={{ title: '类目', tabBarIcon: ({ focused }) => tabIcon('bookmark', focused) }}
      />
      <Tabs.Screen
        name="report"
        options={{ title: '报告', tabBarIcon: ({ focused }) => tabIcon('bar-chart', focused) }}
      />
    </Tabs>
  );
}
