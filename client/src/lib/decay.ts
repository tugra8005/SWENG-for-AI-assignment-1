/**
 * Mahzen çürümesi: metin okunur kalır.
 *
 * - ``decay`` 0 (taze) → 1 (silinmek üzere); ``1 - ömür``.
 * - Ömrün ilk %70'inde yalnızca soluklaşma olur (renk, bkz. ``DecayText``); bozulma son %30'da
 *   başlar ve orada doğrusal artar.
 * - Bozulan karakter oranı başlıkta en fazla %15, gövdede en fazla %25. Sınır sert bir üst sınırdır:
 *   kısa metinde bile aşılmaz (karakterler rastgele eşikle değil, sayıyla seçilir).
 * - Bozulmaların çoğu benzer görünen karakterdir (s → ş, o → ö, i → ı); tek tük ¤ ¦. Blok
 *   karakterler (░▒▓) yalnızca silinmeye çok yakın başlıklarda.
 * - Bozulma deterministiktir (``seed``); her çizimde aynı karakterler bozulur.
 */

export type DecayKind = 'title' | 'body';

/** Bu çürümeden sonra bozulma başlar (ömrün son %30'u). */
export const CORRUPT_FROM = 0.7;
/** Blok karakterler yalnızca bu çürümeden sonra (ömrün son %5'i). */
export const BLOCKS_FROM = 0.95;
export const MAX_RATE: Record<DecayKind, number> = { title: 0.15, body: 0.25 };

const LOOKALIKE: Record<string, string> = {
  a: 'â', e: 'ê', i: 'ı', ı: 'i', o: 'ö', ö: 'o', u: 'ü', ü: 'u', s: 'ş', ş: 's', c: 'ç', ç: 'c',
  g: 'ğ', ğ: 'g', l: 'ł', n: 'ñ', t: 'ţ', z: 'ž', y: 'ÿ', k: 'ķ', d: 'đ', r: 'ŕ', h: 'ħ',
  A: 'Â', E: 'Ê', I: 'İ', İ: 'I', O: 'Ö', Ö: 'O', U: 'Ü', Ü: 'U', S: 'Ş', Ş: 'S', C: 'Ç', Ç: 'C',
  G: 'Ğ', Ğ: 'G', L: 'Ł', N: 'Ñ', T: 'Ţ', Z: 'Ž', Y: 'Ÿ', K: 'Ķ', D: 'Đ', R: 'Ŕ', H: 'Ħ',
  '0': 'O', '1': 'l', '5': 'S', '?': '¿', '!': '¡',
};
const MARKS = ['¤', '¦'];
const BLOCKS = ['░', '▒', '▓'];

/** Deterministik gürültü, [0, 1). */
export function noise(i: number, seed: number): number {
  const x = Math.sin(i * 12.9898 + seed * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

/** Bozulacak karakterlerin oranı: son %30'luk ömürde 0'dan üst sınıra doğrusal. */
export function corruptionRate(decay: number, kind: DecayKind): number {
  const k = Math.max(0, Math.min(1, (decay - CORRUPT_FROM) / (1 - CORRUPT_FROM)));
  return k * MAX_RATE[kind];
}

/** Metnin bozulmuş hâli. Boşluklar hiç bozulmaz; oran boşluk dışı karakterlere göre hesaplanır. */
export function corrupt(text: string, decay: number, seed: number, kind: DecayKind): string {
  const chars = Array.from(text);
  const visible = chars.map((c, i) => (c.trim() ? i : -1)).filter((i) => i >= 0);
  const budget = Math.floor(corruptionRate(decay, kind) * visible.length);
  if (budget === 0) return text;
  // Benzeri olan karakterler önce seçilir: bozulma çoğunlukla hafif kalır.
  const byNoise = (a: number, b: number) => noise(a, seed) - noise(b, seed);
  const soft = visible.filter((i) => LOOKALIKE[chars[i]]).sort(byNoise);
  const rest = visible.filter((i) => !LOOKALIKE[chars[i]]).sort(byNoise);
  const nearEnd = decay >= BLOCKS_FROM;
  for (const i of [...soft, ...rest].slice(0, budget)) {
    const r = noise(i + 7, seed);
    if (nearEnd && r < 0.3) chars[i] = BLOCKS[Math.floor(noise(i + 13, seed) * BLOCKS.length)];
    else if (r >= 0.92 || !LOOKALIKE[chars[i]]) chars[i] = MARKS[Math.floor(noise(i + 11, seed) * MARKS.length)];
    else chars[i] = LOOKALIKE[chars[i]];
  }
  return chars.join('');
}
