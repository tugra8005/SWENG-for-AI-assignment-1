import { type ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';

import { paper } from '@/theme/tokens';

export type AreaNode = { id: string; name: string; parent_id: string | null };

/**
 * Alan seçicileri düz liste değil, üst alanlara göre gruplanır: her grubun başında üst alanın
 * kendisi, altında alt alanlar girintiyle. Masaüstünde gruplar yan yana, telefonda alt alta.
 */
export function AreaGroups({
  areas,
  renderItem,
}: {
  areas: AreaNode[];
  renderItem: (area: AreaNode, depth: number) => ReactNode;
}) {
  const children = (parent: string | null) =>
    areas.filter((a) => a.parent_id === parent).sort((a, b) => a.name.localeCompare(b.name, 'tr'));
  const branch = (parent: string, depth: number): ReactNode =>
    children(parent).map((a) => (
      <View key={a.id} style={{ paddingLeft: 14, gap: 6 }}>
        {renderItem(a, depth)}
        {branch(a.id, depth + 1)}
      </View>
    ));
  return (
    <View style={st.groups}>
      {children(null).map((root) => (
        <View key={root.id} style={st.group}>
          {renderItem(root, 0)}
          <View style={st.branch}>{branch(root.id, 1)}</View>
        </View>
      ))}
    </View>
  );
}

const st = StyleSheet.create({
  groups: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 18, rowGap: 14 },
  group: { flexGrow: 1, flexBasis: 200, gap: 6 },
  branch: { borderLeftWidth: 1, borderLeftColor: paper.hairline, marginLeft: 6, gap: 6 },
});
