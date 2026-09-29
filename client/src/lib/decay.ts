/**
 * Mahzen çürümesi: CRT arızası gibi blok glifler (░▒▓▚▞▙▟), tek tük ¤ ¦.
 *
 * - ``decay`` 0 (taze) → 1 (silinmek üzere); ``1 - ömür``.
 * - Ömrün ilk %55'inde yalnızca soluklaşma olur (renk, bkz. ``DecayText``); bozulma son %45'te
 *   başlar ve orada doğrusal artar.
 * - Bozulan karakter oranı silinme anında en fazla %10'dur. Sınır serttir: karakterler rastgele
 *   eşikle değil sayıyla seçilir, kısa başlıkta da aşılmaz. Boşluklar bozulmaz.
 * - Bozulma deterministiktir (``seed``): gürültüsü en düşük karakterler önce bozulur, çürüme
 *   arttıkça bozulan karakterler yalnızca çoğalır.
 */

/** Bu çürümeden sonra bozulma başlar (ömrün son %45'i). */
export const CORRUPT_FROM = 0.55;
/** Silinme anındaki bozulma oranı. İlk sürümde %16'ydı. */
export const MAX_RATE = 0.1;
export const GLITCH = ['░', '▒', '▓', '▚', '▞', '▙', '▟', '¦', '¤'];

/** Deterministik gürültü, [0, 1). */
export function noise(i: number, seed: number): number {
  const x = Math.sin(i * 12.9898 + seed * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

/** Bozulacak karakterlerin oranı: son %45'lik ömürde 0'dan üst sınıra doğrusal. */
export function corruptionRate(decay: number): number {
  const k = Math.max(0, Math.min(1, (decay - CORRUPT_FROM) / (1 - CORRUPT_FROM)));
  return k * MAX_RATE;
}

/** Metnin bozulmuş hâli. Oran boşluk dışı karakterlere göre hesaplanır. */
export function corrupt(text: string, decay: number, seed: number): string {
  const chars = Array.from(text);
  const visible = chars.map((c, i) => (c.trim() ? i : -1)).filter((i) => i >= 0);
  const budget = Math.floor(corruptionRate(decay) * visible.length);
  if (budget === 0) return text;
  const picked = visible.sort((a, b) => noise(a, seed) - noise(b, seed)).slice(0, budget);
  for (const i of picked) chars[i] = GLITCH[Math.floor(noise(i + 7, seed) * GLITCH.length)];
  return chars.join('');
}
