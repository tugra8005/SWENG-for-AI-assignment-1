import { Text } from 'react-native';

import { fonts, paper } from '@/theme/tokens';

export type DiffChunk = [op: 'equal' | 'insert' | 'delete', text: string];

/** Kelime bazlı fark: eklenen açık bordo zeminle (altı çizili değil, bağlantı sanılmasın), silinen üstü çizili ve soluk. */
export function DiffText({ chunks, size = 17 }: { chunks: DiffChunk[]; size?: number }) {
  return (
    <Text style={{ fontFamily: fonts.serif, fontSize: size, lineHeight: size * 1.45, color: paper.ink }}>
      {chunks.map(([op, text], i) => {
        if (op === 'insert') {
          return (
            <Text
              key={i}
              accessibilityLabel={`eklendi: ${text}`}
              style={{ color: paper.ink, backgroundColor: paper.insertWash }}
            >
              {text}
            </Text>
          );
        }
        if (op === 'delete') {
          return (
            <Text
              key={i}
              accessibilityLabel={`silindi: ${text}`}
              style={{ color: paper.muted, textDecorationLine: 'line-through' }}
            >
              {text}
            </Text>
          );
        }
        return <Text key={i}>{text}</Text>;
      })}
    </Text>
  );
}
