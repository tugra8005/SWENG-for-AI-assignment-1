/**
 * Pay etkisi önizlemesi (sunucudaki domain/shares.py ile aynı hesap): kapsam başına göreli
 * değişim, payı olan kapsamların ortalaması ve orantısız etkilenenler. Karar sunucunundur;
 * bu yalnızca formda önizlemedir.
 */
export type ShareRow = { scopeId: string; name: string; old: number; next: number; relative: number | null };

export function shareImpact(rows: ShareRow[], thresholdPP: number) {
  const known = rows.filter((r) => r.relative !== null).map((r) => r.relative as number);
  const average = known.length ? known.reduce((a, b) => a + b, 0) / known.length : null;
  const flagged = rows
    .filter(
      (r) =>
        average !== null && r.relative !== null && r.relative < 0 &&
        (average - r.relative) * 100 >= thresholdPP - 1e-9,
    )
    .map((r) => r.scopeId);
  return { average, flagged };
}

export function toRows(shares: { scope_id: string; name: string; points: number }[], edits: Record<string, string>) {
  return shares.map((s) => {
    const raw = edits[s.scope_id];
    const next = raw === undefined || raw === '' ? s.points : Number(raw);
    return {
      scopeId: s.scope_id,
      name: s.name,
      old: s.points,
      next,
      relative: s.points > 0 && Number.isFinite(next) ? (next - s.points) / s.points : null,
    };
  });
}
