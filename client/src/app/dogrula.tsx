import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { api } from '@/api/client';
import {
  Button,
  ErrorNotice,
  Field,
  H1,
  InfoNotice,
  Kicker,
  Muted,
  Page,
  Rule,
} from '@/components/paper';
import { useApi } from '@/lib/useApi';

export default function Verify() {
  const params = useLocalSearchParams<{ email?: string }>();
  const [email, setEmail] = useState(params.email ?? '');
  const [code, setCode] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [info, setInfo] = useState<string | null>(null);
  const health = useApi<{ ortam?: string }>('/health');

  const submit = async () => {
    setError(null);
    try {
      await api('/auth/verify', { method: 'POST', body: { email, code } });
      router.replace({ pathname: '/giris', params: { dogrulandi: '1' } });
    } catch (e) {
      setError(e);
    }
  };

  const resend = async () => {
    setError(null);
    try {
      const r = await api('/auth/resend', { method: 'POST', body: { email } });
      setInfo(r.message);
    } catch (e) {
      setError(e);
    }
  };

  return (
    <Page>
      <View style={{ maxWidth: 440, width: '100%', alignSelf: 'center' }}>
        <Kicker>Yurttaşlık kaydı · Form 2</Kicker>
        <H1>E-posta doğrulama</H1>
        <Muted>E-posta adresinize gönderilen altı haneli kodu girin.</Muted>
        {health.data?.ortam === 'dev' ? (
          <Muted style={{ fontSize: 13, marginTop: 4 }}>
            Geliştirme ortamı: e-posta gönderilmez; kod sunucu konsoluna basılır (docker compose logs api).
          </Muted>
        ) : null}
        <Rule />
        <Field
          label="E-posta"
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
        />
        <Field
          label="Doğrulama kodu"
          value={code}
          onChangeText={setCode}
          keyboardType="number-pad"
          maxLength={6}
          onSubmitEditing={submit}
        />
        {info ? <InfoNotice>{info}</InfoNotice> : null}
        <ErrorNotice error={error} />
        <View style={{ flexDirection: 'row', gap: 16, alignItems: 'center' }}>
          <Button label="Doğrula" onPress={submit} disabled={!email || code.length !== 6} />
          <Button label="Kodu yeniden gönder" variant="quiet" onPress={resend} disabled={!email} />
        </View>
      </View>
    </Page>
  );
}
