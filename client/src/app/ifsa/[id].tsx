import { useLocalSearchParams } from 'expo-router';

import { ErrorNotice, Loading, Page } from '@/components/paper';
import { RevealedThread } from '@/components/revealed-thread';
import { useApi } from '@/lib/useApi';

export default function Revealed() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const t = useApi<any>(`/cellar/revealed/${id}`);
  return (
    <Page>
      {t.data ? <RevealedThread t={t.data} /> : t.error ? <ErrorNotice error={t.error} /> : <Loading />}
    </Page>
  );
}
