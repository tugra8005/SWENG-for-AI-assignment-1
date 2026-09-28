import { StyleSheet, Text, View, type TextStyle } from 'react-native';

import { Kicker } from '@/components/paper';
import { fmtNumber, fmtPercent, fmtSession } from '@/lib/format';
import { fonts, paper } from '@/theme/tokens';

export type Maturity = {
  klass: 'dar' | 'genis' | 'genel';
  label: string;
  hours: number;
  matures_at: string;
  mature: boolean;
  first_session_at: string;
};

/**
 * Öneri başlığı. R2 daraltması varsa iki satır: üstte küçük ve üstü çizili talep, altta büyük
 * etki (kaynak adı + seçmen kapsamının payı). Oylanan şey etkidir; talep kayıt için durur.
 */
export function ProposalTitle({
  title,
  effective,
  style,
  heading = false,
}: {
  title: string;
  effective?: string | null;
  style?: TextStyle;
  heading?: boolean;
}) {
  const role = heading ? 'header' : undefined;
  if (!effective) return <Text accessibilityRole={role} style={style}>{title}</Text>;
  return (
    <View style={{ gap: 2 }}>
      <Text style={st.request} accessibilityLabel={`Talep (daraltıldı): ${title}`}>
        Talep: <Text style={st.struck}>{title}</Text>
      </Text>
      <Text accessibilityRole={role} style={style} accessibilityLabel={`Etki: ${effective}`}>
        <Text style={{ color: paper.seal }}>Etki: </Text>
        {effective}
      </Text>
    </View>
  );
}

/** "4.000 / 20.000 puan (%20)" ve pay çubuğu: tamamı gri, etkilenen pay bordo. */
export function ShareBar({ share, total, unit = 'puan' }: { share: number; total: number; unit?: string }) {
  const pct = Math.max(0, Math.min(100, (share / total) * 100));
  return (
    <View style={{ gap: 6, marginTop: 8 }}>
      <Text style={st.ratio}>
        {fmtNumber(share)} / {fmtNumber(total)} {unit} ({fmtPercent(share, total)})
      </Text>
      <View
        style={st.track}
        accessible
        accessibilityRole="progressbar"
        accessibilityLabel={`Kaynağın ${fmtPercent(share, total)} kadarı etkileniyor`}
        accessibilityValue={{ min: 0, max: total, now: share }}
      >
        <View style={[st.fill, { width: `${pct}%` }]} />
      </View>
    </View>
  );
}

/** R2 daraltma kutusu: gerekçe cümlesi, oran ve pay çubuğu. Öneri ve ondan doğan konu kullanır. */
export function NarrowingBox({ message, share, total }: { message: string; share: number; total?: number | null }) {
  return (
    <View style={st.narrow}>
      <Kicker style={{ color: paper.seal }}>R2 · otomatik daralma</Kicker>
      <Text style={st.narrowText}>{message}</Text>
      {total ? <ShareBar share={share} total={total} /> : null}
    </View>
  );
}

const fmtDuration = (hours: number) => (hours % 24 === 0 && hours > 72 ? `${hours / 24} gün` : `${hours} saat`);

/** Kısa satır: "Olgunlaşıyor — 11 Ekim Pazar 20:00 oturumunda oylanacak". */
export function maturityLine(m?: Maturity | null): string | null {
  if (!m || m.mature) return null;
  return `Olgunlaşıyor — ${fmtSession(m.first_session_at)} oturumunda oylanacak`;
}

/** Öneri sayfası için açıklamalı hâli. */
export function maturityDetail(m: Maturity): string {
  return (
    `Olgunlaşma süresi ${fmtDuration(m.hours)} (${m.label} etki); ${fmtSession(m.matures_at)} itibarıyla ` +
    'dolar. Süre dolmadan açılan Karar Saati penceresi bu öneriyi almaz, sonraki oturuma kaydırır.'
  );
}

const st = StyleSheet.create({
  request: { fontFamily: fonts.mono, fontSize: 12, lineHeight: 17, color: paper.muted },
  struck: { textDecorationLine: 'line-through' },
  ratio: { fontFamily: fonts.monoMedium, fontSize: 14, color: paper.ink },
  track: {
    height: 12,
    borderWidth: 1,
    borderColor: paper.muted,
    backgroundColor: paper.hairline,
    overflow: 'hidden',
  },
  fill: { height: '100%', backgroundColor: paper.seal },
  narrow: {
    borderWidth: 2,
    borderColor: paper.seal,
    padding: 12,
    marginVertical: 8,
    backgroundColor: paper.sealWash,
  },
  narrowText: { fontFamily: fonts.serifBold, fontSize: 20, color: paper.seal, marginTop: 4 },
});
