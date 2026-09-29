/**
 * Karar Saati sonuç açıklaması.
 *
 * Özet (varsayılan): toplamlar, KABUL / RET mührü, açık oylar (temsilciler ve Hâtif) listesi. Gizli
 * oylar için kart gösterilmez; yalnızca toplamlara katılır. "Oyların açılışını izle" ile bütün oylar
 * tek tek düşer: açık oylar takma adla, gizli oylar oturuma özel takma kimlikle. Azaltılmış hareket
 * tercihinde son durum anında görünür.
 */
import { useEffect, useMemo, useState } from 'react';
import { Animated, Easing, StyleSheet, Text, useWindowDimensions, View } from 'react-native';

import { Button, Kicker, Muted } from '@/components/paper';
import { fmtPercent1 } from '@/lib/format';
import { useAnimatedValue, useReducedMotion } from '@/lib/motion';
import { fonts, paper } from '@/theme/tokens';

type Vote = {
  ballot_id: number;
  open: boolean;
  voter?: string;
  pseudonym?: string;
  choice: string | number[];
  weight: number;
  delegators?: string[];
};

const STEP_MS = 520;

function parseRatio(oran: string): number {
  const [a, b] = oran.split('/').map(Number);
  return b ? a / b : Number(oran);
}

const choiceText = (binary: boolean, c: string | number[]) =>
  binary ? String(c) : (c as number[]).length ? (c as number[]).map((x) => `#${x}`).join(' ') : 'hiçbiri';

function stampText(result: any): string {
  if (result.overall?.conflict) return 'UYGULANAMADI';
  if (result.kind !== 'binary') return result.winner ? 'KARAR' : 'KARAR YOK';
  // Eşzamanlı çoğunlukta tek oylamanın sonucu önerinin kaderi değildir; özet satırı söyler.
  if (result.concurrent || result.overall?.summary) return result.passed ? 'ÇOĞUNLUK VAR' : 'ÇOĞUNLUK YOK';
  return result.passed ? 'KABUL' : 'RET';
}

function Slip({ v, binary, reduced }: { v: Vote; binary: boolean; reduced: boolean }) {
  const y = useAnimatedValue(reduced ? 0 : -26);
  const o = useAnimatedValue(reduced ? 1 : 0);
  useEffect(() => {
    if (reduced) {
      y.stopAnimation();
      o.stopAnimation();
      y.setValue(0);
      o.setValue(1);
      return;
    }
    Animated.parallel([
      Animated.timing(y, { toValue: 0, duration: 380, easing: Easing.out(Easing.back(1.6)), useNativeDriver: false }),
      Animated.timing(o, { toValue: 1, duration: 220, useNativeDriver: false }),
    ]).start();
  }, [o, reduced, y]);
  const yes = binary && v.choice === 'EVET';
  return (
    <Animated.View style={[st.slip, { transform: [{ translateY: y }], opacity: o }, yes ? st.slipYes : st.slipNo]}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
        {v.open ? (
          <Text style={st.slipVoter}>{v.voter}</Text>
        ) : (
          <Text style={st.slipAlias} accessibilityLabel={`gizli oy, takma kimlik ${v.pseudonym}`}>
            gizli · {v.pseudonym}
          </Text>
        )}
        <Text style={st.slipWeight}>×{v.weight}</Text>
      </View>
      <Text style={[st.slipChoice, yes ? { color: paper.seal } : { color: paper.ink }]}>{choiceText(binary, v.choice)}</Text>
    </Animated.View>
  );
}

function Stamp({ text, reduced, animate }: { text: string; reduced: boolean; animate: boolean }) {
  const { width } = useWindowDimensions();
  const narrow = width < 520;
  const still = reduced || !animate;
  const scale = useAnimatedValue(still ? 1 : 2.4);
  const o = useAnimatedValue(still ? 1 : 0);
  useEffect(() => {
    if (still) {
      scale.setValue(1);
      o.setValue(1);
      return;
    }
    Animated.parallel([
      Animated.timing(scale, { toValue: 1, duration: 260, easing: Easing.in(Easing.quad), useNativeDriver: false }),
      Animated.timing(o, { toValue: 1, duration: 200, useNativeDriver: false }),
    ]).start();
  }, [o, scale, still]);
  return (
    <Animated.View
      accessibilityLabel={`Sonuç: ${text}`}
      style={[
        st.stamp,
        narrow && st.stampNarrow,
        { opacity: o, transform: [{ scale }, { rotate: narrow ? '-3deg' : '-7deg' }] },
      ]}
    >
      <Text style={[st.stampText, narrow && st.stampTextNarrow]} numberOfLines={1}>
        {text}
      </Text>
    </Animated.View>
  );
}

function useSequence(total: number, reduced: boolean) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const id = setInterval(() => {
      setShown((i) => {
        if (i + 1 >= total) clearInterval(id);
        return Math.min(total, i + 1);
      });
    }, STEP_MS);
    return () => clearInterval(id);
  }, [total, reduced]);
  return reduced ? total : shown;
}

export function RevealTally({ result, autoplay }: { result: any; autoplay?: boolean }) {
  const [run, setRun] = useState(autoplay ? 1 : 0);
  if (!run) return <Summary result={result} onReplay={() => setRun(1)} />;
  return (
    <Replay
      key={run}
      result={result}
      onReplay={() => setRun((r) => r + 1)}
      onClose={() => setRun(0)}
    />
  );
}

function tallyOf(result: any, visible: Vote[]) {
  if (result.kind === 'binary') {
    let yes = 0;
    let no = 0;
    for (const v of visible) {
      if (v.choice === 'EVET') yes += v.weight;
      else no += v.weight;
    }
    return { yes, no, scores: {} as Record<number, number> };
  }
  const scores: Record<number, number> = {};
  for (const s of result.scores) scores[s.text_id] = 0;
  for (const v of visible) for (const t of v.choice as number[]) scores[t] = (scores[t] ?? 0) + v.weight;
  return { yes: 0, no: 0, scores };
}

function Board({ result, visible, done }: { result: any; visible: Vote[]; done: boolean }) {
  const t = useMemo(() => tallyOf(result, visible), [result, visible]);
  return result.kind === 'binary' ? (
    <BinaryBoard result={result} yes={t.yes} no={t.no} />
  ) : (
    <ApprovalBoard result={result} scores={t.scores} done={done} />
  );
}

function Verdict({ result, reduced, animate }: { result: any; reduced: boolean; animate: boolean }) {
  const { width } = useWindowDimensions();
  const narrow = width < 520;
  return (
    <View style={narrow ? { gap: 10 } : { flexDirection: 'row', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
      <View style={narrow ? { alignSelf: 'flex-start', paddingVertical: 4 } : undefined}>
        <Stamp reduced={reduced} animate={animate} text={stampText(result)} />
      </View>
      <Muted style={narrow ? undefined : { flex: 1, minWidth: 200 }}>{result.note}</Muted>
    </View>
  );
}

function Facts({ result }: { result: any }) {
  return (
    <View style={{ gap: 6 }}>
      <Kicker>
        {result.eligible} seçmen · {result.abstained} çekimser (oy vermeyen ya da zinciri oy vermeyende biten)
      </Kicker>
      {result.oracle ? (
        <Muted>
          Hâtif: {result.oracle.choice} — {result.oracle.reason}
        </Muted>
      ) : null}
      {result.flagged_count ? (
        <View style={st.flagged}>
          <Kicker style={{ color: paper.seal }}>
            {result.flagged_count} hesabın oyu baskın şüphesiyle sayılmadı
          </Kicker>
          {(result.flagged_reasons ?? []).map((r: string) => (
            <Muted key={r} style={{ fontSize: 13 }}>
              {r}
            </Muted>
          ))}
          <Muted style={{ fontSize: 12 }}>
            Hesaplar adlarıyla listelenmez; dışlanan kişi bunu kendi oylama sayfasında görür.
          </Muted>
        </View>
      ) : null}
    </View>
  );
}

function OpenVotes({ result }: { result: any }) {
  const binary = result.kind === 'binary';
  const open: Vote[] = (result.votes ?? []).filter((v: Vote) => v.open);
  const secret = (result.votes ?? []).length - open.length;
  return (
    <View style={{ gap: 6 }}>
      <Kicker>Açık oylar (temsilciler)</Kicker>
      <Muted style={{ fontSize: 13 }}>
        Başkalarının oyunu taşıyanların (ağırlığı 1&apos;den büyük) ve Hâtif&apos;in oyu açıktır. {secret} gizli oy yalnızca
        toplamlara katıldı.
      </Muted>
      {open.map((v) => (
        <View key={v.ballot_id} style={st.openRow}>
          <Text style={st.openVoter}>{v.voter}</Text>
          <Text style={st.openChoice}>{choiceText(binary, v.choice)}</Text>
          <Text style={st.openWeight}>×{v.weight}</Text>
          {v.delegators?.length ? (
            <Text style={st.openDeleg} numberOfLines={2}>
              havale: {v.delegators.join(', ')}
            </Text>
          ) : null}
        </View>
      ))}
      {open.length === 0 ? <Muted style={{ fontSize: 13 }}>Açık oy yok.</Muted> : null}
    </View>
  );
}

function Summary({ result, onReplay }: { result: any; onReplay: () => void }) {
  const reduced = useReducedMotion();
  const votes: Vote[] = result.votes ?? [];
  return (
    <View style={{ gap: 12 }}>
      <Board result={result} visible={votes} done />
      <Verdict result={result} reduced={reduced} animate={false} />
      <Facts result={result} />
      <OpenVotes result={result} />
      {votes.length ? <Button label="Oyların açılışını izle" variant="quiet" onPress={onReplay} /> : null}
    </View>
  );
}

function Replay({ result, onReplay, onClose }: { result: any; onReplay: () => void; onClose: () => void }) {
  const reduced = useReducedMotion();
  const votes: Vote[] = result.votes ?? [];
  const shown = useSequence(votes.length, reduced);
  const done = shown >= votes.length;
  const visible = votes.slice(0, shown);
  const binary = result.kind === 'binary';
  return (
    <View style={{ gap: 12 }}>
      <Board result={result} visible={visible} done={done} />
      <View style={st.slips}>
        {visible.map((v) => (
          <Slip key={v.ballot_id} v={v} binary={binary} reduced={reduced} />
        ))}
      </View>
      {done ? <Verdict result={result} reduced={reduced} animate /> : null}
      <View style={{ flexDirection: 'row', gap: 18, flexWrap: 'wrap' }}>
        {done && !reduced ? <Button label="Yeniden oynat" variant="quiet" onPress={onReplay} /> : null}
        <Button label="Özete dön" variant="quiet" onPress={onClose} />
      </View>
    </View>
  );
}

function BinaryBoard({ result, yes, no }: { result: any; yes: number; no: number }) {
  const total = yes + no;
  const ratio = parseRatio(result.threshold.oran);
  const pct = total ? yes / total : 0;
  const sign = result.threshold.karsilastirma === '>' ? '>' : '≥';
  return (
    <View style={{ gap: 6 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <View>
          <Kicker style={{ color: paper.seal }}>Evet</Kicker>
          <Text style={[st.count, { color: paper.seal }]}>{yes}</Text>
        </View>
        <Text style={st.pct}>{total ? fmtPercent1(pct) : '—'}</Text>
        <View style={{ alignItems: 'flex-end' }}>
          <Kicker>Hayır</Kicker>
          <Text style={st.count}>{no}</Text>
        </View>
      </View>
      <View style={st.bar} aria-label={`Evet oranı ${fmtPercent1(pct)}`}>
        <View style={[st.barYes, { width: `${pct * 100}%` }]} />
        <View style={[st.threshold, { left: `${ratio * 100}%` }]} />
      </View>
      <Text style={st.thresholdLabel}>
        eşik: {result.threshold.key} {sign} {result.threshold.oran} (kullanılan oylar içinde)
      </Text>
    </View>
  );
}

function ApprovalBoard({ result, scores, done }: { result: any; scores: Record<number, number>; done: boolean }) {
  const max = Math.max(1, ...Object.values(scores));
  return (
    <View style={{ gap: 10 }}>
      {result.scores.map((s: any) => {
        const val = scores[s.text_id] ?? 0;
        const winner = done && result.winner === s.text_id;
        return (
          <View key={s.text_id} style={{ gap: 3 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10 }}>
              <Text style={[st.approvalText, winner && { color: paper.seal, fontFamily: fonts.serifBold }]} numberOfLines={2}>
                #{s.text_id} {s.text} <Text style={{ fontFamily: fonts.serifItalic, color: paper.muted }}>— {s.author}</Text>
              </Text>
              <Text style={[st.count, { fontSize: 22 }, winner && { color: paper.seal }]}>{val}</Text>
            </View>
            <View style={st.bar}>
              <View style={[st.barYes, { width: `${(val / max) * 100}%` }, !winner && done && { backgroundColor: paper.inkSoft }]} />
            </View>
          </View>
        );
      })}
    </View>
  );
}

const st = StyleSheet.create({
  count: { fontFamily: fonts.monoBold, fontSize: 40, color: paper.ink },
  pct: { fontFamily: fonts.monoMedium, fontSize: 18, color: paper.inkSoft, paddingBottom: 8 },
  bar: { height: 16, borderWidth: 1.5, borderColor: paper.ink, backgroundColor: paper.sheet, overflow: 'visible' },
  barYes: { height: '100%', backgroundColor: paper.seal },
  threshold: { position: 'absolute', top: -6, bottom: -6, width: 2, backgroundColor: paper.ink },
  thresholdLabel: { fontFamily: fonts.mono, fontSize: 11, color: paper.inkSoft },
  slips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  slip: { width: 132, borderWidth: 1, padding: 8, backgroundColor: paper.sheet, gap: 2 },
  slipYes: { borderColor: paper.seal },
  slipNo: { borderColor: paper.ink },
  slipVoter: { fontFamily: fonts.serifMedium, fontSize: 14, color: paper.ink, flexShrink: 1 },
  slipAlias: { fontFamily: fonts.mono, fontSize: 11, color: paper.inkSoft, flexShrink: 1 },
  slipWeight: { fontFamily: fonts.monoBold, fontSize: 13, color: paper.ink },
  slipChoice: { fontFamily: fonts.monoBold, fontSize: 13, letterSpacing: 1.5 },
  stamp: { borderWidth: 4, borderColor: paper.seal, paddingHorizontal: 16, paddingVertical: 4 },
  stampNarrow: { borderWidth: 3, paddingHorizontal: 10, paddingVertical: 2 },
  stampText: { fontFamily: fonts.serifDisplay, fontSize: 38, letterSpacing: 4, color: paper.seal },
  stampTextNarrow: { fontSize: 24, letterSpacing: 2 },
  flagged: { borderLeftWidth: 3, borderLeftColor: paper.seal, paddingLeft: 10, gap: 2 },
  openRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 10,
    flexWrap: 'wrap',
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: paper.hairline,
  },
  openVoter: { fontFamily: fonts.serifBold, fontSize: 16, color: paper.ink, minWidth: 90 },
  openChoice: { fontFamily: fonts.monoBold, fontSize: 13, letterSpacing: 1.5, color: paper.ink },
  openWeight: { fontFamily: fonts.monoBold, fontSize: 13, color: paper.inkSoft },
  openDeleg: { fontFamily: fonts.serifItalic, fontSize: 13, color: paper.muted, flexBasis: '100%' },
  approvalText: { fontFamily: fonts.serif, fontSize: 16, color: paper.ink, flex: 1 },
});
