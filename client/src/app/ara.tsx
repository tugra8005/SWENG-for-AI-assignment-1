import { useLocalSearchParams, router } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { Field, Grid, Kicker, Loading, Muted, Page, PageHead, PressLink, Section } from '@/components/paper';
import { useApi } from '@/lib/useApi';
import { fonts, paper } from '@/theme/tokens';

type Hit = { id: number; title: string; link: string; snippet: string };
type Result = { q: string; total: number; groups: Record<string, Hit[]> };

const GROUPS: [string, string][] = [
  ['konular', 'Konular'],
  ['oneriler', 'Öneriler'],
  ['mesajlar', 'Tartışma'],
  ['dilekceler', 'Dilekçeler'],
  ['etkinlikler', 'Etkinlikler'],
];

export default function Search() {
  const params = useLocalSearchParams<{ q?: string }>();
  const [text, setText] = useState(params.q ?? '');
  const [query, setQuery] = useState(params.q ?? '');
  // Yazarken her tuşta istek atılmaz: 300 ms durunca aranır; adres çubuğu da güncellenir.
  useEffect(() => {
    const id = setTimeout(() => {
      const q = text.trim();
      setQuery(q);
      router.setParams({ q: q || undefined });
    }, 300);
    return () => clearTimeout(id);
  }, [text]);
  const res = useApi<Result>(query.length >= 2 ? `/search?q=${encodeURIComponent(query)}` : null);
  const d = res.data;
  return (
    <Page>
      <PageHead kicker="Arama" title="Meydan’da ara">
        <Muted>Konular, öneriler, tartışma mesajları, dilekçeler ve etkinlikler. Mahzen ve silinen içerik aranmaz.</Muted>
      </PageHead>
      <Field label="Ne arıyorsunuz?" value={text} onChangeText={setText} autoFocus placeholder="ör. İstanbul, Menon, bisiklet" returnKeyType="search" />
      {query.length >= 2 && res.loading ? <Loading /> : null}
      {d && d.total === 0 ? <Muted>“{d.q}” için sonuç yok.</Muted> : null}
      {d ? (
        <Grid min={340} ruled>
          {GROUPS.filter(([key]) => d.groups[key]?.length).map(([key, label]) => (
            <Section key={key} title={label} aside={<Kicker>{d.groups[key].length}</Kicker>}>
              {d.groups[key].map((h) => (
                <PressLink key={`${key}:${h.id}`} href={h.link} style={st.hit}>
                  <Text style={st.title}>{h.title}</Text>
                  {h.snippet ? <Text style={st.snippet}>{h.snippet}</Text> : null}
                </PressLink>
              ))}
            </Section>
          ))}
        </Grid>
      ) : null}
      {!query ? (
        <View style={{ marginTop: 8 }}>
          <Muted style={{ fontSize: 14 }}>İpucu: web’de herhangi bir sayfada “/” tuşu aramayı açar.</Muted>
        </View>
      ) : null}
    </Page>
  );
}

const st = StyleSheet.create({
  hit: { paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 3 },
  title: { fontFamily: fonts.serifMedium, fontSize: 17, color: paper.ink },
  snippet: { fontFamily: fonts.serif, fontSize: 14, lineHeight: 20, color: paper.inkSoft },
});
