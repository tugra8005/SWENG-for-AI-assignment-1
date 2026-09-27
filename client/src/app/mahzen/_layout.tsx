import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { CrtProvider } from '@/components/cellar';
import { cellar } from '@/theme/tokens';

export default function CellarLayout() {
  return (
    <CrtProvider>
      <StatusBar style="light" />
      <Stack screenOptions={{ headerShown: false, animation: 'fade', contentStyle: { backgroundColor: cellar.bg } }} />
    </CrtProvider>
  );
}
