import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { api } from '@/api/client';
import { CityPicker } from '@/components/city-picker';
import {
  Body,
  Button,
  ErrorNotice,
  Field,
  H1,
  Kicker,
  Muted,
  Page,
  Rule,
} from '@/components/paper';
import { paper } from '@/theme/tokens';

/** "GG.AA.YYYY" → "YYYY-AA-GG" */
function parseDate(text: string): string | null {
  const m = text.trim().match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  if (!m) return null;
  const [, d, mo, y] = m;
  return `${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}`;
}

export default function Register() {
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    nickname: '',
    password: '',
    birth: '',
    city: '',
    district: '',
    address_line: '',
  });
  const [error, setError] = useState<unknown>(null);
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async () => {
    setError(null);
    const birth_date = parseDate(form.birth);
    if (!birth_date) {
      setError({ message: 'Doğum tarihini GG.AA.YYYY biçiminde girin.', violations: [] });
      return;
    }
    try {
      await api('/auth/register', {
        method: 'POST',
        body: { ...form, birth_date, birth: undefined },
      });
      router.replace({ pathname: '/dogrula', params: { email: form.email } });
    } catch (e) {
      setError(e);
    }
  };

  return (
    <Page>
      <View style={{ maxWidth: 560, width: '100%', alignSelf: 'center' }}>
        <Kicker>Yurttaşlık kaydı · Form 1</Kicker>
        <H1>Kayıt</H1>
        <Muted>
          Ad soyad, adres ve doğum tarihi yalnızca size görünür. Profilinizde herkese yalnızca
          takma adınız görünür.
        </Muted>
        <Rule />
        <Field label="Ad soyad" value={form.full_name} onChangeText={set('full_name')} autoComplete="name" />
        <Field
          label="E-posta"
          value={form.email}
          onChangeText={set('email')}
          autoCapitalize="none"
          keyboardType="email-address"
          autoComplete="email"
        />
        <Field
          label="Takma ad"
          value={form.nickname}
          onChangeText={set('nickname')}
          autoCapitalize="none"
          hint="3–24 karakter; herkese görünen tek kimliğiniz."
        />
        <Field
          label="Şifre"
          value={form.password}
          onChangeText={set('password')}
          secureTextEntry
          hint="En az 8 karakter."
        />
        <Field
          label="Doğum tarihi"
          value={form.birth}
          onChangeText={set('birth')}
          placeholder="GG.AA.YYYY"
          hint="Kayıt için 18 yaşını doldurmuş olmalısınız. Yaş grubunuz buradan hesaplanır."
        />
        <Kicker style={{ marginTop: 6, marginBottom: 8 }}>Adres</Kicker>
        <CityPicker value={form.city} onChange={set('city')} />
        <Field label="İlçe" value={form.district} onChangeText={set('district')} />
        <Field label="Açık adres (isteğe bağlı)" value={form.address_line} onChangeText={set('address_line')} />
        <Body style={{ fontSize: 15, color: paper.inkSoft, marginBottom: 12 }}>
          Şehriniz, şehir kapsamındaki oylamalara katılmanızı belirler. Adresinizi sonradan
          değiştirirseniz yeni şehirde oy hakkınız 90 gün sonra doğar.
        </Body>
        <ErrorNotice error={error} />
        <Button label="Kaydı gönder" onPress={submit} />
      </View>
    </Page>
  );
}
