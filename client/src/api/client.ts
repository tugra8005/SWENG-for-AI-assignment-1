/** Meşveret API istemcisi. Hata gövdesi: { detail, violations }. */

export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

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

export function setToken(value: string | null) {
  token = value;
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
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(url.toString(), {
      method: opts.method ?? 'GET',
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, `Sunucuya ulaşılamadı (${API_URL}).`);
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    throw new ApiError(res.status, describeValidation(data?.detail), data?.violations ?? []);
  }
  return data as T;
}
