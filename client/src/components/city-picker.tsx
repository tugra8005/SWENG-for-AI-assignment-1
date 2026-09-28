import { useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';

import { Field } from '@/components/paper';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

/** 81 il listesinden seçim; yazılanla başlayan iller (Türkçe büyük/küçük harf duyarsız) önerilir. */
export function CityPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const cities = useApi<string[]>('/cities');
  const [query, setQuery] = useState(value);
  const matches = useMemo(() => {
    const q = query.toLocaleLowerCase('tr-TR');
    return (cities.data ?? []).filter((c) => c.toLocaleLowerCase('tr-TR').startsWith(q)).slice(0, 6);
  }, [cities.data, query]);
  return (
    <View>
      <Field
        label="İl"
        value={query}
        onChangeText={(t) => {
          setQuery(t);
          onChange('');
        }}
        placeholder="ör. İstanbul"
        hint={value ? `Seçilen il: ${value}` : 'Listeden seçin (81 il).'}
      />
      {!value && query.length > 0 ? (
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: -6, marginBottom: 12 }}>
          {matches.map((c) => (
            <Pressable
              key={c}
              onPress={() => {
                setQuery(c);
                onChange(c);
              }}
              accessibilityRole="button"
              style={{ borderWidth: 1, borderColor: paper.ink, paddingHorizontal: 8, paddingVertical: 4 }}
            >
              <Text style={{ fontFamily: fonts.mono, fontSize: 12, color: paper.ink }}>{c}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}
