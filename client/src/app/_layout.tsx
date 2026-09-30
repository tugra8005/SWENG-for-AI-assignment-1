import {
  IBMPlexMono_400Regular,
  IBMPlexMono_500Medium,
  IBMPlexMono_700Bold,
} from '@expo-google-fonts/ibm-plex-mono';
import {
  Newsreader_400Regular,
  Newsreader_400Regular_Italic,
  Newsreader_500Medium,
  Newsreader_700Bold,
  Newsreader_800ExtraBold,
} from '@expo-google-fonts/newsreader';
import { VT323_400Regular } from '@expo-google-fonts/vt323';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { Platform } from 'react-native';

import { DevSwitcher } from '@/components/dev-switcher';
import { AuthProvider } from '@/lib/auth';
import { ClockProvider } from '@/lib/clock';
import { NotificationsProvider } from '@/lib/notifications';
import { paper } from '@/theme/tokens';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [loaded] = useFonts({
    Newsreader_400Regular,
    Newsreader_400Regular_Italic,
    Newsreader_500Medium,
    Newsreader_700Bold,
    Newsreader_800ExtraBold,
    IBMPlexMono_400Regular,
    IBMPlexMono_500Medium,
    IBMPlexMono_700Bold,
    VT323_400Regular,
  });

  useEffect(() => {
    if (loaded) SplashScreen.hideAsync();
  }, [loaded]);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    // Büyük harf dönüşümü Türkçe kurallarla yapılsın (i → İ).
    document.documentElement.lang = 'tr';
    // Chrome yer tutucuyu satır kutusuna kırpar; "İ"nin noktası düşer ("ör. İstanbul" → "Istanbul").
    const style = document.createElement('style');
    style.textContent = 'input::placeholder, textarea::placeholder { overflow: visible; }';
    document.head.appendChild(style);
    return () => style.remove();
  }, []);

  if (!loaded) return null;

  return (
    <AuthProvider>
      <NotificationsProvider>
      <ClockProvider>
        <StatusBar style="dark" />
        <Stack
          screenOptions={{
            headerShown: false,
            animation: 'fade',
            contentStyle: { backgroundColor: paper.bg },
          }}
        >
          {/* Yolsuz açılışta (Android'de Expo Go) ilk ekran Meydan olsun: ilk tanımlanan ekran. */}
          <Stack.Screen name="index" />
          <Stack.Screen name="mahzen" options={{ contentStyle: { backgroundColor: '#000' } }} />
        </Stack>
        <DevSwitcher />
      </ClockProvider>
      </NotificationsProvider>
    </AuthProvider>
  );
}
