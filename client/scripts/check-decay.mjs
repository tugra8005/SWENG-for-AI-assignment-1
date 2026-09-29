/**
 * Mahzen çürümesinin kuralları (src/lib/decay.ts). scripts/test.sh çalıştırır:
 *   node scripts/check-decay.mjs
 * Bozulan karakter oranı en fazla %10; ömrün ilk %55'inde bozulma yok; bozulma yalnızca eski blok
 * glifleri (░▒▓▚▞▙▟ ¦ ¤) kullanır; çürüme arttıkça bozulan karakterler yalnızca çoğalır; boşluk
 * bozulmaz; aynı girdiyle aynı çıktı.
 */
import assert from 'node:assert/strict';

import { CORRUPT_FROM, GLITCH, MAX_RATE, corrupt } from '../src/lib/decay.ts';

const TITLES = [
  'Bir ağaç ormanda devrilirse ve kimse duymazsa ses çıkar mı?',
  'Müzik bir dil midir?',
  'Sokak kedileri kimindir?',
  'Oy vermemek de bir oy mudur?',
  "Theseus'un gemisi: parçaları tek tek değişen şey hâlâ aynı mıdır?",
  'Kura adil bir seçim yöntemi midir?',
];
const BODY = 'Kısa bir cevap arıyorum ama sanırım yok; iki tarafı da ikna edici buluyorum. >>12';
const TEXTS = [...TITLES, ...TITLES.map((t) => `${t} ${BODY}`)];

let total = 0;
TEXTS.forEach((text, k) => {
  const src = Array.from(text);
  const visible = src.filter((c) => c.trim()).length;
  let before = new Set();
  for (let step = 0; step <= 100; step++) {
    const decay = step / 100;
    const out = Array.from(corrupt(text, decay, k + 1));
    assert.equal(out.length, src.length, 'uzunluk değişmez');
    const changed = new Set(out.map((c, i) => (c !== src[i] ? i : -1)).filter((i) => i >= 0));
    assert.ok(changed.size <= MAX_RATE * visible, `oran aşıldı: ${decay} ${text}`);
    if (decay < CORRUPT_FROM) assert.equal(changed.size, 0, `ömrün ilk %55'inde bozulma: ${decay}`);
    for (const i of changed) {
      assert.ok(src[i].trim(), 'boşluk bozulmaz');
      assert.ok(GLITCH.includes(out[i]), `eski glif kümesinde değil: ${out[i]}`);
    }
    for (const i of before) assert.ok(changed.has(i), `bozulma geri alındı: ${decay} ${text}`);
    assert.equal(corrupt(text, decay, k + 1), out.join(''), 'deterministik');
    before = changed;
  }
  total += before.size;
});
assert.ok(total > 0, 'hiç bozulma yok');
console.log(`çürüme kuralları: tamam (silinme anında ${total} bozulan karakter, en fazla %${MAX_RATE * 100})`);
