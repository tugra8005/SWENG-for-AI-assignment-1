/**
 * Kayıt formundaki doğum tarihi yardımcısı (src/lib/birth-date.ts). scripts/test.sh çalıştırır:
 *   node scripts/check-birth-date.mjs
 * Maske yazarken noktaları ekler, silmeyi bozmaz, tek haneli günü tamamlar; denetim sunucuyla
 * aynı yaşı hesaplar (18. doğum günü dahil) ve geçersiz tarihi hemen söyler.
 */
import assert from 'node:assert/strict';

import { ageOn, checkBirthDate, istanbulDate, maskBirthDate } from '../src/lib/birth-date.ts';

/** Karakter karakter yazma: her tuştan sonra alanın değeri maskeden geçer. */
function typeInto(keys, start = '') {
  let value = start;
  for (const k of keys) value = maskBirthDate(k === '\b' ? value.slice(0, -1) : value + k);
  return value;
}

// Yazarken noktalar kendiliğinden gelir.
assert.equal(typeInto('14031995'), '14.03.1995');
assert.equal(typeInto('1403'), '14.03');
assert.equal(typeInto('140'), '14.0');
// Nokta elle yazılırsa çift olmaz; tek haneli gün ve ay 0 ile tamamlanır.
assert.equal(typeInto('14.03.1995'), '14.03.1995');
assert.equal(typeInto('1.3.1995'), '01.03.1995');
assert.equal(typeInto('14.'), '14.');
assert.equal(typeInto('14..'), '14.');
// Geri silme her seferinde bir karakter alır; nokta takılıp kalmaz.
assert.equal(typeInto('\b', '14.03.1'), '14.03.');
assert.equal(typeInto('\b\b', '14.03.1'), '14.03');
assert.equal(typeInto('\b\b\b\b', '14.03.1'), '14.');
assert.equal(typeInto('\b\b\b\b\b', '14.03.1'), '14');
// Harf ve fazla rakam alınmaz; yapıştırılan ISO tarih çevrilir.
assert.equal(maskBirthDate('14a03b1995'), '14.03.1995');
assert.equal(maskBirthDate('140319951'), '14.03.1995');
assert.equal(maskBirthDate('1995-03-14'), '14.03.1995');
assert.equal(maskBirthDate(''), '');

// Sahte saat: Salı 29 Eylül 2026, 10:00 İstanbul (07:00 UTC); gün İstanbul'a göre.
const today = istanbulDate(Date.UTC(2026, 8, 29, 7));
assert.deepEqual(today, { y: 2026, m: 9, d: 29 });
assert.deepEqual(istanbulDate(Date.UTC(2026, 8, 29, 21, 30)), { y: 2026, m: 9, d: 30 });

const check = (text) => checkBirthDate(text, today);
assert.deepEqual(check(''), { state: 'empty' });
assert.deepEqual(check('14.0'), { state: 'partial' });
assert.equal(check('32').error, 'Gün 01 ile 31 arasında olmalı.');
assert.equal(check('00').error, 'Gün 01 ile 31 arasında olmalı.');
assert.equal(check('14.13').error, 'Ay 01 ile 12 arasında olmalı.');
assert.equal(check('31.02.1995').error, '31 Şubat 1995 diye bir gün yok.');
assert.equal(check('29.02.2001').state, 'invalid');
assert.equal(check('29.02.2000').state, 'ok');
assert.equal(check('01.01.1899').state, 'invalid');
assert.equal(check('30.09.2026').error, 'Doğum tarihi gelecekte olamaz.');

const ok = check('14.03.1995');
assert.deepEqual(ok, { state: 'ok', iso: '1995-03-14', label: '14 Mart 1995', age: 31 });

// 18 yaş sınırı sunucudaki age_on ile aynı: doğum günü bugünse dolmuş, yarınsa dolmamış.
assert.equal(check('29.09.2008').state, 'ok');
const young = check('30.09.2008');
assert.equal(young.state, 'invalid');
assert.match(young.error, /18 yaşını dolduracağınız gün: 30 Eylül 2026\.$/);
// 29 Şubat doğumlu: artık olmayan yılda 18 yaş 1 Mart'ta dolar.
assert.match(checkBirthDate('29.02.2012', { y: 2029, m: 9, d: 1 }).error, /1 Mart 2030\.$/);
assert.equal(ageOn({ y: 2012, m: 2, d: 29 }, { y: 2030, m: 2, d: 28 }), 17);
assert.equal(ageOn({ y: 2012, m: 2, d: 29 }, { y: 2030, m: 3, d: 1 }), 18);

console.log('doğum tarihi yardımcısı: tamam');
