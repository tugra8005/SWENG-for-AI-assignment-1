const TZ = 'Europe/Istanbul';

const dateFmt = new Intl.DateTimeFormat('tr-TR', {
  timeZone: TZ,
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});
const dateTimeFmt = new Intl.DateTimeFormat('tr-TR', {
  timeZone: TZ,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});
const longFmt = new Intl.DateTimeFormat('tr-TR', {
  timeZone: TZ,
  weekday: 'long',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
});
const timeFmt = new Intl.DateTimeFormat('tr-TR', { timeZone: TZ, hour: '2-digit', minute: '2-digit' });
const sessionFmt = new Intl.DateTimeFormat('tr-TR', {
  timeZone: TZ,
  day: 'numeric',
  month: 'long',
  weekday: 'long',
  hour: '2-digit',
  minute: '2-digit',
});
const numberFmt = new Intl.NumberFormat('tr-TR');

export const fmtDate = (iso?: string | null) => (iso ? dateFmt.format(new Date(iso)) : '—');
export const fmtDateTime = (iso?: string | null) => (iso ? dateTimeFmt.format(new Date(iso)) : '—');
export const fmtLong = (d: Date) => longFmt.format(d);
export const fmtTime = (iso?: string | null) => (iso ? timeFmt.format(new Date(iso)) : '—');

/** "11 Ekim Pazar 20:00" — Karar Saati oturumunu anmak için. */
export const fmtSession = (iso?: string | null) => (iso ? sessionFmt.format(new Date(iso)) : '—');
export const fmtNumber = (n: number) => numberFmt.format(n);
/** Türkçe yüzde: "%20". */
export const fmtPercent = (part: number, whole: number) => `%${Math.round((part / whole) * 100)}`;

export const shortHash = (h?: string | null) => (h ? h.slice(0, 8) : '········');

const pad = (n: number) => String(n).padStart(2, '0');

/** "3g 04:12:09" biçiminde kalan süre. */
export function fmtCountdown(ms: number): string {
  if (ms <= 0) return '00:00:00';
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${d > 0 ? `${d}g ` : ''}${pad(h)}:${pad(m)}:${pad(sec)}`;
}

/** "14 saat sonra" gibi kısa ifade. */
export function fmtRemaining(ms: number): string {
  if (ms <= 0) return 'süre doldu';
  const h = ms / 3_600_000;
  if (h < 1) return `${Math.max(1, Math.round(ms / 60000))} dakika kaldı`;
  if (h < 48) return `${Math.round(h)} saat kaldı`;
  return `${Math.round(h / 24)} gün kaldı`;
}

export const STATUS_LABELS: Record<string, string> = {
  DRAFT: 'Taslak',
  SILENT: 'Sessiz onayda',
  RIVAL_PERIOD: 'Rakip metin süresi',
  QUEUED: 'Karar Saati kuyruğunda',
  VOTING: 'Oylamada',
  ACCEPTED: 'Kabul edildi',
  REJECTED: 'Reddedildi',
};

export const TYPE_LABELS: Record<string, string> = {
  KONU: 'Konu',
  ALT_KONU: 'Alt konu',
  DUZENLEME: 'Düzenleme',
  SILME: 'Silme',
  YONETMELIK: 'Yönetmelik',
  KAPANIS: 'Kapanış',
};

export function describeArticleValue(kind: string, value: any): string {
  if (!value) return '—';
  if (kind === 'sure') {
    if ('dakika' in value) return `${value.dakika} dakika`;
    if ('saat' in value) return `${value.saat} saat`;
    return `${value.gun} gün`;
  }
  if (kind === 'oran') return `${value.karsilastirma === '>' ? '>' : '≥'} ${value.oran}`;
  if (kind === 'tamsayi' || kind === 'sayi') return String(value.deger);
  if (kind === 'itiraz') return `max(${value.min}, aktif üyelerin ${value.oran}'i) · aktif: son ${value.aktiflik_gun} gün`;
  if (kind === 'karar_saati') {
    const day = String(value.gun).charAt(0) + String(value.gun).slice(1).toLowerCase();
    return `${day} ${value.saat} · ${value.pencere_dakika} dk pencere`;
  }
  return Object.entries(value)
    .map(([k, v]) => `${k}: ${v}`)
    .join(' · ');
}
