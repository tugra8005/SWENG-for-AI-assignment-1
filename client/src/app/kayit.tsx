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
  H2,
  Kicker,
  Muted,
  Page,
  Rule,
} from '@/components/paper';
import { checkBirthDate, istanbulDate, maskBirthDate } from '@/lib/birth-date';
import { useClock } from '@/lib/clock';
import { paper } from '@/theme/tokens';

const BIRTH_HINT = 'Kayıt için 18 yaşını doldurmuş olmalısınız. Yaş grubunuz buradan hesaplanır.';
const BIRTH_INCOMPLETE = 'Tarih eksik: GG.AA.YYYY biçiminde girin, örneğin 14.03.1995.';

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
  // Eksik tarih uyarısı alandan çıkınca ya da gönderince görünür, yazmaya dönünce kalkar;
  // geçersiz tarih (gün 32, 31 Şubat, 18 yaş altı) yazarken hemen görünür.
  const [birthLeft, setBirthLeft] = useState(false);
  const clock = useClock();
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));
  // Yaş sunucunun (sahte) saatine göre hesaplanır; sunucu da aynı güne göre denetler.
  const birth = checkBirthDate(form.birth, istanbulDate(clock.now()));
  const birthError =
    birth.state === 'invalid' || birth.state === 'partial'
      ? (birth.error ?? (birthLeft ? BIRTH_INCOMPLETE : undefined))
      : undefined;
  const birthHint = birth.state === 'ok' ? `${birth.label} · ${birth.age} yaş` : BIRTH_HINT;

  const submit = async () => {
    setError(null);
    if (birth.state !== 'ok') {
      setBirthLeft(true);
      const message =
        birth.state === 'empty' ? 'Doğum tarihini girin.' : (birth.error ?? BIRTH_INCOMPLETE);
      setError({ message, violations: [] });
      return;
    }
    const birth_date = birth.iso;
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
          onChangeText={(v) => {
            setForm((f) => ({ ...f, birth: maskBirthDate(v) }));
            setBirthLeft(false);
          }}
          onBlur={() => setBirthLeft(true)}
          placeholder="GG.AA.YYYY"
          keyboardType="number-pad"
          maxLength={10}
          hint={birthHint}
          error={birthError}
        />
        <View style={{ marginTop: 18, marginBottom: 10 }}>
          <H2>Adres</H2>
          <Rule style={{ marginTop: 4, marginBottom: 0 }} />
        </View>
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
