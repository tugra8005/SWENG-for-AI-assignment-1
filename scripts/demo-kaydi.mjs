/**
 * Sınıf gösteriminin baştan sona otomatik çalıştırması: video kaydı, süre ölçümü ve ekranda görünen
 * sayıların karşılaştırması.
 *
 *   PLAYWRIGHT_CORE=<playwright-core dizini> CHROME=<chrome yolu> \
 *     node scripts/demo-kaydi.mjs run A [--video docs/demo.mp4]
 *   node scripts/demo-kaydi.mjs md        # iki ölçümü karşılaştırır, DEMO.md'deki süreleri günceller
 *
 * Her adım: `meşveret-dev demo next` (1. adım `demo goto 1` ile kurulur, ölçüme girmez), ardından
 * adımın her ekranı sağ alttaki geliştirme menüsünden açılır (o kullanıcıyla giriş + sayfa) ve
 * DEMO.md'deki tıklamalar yapılır. Adım, konuşma notunun okunma süresi (dakikada 132 kelime) kadar
 * ekranda kalır; video canlı anlatımın yedeği olarak üstünden konuşulabilsin diye.
 * Her ekranda sayfadaki rakam içeren bütün dizgiler ve sonunda defterin hash zinciri kaydedilir.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BASE = process.env.BASE ?? 'http://localhost:8081';
const LEDGER = process.env.LEDGER ?? 'http://localhost:8101';
const OUT = path.join(ROOT, 'docs', 'demo-olcum');
const WORDS_PER_SECOND = 2.2;
const SERH = 'Akşam 20:00 çalışan annelerin parkı kullanmasını imkânsız kılıyordu; itirazımı kayda geçiriyorum.';

function notes() {
  const md = fs.readFileSync(path.join(ROOT, 'DEMO.md'), 'utf8');
  const re = /^### Adım (\S+) · ([^\n]+)\n(.*?)^> \*\*Konuşma:\*\* ([^\n]+)$/gms;
  return [...md.matchAll(re)].map((m) => ({ key: m[1], title: m[2], note: m[4], words: m[4].split(/\s+/).length }));
}

function cli(...args) {
  const t = Date.now();
  const out = execFileSync('docker', ['compose', 'exec', '-T', 'api', 'meşveret-dev', 'demo', ...args],
    { cwd: ROOT, encoding: 'utf8' });
  return { ms: Date.now() - t, out };
}

async function settle(page) {
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
}

async function show(page, text, opts = {}) {
  const el = page.getByText(text, { exact: false, ...opts }).first();
  await el.waitFor({ timeout: 30000 });
  await el.evaluate((e) => e.scrollIntoView({ block: 'center', behavior: 'smooth' }));
  await page.waitForTimeout(700);
}

async function click(page, text, exact = false) {
  const el = page.getByText(text, { exact }).first();
  await el.waitFor({ timeout: 30000 });
  await el.evaluate((e) => e.scrollIntoView({ block: 'center' }));
  await el.click();
}

async function fill(page, label, value) {
  const el = page.getByLabel(label, { exact: true }).first();
  await el.waitFor({ timeout: 30000 });
  await el.evaluate((e) => e.scrollIntoView({ block: 'center' }));
  await el.pressSequentially(value, { delay: 25 });
}

/** DEMO.md'deki tıklamalar: adım → ekran sırası. */
const ACTS = {
  1: [
    async (p) => { await show(p, 'Yalnızca size görünür'); await p.waitForTimeout(1500); await show(p, 'Kapsam üyelikleri'); },
    async (p) => { await show(p, 'Yurttaş Kayıt Belgesi'); },
  ],
  2: [async (p) => { await show(p, 'Sessiz onay'); }],
  3: [
    async (p) => { await show(p, 'otomatik daralma'); },
    async (p) => { await show(p, 'otomatik daralma'); },
  ],
  4: [async (p) => { await show(p, 'Pay etkisi'); await p.waitForTimeout(1500); await show(p, "Genel'de geçti"); }],
  5: [
    async (p) => { await show(p, 'kabulünüzü bekliyor'); await p.waitForTimeout(1500); await show(p, 'Verdiğiniz havaleler'); },
    async (p) => { await p.getByText('Yeniden oynat').first().waitFor({ timeout: 60000 }); },
    async (p) => { await show(p, 'Karar Saati #1 sonuçlandı'); await show(p, 'havaleyle ceren'); },
  ],
  6: [async (p) => {
    await show(p, 'Şerhler');
    await click(p, 'Şerh ekle', true);
    await fill(p, 'Şerh metni', SERH);
    await click(p, 'Şerhi mühürle', true);
    await show(p, SERH.slice(0, 30));
  }],
  7: [
    async (p) => { await show(p, 'IK-1 gereğince silindi'); },
    async (p) => {
      await fill(p, 'Gerekçe', 'Bu mesajı beğenmedim.');
      await click(p, 'Öneriyi aç', true);
      await show(p, 'R7', { exact: true });
    },
  ],
  8: [
    async (p) => {
      const f = p.getByLabel('Yeni oran (pay/payda)', { exact: true }).first();
      await f.waitFor({ timeout: 30000 });
      await f.fill('');
      await fill(p, 'Yeni oran (pay/payda)', '1/2');
      await click(p, '>  (fazlası)', true);
      await click(p, 'Öneriyi aç', true);
      await show(p, 'R8', { exact: true });
    },
    async (p) => { await click(p, 'Öneriyi aç', true); await show(p, 'R8', { exact: true }); },
  ],
  9: [
    async (p) => {
      await click(p, 'anladım, devam');
      await p.getByText('Çoğunluk haklı olabilir mi?').first().waitFor({ timeout: 30000 });
      await p.waitForTimeout(1500);
      await show(p, 'No.1 ·');  // listenin sonu: çürümüş başlık (metni bozuk, numarası değil)
    },
    async (p) => {
      await p.getByText('Köylüleri niçin öldürmeliyiz?').first().waitFor({ timeout: 30000 });
      await p.waitForTimeout(1500);
      await show(p, 'NASIL KURTARALIM?');
      await p.waitForTimeout(1500);
      await show(p, 'karar veremedim');
    },
    async (p) => {
      await click(p, '[ evet ]', true);
      await p.getByText('ifşa edildi').first().waitFor({ timeout: 30000 });
      await p.waitForTimeout(1500);
    },
  ],
  '10a': [async (p) => {
    await p.getByRole('button', { name: 'Doğrula', exact: true }).click();
    await show(p, 'Yönetmelik: FARKLI');
  }],
  '10b': [async (p) => {
    await p.getByRole('button', { name: 'Doğrula', exact: true }).click();
    await show(p, 'Yönetmelik: tutarlı');
    await p.waitForTimeout(1200);
    await show(p, 'GERİ ALINDI');
  }],
};

/** Sayfada görünen, rakam içeren bütün dizgiler (geliştirme menüsü dahil). */
async function numbers(page) {
  const text = await page.evaluate(() => document.body.innerText);
  return text.match(/[^\s]*\d[^\s]*/g) ?? [];
}

async function openFromMenu(page, i, screen) {
  await page.getByRole('button', { name: 'Geliştirme menüsü' }).click();
  const label = `${i + 1}) ${screen.user} → ${screen.path}`;
  const entry = page.getByText(label, { exact: true });
  await entry.waitFor({ timeout: 15000 });
  const want = new URL(BASE + screen.path).pathname;
  const nav = page.waitForURL((u) => u.pathname === want, { timeout: 30000 });
  await entry.click();
  await nav;
  await settle(page);
}

async function run(label, videoOut) {
  const { chromium } = createRequire(import.meta.url)(process.env.PLAYWRIGHT_CORE);
  fs.mkdirSync(OUT, { recursive: true });
  const steps = notes();
  console.log('demo goto 1 …');
  cli('goto', '1');
  const browser = await chromium.launch({ executablePath: process.env.CHROME });
  const videoDir = path.join(OUT, `video-${label}`);
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 }, locale: 'tr-TR', timezoneId: 'Europe/Istanbul',
    recordVideo: { dir: videoDir, size: { width: 1440, height: 900 } },
  });
  const page = await context.newPage();
  await page.goto(BASE + '/');
  await settle(page);
  const result = { label, started: new Date().toISOString(), steps: [] };
  for (const step of steps) {
    const t0 = Date.now();
    const transition = step.key === '1' ? { ms: 0, out: '' } : cli('next');
    const view = await (await fetch('http://localhost:8000/_dev/demo')).json();
    if (view.step !== step.key) throw new Error(`beklenen adım ${step.key}, yığın ${view.step}`);
    const speakMs = (step.words / WORDS_PER_SECOND) * 1000;
    const perScreen = speakMs / view.screens.length;
    const screens = [];
    for (const [i, sc] of view.screens.entries()) {
      const s0 = Date.now();
      await openFromMenu(page, i, sc);
      await ACTS[step.key][i](page);
      const mechMs = Date.now() - s0;
      screens.push({ user: sc.user, path: sc.path, mech_ms: mechMs, numbers: await numbers(page) });
      await page.waitForTimeout(Math.max(1200, perScreen - mechMs));
    }
    const total = Date.now() - t0;
    const mech = transition.ms + screens.reduce((a, s) => a + s.mech_ms, 0);
    result.steps.push({ key: step.key, title: step.title, cli_ms: transition.ms, mech_ms: mech,
                        speak_ms: Math.round(speakMs), total_ms: total, screens });
    console.log(`${step.key.padEnd(4)} ${String(Math.round(total / 1000)).padStart(3)} sn ` +
                `(komut ${(transition.ms / 1000).toFixed(1)} sn, işlem ${(mech / 1000).toFixed(1)} sn) ${step.title}`);
  }
  const video = page.video();
  await context.close();
  await browser.close();
  const records = [];
  for (let from = 1; ; from += 500) {
    const batch = await (await fetch(`${LEDGER}/records?from_seq=${from}&limit=500`)).json();
    records.push(...batch.map((r) => r.hash));
    if (batch.length < 500) break;
  }
  result.ledger = { length: records.length, hashes: records };
  result.total_ms = result.steps.reduce((a, s) => a + s.total_ms, 0);
  fs.writeFileSync(path.join(OUT, `olcum-${label}.json`), JSON.stringify(result, null, 1));
  const webm = await video.path();
  if (videoOut) {
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', webm, '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                            '-crf', '26', '-preset', 'medium', '-movflags', '+faststart', path.resolve(ROOT, videoOut)]);
    console.log(`video: ${videoOut}`);
  }
  fs.rmSync(videoDir, { recursive: true, force: true });
  console.log(`toplam ${Math.round(result.total_ms / 1000)} sn · defter ${records.length} kayıt`);
}

function compare() {
  const a = JSON.parse(fs.readFileSync(path.join(OUT, 'olcum-A.json'), 'utf8'));
  const b = JSON.parse(fs.readFileSync(path.join(OUT, 'olcum-B.json'), 'utf8'));
  const rows = [];
  let allSame = true;
  for (const [i, sa] of a.steps.entries()) {
    const sb = b.steps[i];
    const diffs = [];
    sa.screens.forEach((sc, j) => {
      const x = sc.numbers.join(' ');
      const y = sb.screens[j].numbers.join(' ');
      if (x !== y) {
        const xs = sc.numbers, ys = sb.screens[j].numbers;
        const k = xs.findIndex((v, n) => v !== ys[n]);
        diffs.push(`ekran ${j + 1}: ${xs[k] ?? '∅'} ≠ ${ys[k] ?? '∅'}`);
      }
    });
    allSame &&= diffs.length === 0;
    rows.push({ key: sa.key, title: sa.title, a: sa.total_ms, b: sb.total_ms, mech: [sa.mech_ms, sb.mech_ms],
                speak: sa.speak_ms, count: sa.screens.reduce((n, s) => n + s.numbers.length, 0), diffs });
  }
  const ledgerSame = a.ledger.hashes.join() === b.ledger.hashes.join();
  return { rows, allSame, ledgerSame, a, b };
}

function sec(ms) {
  return (ms / 1000).toFixed(1).replace('.', ',');
}

function updateMd() {
  const { rows, allSame, ledgerSame, a, b } = compare();
  let md = fs.readFileSync(path.join(ROOT, 'DEMO.md'), 'utf8');
  for (const r of rows) {
    const re = new RegExp(`(### Adım ${r.key} · [^\\n]+\\n\\*\\*Süre:\\*\\* )[^·]+·`);
    md = md.replace(re, `$1${Math.round((r.a + r.b) / 2000)} sn ·`);
  }
  const lines = [
    '<!-- ölçüm: scripts/demo-kaydi.mjs --md ile güncellenir -->',
    `İki çalıştırma (A: ${a.started.slice(0, 16).replace('T', ' ')} UTC, B: ${b.started.slice(0, 16).replace('T', ' ')} UTC), 1440 × 900 Chromium, Docker yığını. ` +
      '*Süre* adımın ekranda kaldığı toplam süredir: `demo next` komutu, sayfaların menüden açılması, tıklamalar, ' +
      'canlandırmalar ve konuşma notunun okunma süresine (dakikada 132 kelime) tamamlayan bekleme. *İşlem* bunlardan ' +
      'yalnızca komut, sayfa ve tıklama kısmıdır; canlıda konuşma bununla üst üste biner.',
    '',
    '| Adım | A (sn) | B (sn) | İşlem A / B (sn) | Konuşma (sn) | Ekrandaki sayılar | A = B |',
    '|---|---|---|---|---|---|---|',
    ...rows.map((r) => `| ${r.key} · ${r.title} | ${sec(r.a)} | ${sec(r.b)} | ${sec(r.mech[0])} / ${sec(r.mech[1])} | ` +
      `${sec(r.speak)} | ${r.count} | ${r.diffs.length ? '✗ ' + r.diffs.join('; ') : '✓'} |`),
    `| **Toplam** | **${sec(a.total_ms)}** | **${sec(b.total_ms)}** | | | | ${allSame ? '✓' : '✗'} |`,
    '',
    `Defter: A ${a.ledger.length} kayıt, B ${b.ledger.length} kayıt; hash zinciri ${ledgerSame ? 'birebir aynı' : 'FARKLI'}.`,
  ];
  md = md.replace(/<!-- ölçüm: scripts\/demo-kaydi\.mjs --md ile güncellenir -->[\s\S]*$/, lines.join('\n') + '\n');
  fs.writeFileSync(path.join(ROOT, 'DEMO.md'), md);
  console.log(lines.join('\n'));
}

const [cmd, label, flag, videoOut] = process.argv.slice(2);
if (cmd === 'run') await run(label, flag === '--video' ? videoOut : null);
else if (cmd === 'md') updateMd();
else console.log('kullanım: node scripts/demo-kaydi.mjs run A [--video docs/demo.mp4] | md');
