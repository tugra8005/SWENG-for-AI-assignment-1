import { Link, useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';

import { DiffText } from '@/components/diff';
import { Body, ErrorNotice, H1, Kicker, Loading, Muted, Page, Rule, Seal } from '@/components/paper';
import { fmtDateTime } from '@/lib/format';
import { useApi } from '@/lib/useApi';
import { paper } from '@/theme/tokens';

export default function History() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const h = useApi<any>(`/messages/${id}/history`);
  return (
    <Page>
      <Kicker>Mesaj #{id} · sürüm geçmişi</Kicker>
      <H1>Sürümler</H1>
      {h.data ? (
        <Link href={`/konu/${h.data.topic_id}`} style={{ color: paper.seal }}>
          ← konuya dön
        </Link>
      ) : null}
      <Rule double />
      {h.error ? <ErrorNotice error={h.error} /> : null}
      {!h.data && !h.error ? <Loading /> : null}
      {h.data?.versions.map((v: any) => (
        <View key={v.version} style={{ paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: paper.hairline, gap: 6 }}>
          <Kicker>
            Sürüm {v.version} · {v.editor} · {fmtDateTime(v.created_at)}
            {v.via_proposal_id ? ` · №${v.via_proposal_id} numaralı düzenleme önerisiyle` : ''}
          </Kicker>
          {v.diff ? <DiffText chunks={v.diff} /> : <Body>{v.text}</Body>}
          <Seal hash={v.ledger_hash} />
        </View>
      ))}
      {h.data ? (
        <Muted style={{ marginTop: 12 }}>Her sürüm deftere ayrı bir kayıt olarak yazılır; geçmiş silinmez.</Muted>
      ) : null}
    </Page>
  );
}
