/**
 * Bağlantıyı paylaş: web'de sayfanın adresini panoya kopyalar, telefonda sistemin paylaşım
 * penceresini açar. Öneri, dilekçe ve etkinlik sayfalarında.
 */

import * as Linking from 'expo-linking';
import { useState } from 'react';
import { Platform, Share } from 'react-native';

import { Button } from '@/components/paper';

export function ShareLink({ path, title }: { path: string; title: string }) {
  const [copied, setCopied] = useState(false);
  const share = async () => {
    if (Platform.OS === 'web') {
      const url = `${window.location.origin}${path}`;
      try {
        await navigator.clipboard.writeText(url);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch {
        window.prompt('Bağlantıyı kopyalayın:', url);
      }
      return;
    }
    await Share.share({ message: `${title}\n${Linking.createURL(path)}` });
  };
  return (
    <Button
      label={copied ? 'Bağlantı kopyalandı ✓' : Platform.OS === 'web' ? 'Bağlantıyı kopyala' : 'Paylaş'}
      variant="quiet"
      onPress={share}
    />
  );
}
