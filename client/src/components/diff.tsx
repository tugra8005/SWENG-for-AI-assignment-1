import { Text } from 'react-native';

import { fonts, paper } from '@/theme/tokens';

export type DiffChunk = [op: 'equal' | 'insert' | 'delete', text: string];

/** Kelime bazlı fark: eklenen bordo altı çizili, silinen üstü çizili. */
export function DiffText({ chunks, size = 17 }: { chunks: DiffChunk[]; size?: number }) {
  return (
    <Text style={{ fontFamily: fonts.serif, fontSize: size, lineHeight: size * 1.45, color: paper.ink }}>
      {chunks.map(([op, text], i) => {
        if (op === 'insert') {
          return (
            <Text
              key={i}
              accessibilityLabel={`eklendi: ${text}`}
              style={{ color: paper.seal, backgroundColor: paper.sealWash, textDecorationLine: 'underline' }}
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
