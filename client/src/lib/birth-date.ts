/**
 * Kayıt formundaki doğum tarihi: yazarken "GG.AA.YYYY" maskesi ve anında denetim.
 *
 * Sunucu aynı kuralları uygular (api/src/mesveret/services/auth.py: gelecekte olamaz, 18 yaş
 * doldurulmuş olmalı, yaş ``age_on`` ile hesaplanır). Buradaki denetim kullanıcıya gönderimden
 * önce söyler; karar yine sunucunundur.
 */

export const MIN_AGE = 18;
const MONTHS = [
  'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
  'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık',
];

export type Ymd = { y: number; m: number; d: number };

export type BirthCheck =
  | { state: 'empty' }
  /** Yazılıyor; ``error`` yazılan kısım zaten geçersizse (gün 32, ay 13). */
  | { state: 'partial'; error?: string }
  | { state: 'invalid'; error: string }
  | { state: 'ok'; iso: string; label: string; age: number };

/**
 * Yazılanı maskeye oturtur: yalnızca rakamlar alınır, noktalar kendiliğinden eklenir.
 * Tek haneli gün ya da aydan sonra ayırıcı yazılırsa başına 0 eklenir ("1." → "01.").
 * "YYYY-AA-GG" yapıştırılırsa sıra çevrilir.
 */
export function maskBirthDate(raw: string): string {
  const iso = raw.trim().match(/^(\d{4})[-./](\d{1,2})[-./](\d{1,2})$/);
  if (iso) return `${iso[3].padStart(2, '0')}.${iso[2].padStart(2, '0')}.${iso[1]}`;
  let digits = '';
  let separator = false;
  for (const ch of raw) {
    if (ch >= '0' && ch <= '9') {
      digits += ch;
      separator = false;
      continue;
    }
    if (digits.length === 1 || digits.length === 3) {
      digits = `${digits.slice(0, -1)}0${digits.slice(-1)}`;
    }
    separator = digits.length === 2 || digits.length === 4;
  }
  digits = digits.slice(0, 8);
  const parts = [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4)].filter(Boolean);
  return parts.join('.') + (separator && digits.length < 8 ? '.' : '');
}

/** İstanbul'daki takvim günü (UTC+3; 2016'dan beri yaz saati yok). */
export function istanbulDate(ms: number): Ymd {
  const t = new Date(ms + 3 * 3600_000);
  return { y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate() };
}

function exists({ y, m, d }: Ymd): boolean {
  const t = new Date(Date.UTC(y, m - 1, d));
  return t.getUTCFullYear() === y && t.getUTCMonth() === m - 1 && t.getUTCDate() === d;
}

const before = (a: Ymd, b: Ymd) => a.y !== b.y ? a.y < b.y : a.m !== b.m ? a.m < b.m : a.d < b.d;

export function fmtYmd({ y, m, d }: Ymd): string {
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

/** Sunucudaki ``age_on`` ile aynı: doğum günü gelmediyse bir eksik. */
export function ageOn(birth: Ymd, on: Ymd): number {
  const years = on.y - birth.y;
  return (on.m < birth.m || (on.m === birth.m && on.d < birth.d)) ? years - 1 : years;
}

/** 18 yaşın dolduğu gün; 29 Şubat doğumlularda artık olmayan yılda 1 Mart. */
function adultOn(birth: Ymd): Ymd {
  const day = { y: birth.y + MIN_AGE, m: birth.m, d: birth.d };
  return exists(day) ? day : { y: day.y, m: 3, d: 1 };
}

export function checkBirthDate(text: string, today: Ymd): BirthCheck {
  if (!text) return { state: 'empty' };
  const [dd = '', mm = '', yyyy = ''] = text.split('.');
  if (dd.length === 2 && (+dd < 1 || +dd > 31)) {
    return { state: 'partial', error: 'Gün 01 ile 31 arasında olmalı.' };
  }
  if (mm.length === 2 && (+mm < 1 || +mm > 12)) {
    return { state: 'partial', error: 'Ay 01 ile 12 arasında olmalı.' };
  }
  if (!/^\d{2}\.\d{2}\.\d{4}$/.test(text)) return { state: 'partial' };
  const birth = { y: +yyyy, m: +mm, d: +dd };
  if (!exists(birth)) return { state: 'invalid', error: `${fmtYmd(birth)} diye bir gün yok.` };
  if (birth.y < 1900) return { state: 'invalid', error: 'Yılı kontrol edin: 1900 ve sonrası olmalı.' };
  if (before(today, birth)) return { state: 'invalid', error: 'Doğum tarihi gelecekte olamaz.' };
  const age = ageOn(birth, today);
  if (age < MIN_AGE) {
    return {
      state: 'invalid',
      error: `Kayıt için ${MIN_AGE} yaşını doldurmuş olmalısınız. ${MIN_AGE} yaşını dolduracağınız gün: ${fmtYmd(adultOn(birth))}.`,
    };
  }
  return { state: 'ok', iso: `${yyyy}-${mm}-${dd}`, label: fmtYmd(birth), age };
}
