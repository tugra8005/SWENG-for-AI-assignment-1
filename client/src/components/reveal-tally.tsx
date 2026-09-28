/**
 * Karar Saati sonuç açıklaması: açılan oylar tek tek düşer, sayaçlar ilerler,
 * en sonda KABUL / RET mührü basılır. Azaltılmış hareket tercihinde son durum anında görünür.
 */
import { useEffect, useMemo, useState } from 'react';
import { Animated, Easing, StyleSheet, Text, View } from 'react-native';

import { Button, Kicker, Muted, Seal } from '@/components/paper';
import { fmtPercent1 } from '@/lib/format';
import { useAnimatedValue, useReducedMotion } from '@/lib/motion';
import { fonts, paper } from '@/theme/tokens';

type Vote = {
  ballot_id: number;
  voter: string;
  choice: string | number[];
  weight: number;
  delegators: string[];
  ledger_hash?: string | null;
};

const STEP_MS = 520;

function parseRatio(oran: string): number {
  const [a, b] = oran.split('/').map(Number);
  return b ? a / b : Number(oran);
}

function Drop({ v, label, reduced }: { v: Vote; label: string; reduced: boolean }) {
  const y = useAnimatedValue(reduced ? 0 : -26);
  const o = useAnimatedValue(reduced ? 1 : 0);
  useEffect(() => {
    if (reduced) return;
    Animated.parallel([
      Animated.timing(y, { toValue: 0, duration: 380, easing: Easing.out(Easing.back(1.6)), useNativeDriver: false }),
      Animated.timing(o, { toValue: 1, duration: 220, useNativeDriver: false }),
    ]).start();
  }, [o, reduced, y]);
  const yes = label === 'EVET';
  return (
    <Animated.View style={[st.slip, { transform: [{ translateY: y }], opacity: o }, yes ? st.slipYes : st.slipNo]}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
        <Text style={st.slipVoter}>{v.voter}</Text>
        <Text style={st.slipWeight}>×{v.weight}</Text>
      </View>
      <Text style={[st.slipChoice, yes ? { color: paper.seal } : { color: paper.ink }]}>{label}</Text>
      {v.delegators.length ? (
        <Text style={st.slipDeleg} numberOfLines={2}>havale: {v.delegators.join(', ')}</Text>
      ) : null}
    </Animated.View>
  );
}

function Stamp({ text, reduced }: { text: string; reduced: boolean }) {
  const scale = useAnimatedValue(reduced ? 1 : 2.4);
  const o = useAnimatedValue(reduced ? 1 : 0);
  useEffect(() => {
    if (reduced) return;
    Animated.parallel([
      Animated.timing(scale, { toValue: 1, duration: 260, easing: Easing.in(Easing.quad), useNativeDriver: false }),
      Animated.timing(o, { toValue: 1, duration: 200, useNativeDriver: false }),
    ]).start();
  }, [o, reduced, scale]);
  return (
    <Animated.View
      accessibilityLabel={`Sonuç: ${text}`}
      style={[st.stamp, { opacity: o, transform: [{ scale }, { rotate: '-7deg' }] }]}
    >
      <Text style={st.stampText}>{text}</Text>
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

export function RevealTally({ result }: { result: any }) {
  const [run, setRun] = useState(0);
  return <Tally key={run} result={result} onReplay={() => setRun((r) => r + 1)} />;
}

function Tally({ result, onReplay }: { result: any; onReplay: () => void }) {
  const reduced = useReducedMotion();
  const votes: Vote[] = result.votes ?? [];
  const shown = useSequence(votes.length, reduced);
  const done = shown >= votes.length;
  const visible = votes.slice(0, shown);

  const binary = result.kind === 'binary';
  const tally = useMemo(() => {
    if (binary) {
      let yes = 0;
      let no = 0;
      for (const v of visible) {
        if (v.choice === 'EVET') yes += v.weight;
        else no += v.weight;
      }
      return { yes, no };
    }
    const scores: Record<number, number> = {};
    for (const s of result.scores) scores[s.text_id] = 0;
    for (const v of visible) for (const t of v.choice as number[]) scores[t] = (scores[t] ?? 0) + v.weight;
    return { scores };
  }, [binary, visible, result.scores]);

  return (
    <View style={{ gap: 12 }}>
      {binary ? (
        <BinaryBoard result={result} yes={tally.yes!} no={tally.no!} />
      ) : (
        <ApprovalBoard result={result} scores={tally.scores!} done={done} />
      )}

      <View style={st.slips}>
        {visible.map((v) => (
          <Drop
            key={v.ballot_id}
            v={v}
            reduced={reduced}
            label={binary ? String(v.choice) : `${(v.choice as number[]).length ? (v.choice as number[]).map((x) => `#${x}`).join(' ') : 'hiçbiri'}`}
          />
        ))}
      </View>

      {done ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
          <Stamp
            reduced={reduced}
            text={
              binary
                ? // Eşzamanlı çoğunlukta tek oylamanın sonucu önerinin kaderi değildir; özet satırı söyler.
                  result.concurrent || result.overall?.summary
                  ? result.passed
                    ? 'ÇOĞUNLUK VAR'
                    : 'ÇOĞUNLUK YOK'
                  : result.passed
                    ? 'KABUL'
                    : 'RET'
                : result.winner
                  ? 'KARAR'
                  : 'KARAR YOK'
            }
          />
          <Muted style={{ flex: 1, minWidth: 200 }}>{result.note}</Muted>
        </View>
      ) : null}

      {done ? (
        <View style={{ gap: 6 }}>
          <Kicker>
            {result.eligible} seçmen · {result.abstained} çekimser (oy vermeyen ya da zinciri oy vermeyende biten)
          </Kicker>
          {result.oracle ? (
            <Muted>
              Hâtif: {result.oracle.choice} — {result.oracle.reason}
            </Muted>
          ) : null}
          {result.flagged?.length ? (
            <View style={st.flagged}>
              <Kicker style={{ color: paper.seal }}>
                Baskın şüphesiyle işaretlenip dışlanan {result.flagged.length} hesap
              </Kicker>
              <Text style={st.flaggedNames}>{result.flagged.map((f: any) => f.nickname).join(' · ')}</Text>
              <Muted style={{ fontSize: 13 }}>{result.flagged[0].reason}</Muted>
            </View>
          ) : null}
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
            {votes.map((v) => (
              <Seal key={v.ballot_id} hash={v.ledger_hash} label={v.voter} />
            ))}
          </View>
          {!reduced ? <Button label="Açılışı yeniden oynat" variant="quiet" onPress={onReplay} /> : null}
        </View>
      ) : null}
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
  slipWeight: { fontFamily: fonts.monoBold, fontSize: 13, color: paper.ink },
  slipChoice: { fontFamily: fonts.monoBold, fontSize: 13, letterSpacing: 1.5 },
  slipDeleg: { fontFamily: fonts.serifItalic, fontSize: 11, color: paper.muted },
  stamp: { borderWidth: 4, borderColor: paper.seal, paddingHorizontal: 16, paddingVertical: 4 },
  stampText: { fontFamily: fonts.serifDisplay, fontSize: 38, letterSpacing: 4, color: paper.seal },
  flagged: { borderLeftWidth: 3, borderLeftColor: paper.seal, paddingLeft: 10, gap: 2 },
  flaggedNames: { fontFamily: fonts.monoMedium, fontSize: 13, color: paper.ink },
  approvalText: { fontFamily: fonts.serif, fontSize: 16, color: paper.ink, flex: 1 },
});
