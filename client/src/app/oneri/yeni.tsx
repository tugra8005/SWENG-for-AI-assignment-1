import { router, useLocalSearchParams } from 'expo-router';
import { View } from 'react-native';

import { Choice, H1, InfoNotice, Kicker, Muted, Page, Rule } from '@/components/paper';
import { ProposalForm } from '@/components/proposal-form';
import { useAuth } from '@/lib/auth';
import { TYPE_LABELS } from '@/lib/format';

const LANE_NOTE: Record<string, string> = {
  KONU: 'Hızlı şerit: 24 saat sessiz onay; itiraz eşiği aşılırsa Karar Saati.',
  ALT_KONU: 'Hızlı şerit: 24 saat sessiz onay; itiraz eşiği aşılırsa Karar Saati.',
  DUZENLEME: 'Hızlı şerit: 24 saat sessiz onay; itiraz eşiği aşılırsa Karar Saati.',
  SILME: 'Yavaş şerit: Karar Saati\'nde silme_esigi (2/3) ile oylanır; kendi mesajınız basit çoğunlukla.',
  YONETMELIK: 'Yavaş şerit: Genel kapsamda, Karar Saati\'nde yonetmelik_esigi (2/3) ile oylanır.',
  KAPANIS: '48 saat rakip metin süresi, ardından Karar Saati\'nde onay oylaması.',
};

export default function NewProposal() {
  const params = useLocalSearchParams<{
    type?: string;
    topic?: string;
    message?: string;
    parent?: string;
    article?: string;
    reopen?: string;
    action?: string;
  }>();
  const { me } = useAuth();
  const type = params.type ?? 'KONU';

  return (
    <Page>
      <Kicker>İlan taslağı</Kicker>
      <H1>
        {params.reopen
          ? 'Yeniden açma önerisi'
          : params.action === 'ekle'
            ? 'İçerik kuralı ekleme önerisi'
            : params.action === 'kaldir'
              ? 'Madde kaldırma önerisi'
              : `${TYPE_LABELS[type] ?? type} önerisi`}
      </H1>
      <Muted>{LANE_NOTE[type]}</Muted>
      <Rule double />
      {!me ? (
        <InfoNotice>Öneri açmak için giriş yapın.</InfoNotice>
      ) : (
        <View>
          {!params.topic && !params.message && !params.parent && !params.reopen && !params.action ? (
            <Choice
              label="Tür"
              value={type}
              options={[
                { value: 'KONU', label: 'Konu' },
                { value: 'YONETMELIK', label: 'Yönetmelik' },
              ]}
              onChange={(t) => router.setParams({ type: t })}
            />
          ) : null}
          <ProposalForm
            key={type}
            ctx={{ ...params, type }}
            onDone={(id) => router.replace(`/oneri/${id}`)}
          />
        </View>
      )}
    </Page>
  );
}
