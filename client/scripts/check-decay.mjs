/**
 * Mahzen çürümesinin kuralları (src/lib/decay.ts). scripts/test.sh çalıştırır:
 *   node scripts/check-decay.mjs
 * Bozulan karakter oranı başlıkta en fazla %15, gövdede en fazla %25; ömrün ilk %70'inde bozulma
 * yok; blok karakter yalnızca son %5'te; bozulmaların çoğu benzer görünen karakter.
 */
import assert from 'node:assert/strict';

import { BLOCKS_FROM, CORRUPT_FROM, MAX_RATE, corrupt } from '../src/lib/decay.ts';

const TITLES = [
  'Bir ağaç ormanda devrilirse ve kimse duymazsa ses çıkar mı?',
  'Müzik bir dil midir?',
  'Sokak kedileri kimindir?',
  'Oy vermemek de bir oy mudur?',
  "Theseus'un gemisi: parçaları tek tek değişen şey hâlâ aynı mıdır?",
  'Kura adil bir seçim yöntemi midir?',
];
const BODY = 'Kısa bir cevap arıyorum ama sanırım yok; iki tarafı da ikna edici buluyorum. >>12';
const BLOCK = /[░▒▓]/u;
const MARK = /[¤¦]/u;

let soft = 0;
let total = 0;
for (const [kind, texts] of [['title', TITLES], ['body', TITLES.map((t) => `${t} ${BODY}`)]]) {
  for (let step = 0; step <= 100; step++) {
    const decay = step / 100;
    texts.forEach((text, k) => {
      const src = Array.from(text);
      const out = Array.from(corrupt(text, decay, k + 1, kind));
      assert.equal(out.length, src.length, 'uzunluk değişmez');
      const changed = out.filter((c, i) => c !== src[i]);
      const visible = src.filter((c) => c.trim()).length;
      assert.ok(changed.length <= MAX_RATE[kind] * visible, `${kind} oranı aşıldı: ${decay} ${text}`);
      assert.ok(out.every((c, i) => src[i].trim() || c === src[i]), 'boşluk bozulmaz');
      if (decay < CORRUPT_FROM) assert.equal(changed.length, 0, `ömrün ilk %70'inde bozulma: ${decay}`);
      if (decay < BLOCKS_FROM) assert.ok(!out.some((c) => BLOCK.test(c)), `erken blok: ${decay}`);
      assert.equal(corrupt(text, decay, k + 1, kind), out.join(''), 'deterministik');
      for (const c of changed) {
        total += 1;
        if (!BLOCK.test(c) && !MARK.test(c)) soft += 1;
      }
    });
  }
}
assert.ok(total > 0 && soft / total > 0.75, `benzer karakter payı düşük: ${soft}/${total}`);
console.log(`çürüme kuralları: tamam (${total} bozulma, %${Math.round((soft / total) * 100)} benzer karakter)`);
