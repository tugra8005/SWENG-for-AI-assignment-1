import Constants from 'expo-constants';
import { Platform } from 'react-native';

/** Meşveret API istemcisi. Hata gövdesi: { detail, violations }. */

const LOCAL = new Set(['localhost', '127.0.0.1', '::1', '[::1]']);

/**
 * API adresi. ``EXPO_PUBLIC_API_URL`` bilgisayarın kendisini gösteriyorsa (localhost) ve uygulama
 * başka bir makineden açılmışsa (telefonun tarayıcısı ya da Expo Go, aynı Wi-Fi), adres o makinenin
 * adresine çevrilir: telefonda "localhost" telefonun kendisidir, API'ye ulaşılamaz, giriş yapılamaz.
 * Emülatör ``adb reverse`` ile 127.0.0.1 kullanır; ona dokunulmaz.
 */
function resolveApiUrl(): string {
  const base = new URL(process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000');
  if (LOCAL.has(base.hostname)) {
    let host: string | undefined;
    if (Platform.OS === 'web' && typeof window !== 'undefined') host = window.location.hostname;
    else host = Constants.expoConfig?.hostUri?.split(':')[0];
    if (host && !LOCAL.has(host)) base.hostname = host;
  }
  return base.toString().replace(/\/$/, '');
}

export const API_URL = resolveApiUrl();

export type Violation = { rule: string; message: string };

export class ApiError extends Error {
  status: number;
  violations: Violation[];

  constructor(status: number, message: string, violations: Violation[] = []) {
    super(message);
    this.status = status;
    this.violations = violations;
  }
}

let token: string | null = null;
let onAuthLost: (() => void) | null = null;

export function setToken(value: string | null) {
  token = value;
}

/** Sunucu anahtarı reddettiğinde (ör. tohum yeniden kurulduktan sonra) çağrılır. */
export function setAuthLostHandler(handler: (() => void) | null) {
  onAuthLost = handler;
}

type Options = {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
};

/** Sunucunun doğrulama hatalarındaki alan adları → formlardaki Türkçe etiketler. */
const FIELD_LABELS: Record<string, string> = {
  full_name: 'Ad soyad',
  email: 'E-posta',
  nickname: 'Takma ad',
  password: 'Şifre',
  birth_date: 'Doğum tarihi',
  city: 'İl',
  district: 'İlçe',
  address_line: 'Açık adres',
  code: 'Doğrulama kodu',
  identifier: 'Takma ad ya da e-posta',
  title: 'Başlık',
  body: 'Metin',
  text: 'Metin',
  new_text: 'Yeni metin',
  new_value: 'Yeni değer',
  area_id: 'Alan',
  scope_id: 'Seçmen kapsamı',
  resource_ids: 'Etkilenen kaynaklar',
  target: 'Takma ad',
};

function describeValidation(detail: unknown): string {
  if (Array.isArray(detail)) {
    const fields = detail
      .map((d: { loc?: unknown[] }) => (Array.isArray(d.loc) ? String(d.loc[d.loc.length - 1]) : ''))
      .filter(Boolean)
      .map((f) => FIELD_LABELS[f] ?? f);
    return fields.length ? `Formdaki alanları kontrol edin: ${fields.join(', ')}.` : 'Form geçersiz.';
  }
  return typeof detail === 'string' ? detail : 'Beklenmeyen bir hata oluştu.';
}

export async function api<T = any>(path: string, opts: Options = {}): Promise<T> {
  const url = new URL(API_URL + path);
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
  }
  const headers: Record<string, string> = { Accept: 'application/json' };
  // FormData (görsel yükleme): sınır (boundary) içeren Content-Type'ı fetch kendisi yazar.
  const form = typeof FormData !== 'undefined' && opts.body instanceof FormData;
  if (opts.body !== undefined && !form) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(url.toString(), {
      method: opts.method ?? 'GET',
      headers,
      body: form ? (opts.body as FormData) : opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, `Sunucuya ulaşılamadı (${API_URL}).`);
  }
  if (res.status === 401 && token && headers.Authorization) {
    // Geçersiz anahtar: bırak, oturumu kapat; okuma isteğini anonim olarak yeniden dene.
    token = null;
    onAuthLost?.();
    if ((opts.method ?? 'GET') === 'GET') return api<T>(path, opts);
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    throw new ApiError(res.status, describeValidation(data?.detail), data?.violations ?? []);
  }
  return data as T;
}

/** Görselin adresi: ``baski`` yarım ton (sitede gösterilen), ``ozgun`` EXIF'siz renkli fotoğraf. */
export function mediaUrl(id: string, variant: 'baski' | 'ozgun' = 'baski'): string {
  return `${API_URL}/media/${id}/${variant}`;
}

export type MediaItem = {
  id: string;
  alt: string;
  width: number;
  height: number;
  credit?: string | null;
  source_url?: string | null;
  ledger_hash?: string | null;
};

/** Seçilen dosya: web'de ``file`` (File), telefonda ``uri`` + ad + tür. */
export type PickedFile = { uri: string; name: string; type: string; file?: Blob };

export async function uploadImage(picked: PickedFile, alt: string): Promise<MediaItem> {
  const form = new FormData();
  if (picked.file) form.append('file', picked.file, picked.name);
  // React Native'in FormData'sı dosyayı {uri, name, type} nesnesiyle alır.
  else form.append('file', { uri: picked.uri, name: picked.name, type: picked.type } as any);
  form.append('alt', alt);
  return api<MediaItem>('/media', { method: 'POST', body: form });
}
