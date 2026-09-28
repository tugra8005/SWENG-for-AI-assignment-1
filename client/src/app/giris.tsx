import { Link, router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { Body, Button, ErrorNotice, Field, H1, InfoNotice, Kicker, Muted, Page, Rule } from '@/components/paper';
import { useAuth } from '@/lib/auth';
import { paper } from '@/theme/tokens';

export default function Login() {
  const { login } = useAuth();
  const { dogrulandi } = useLocalSearchParams<{ dogrulandi?: string }>();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<unknown>(null);

  const submit = async () => {
    setError(null);
    try {
      await login(identifier.trim(), password);
      router.replace('/');
    } catch (e) {
      setError(e);
    }
  };

  return (
    <Page>
      <View style={{ maxWidth: 440, width: '100%', alignSelf: 'center' }}>
        <Kicker>Kimlik denetimi</Kicker>
        <H1>Giriş</H1>
        <Rule />
        {dogrulandi ? <InfoNotice>E-postanız doğrulandı; şimdi giriş yapabilirsiniz.</InfoNotice> : null}
        <Field
          label="Takma ad ya da e-posta"
          value={identifier}
          onChangeText={setIdentifier}
          autoCapitalize="none"
          autoComplete="username"
          textContentType="username"
        />
        <Field
          label="Şifre"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoComplete="password"
          textContentType="password"
          onSubmitEditing={submit}
        />
        <ErrorNotice error={error} />
        <Button label="Giriş yap" onPress={submit} disabled={!identifier || !password} />
        <Rule faint style={{ marginTop: 22 }} />
        <Body>
          Hesabınız yok mu?{' '}
          <Link href="/kayit" style={{ color: paper.seal, textDecorationLine: 'underline' }}>
            Kayıt olun
          </Link>
          .
        </Body>
        <Muted style={{ marginTop: 8 }}>
          E-postanızı doğrulamadıysanız{' '}
          <Link href="/dogrula" style={{ color: paper.seal }}>doğrulama kodunu girin</Link>.
        </Muted>
      </View>
    </Page>
  );
}
