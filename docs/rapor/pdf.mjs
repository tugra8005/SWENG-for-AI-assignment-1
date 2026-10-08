// rapor.html → A4 PDF (sayfa numaralı alt bilgiyle; kapakta alt bilgi yok).
//   python3 docs/rapor/olustur.py && node docs/rapor/pdf.mjs
// playwright-core ve Chromium gerekir: PLAYWRIGHT_CORE (modül yolu) ve CHROME (çalıştırılabilir)
// ortam değişkenleriyle verilir; verilmezse modül normal yoldan aranır, tarayıcıyı Playwright seçer.
// Kapak ayrı basılıp pdfunite (poppler) ile başa eklenir; pdfunite yoksa kapak da alt bilgili basılır.
import { execFileSync } from 'child_process';
import { mkdtempSync, rmSync } from 'fs';
import { createRequire } from 'module';
import { tmpdir } from 'os';
import { fileURLToPath } from 'url';
import path from 'path';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');
const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.join(here, 'rapor.html');
const out = path.join(here, 'Mesveret-Analiz-Tasarim-Politikalar.pdf');

const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
const page = await browser.newPage();
await page.goto('file://' + src, { waitUntil: 'load' });
await page.evaluate(() => document.fonts.ready);
const missing = await page.evaluate(() =>
  [...document.images].filter((i) => !i.complete || i.naturalWidth === 0).map((i) => i.src));
const fonts = await page.evaluate(() => [...document.fonts].filter((f) => f.status !== 'loaded').map((f) => f.family));
if (missing.length || fonts.length) {
  console.error('Yüklenmeyen görsel ya da yazı tipi:', missing, fonts);
  process.exitCode = 1;
}
const base = { format: 'A4', preferCSSPageSize: true, printBackground: true };
const footer = {
  displayHeaderFooter: true,
  headerTemplate: '<span></span>',
  footerTemplate: '<div style="width:100%;font-family:monospace;font-size:7pt;color:#6B6558;padding:0 17mm;'
    + 'display:flex;justify-content:space-between"><span>MEŞVERET · Analiz, Tasarım ve Politikalar</span>'
    + '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',
};
let unite = true;
try {
  execFileSync('pdfunite', ['-v'], { stdio: 'ignore' });
} catch {
  unite = false;
}
if (unite) {
  // Sayfa aralığıyla basılan gövdede numaralar belgedeki yerini korur ("2 / N").
  const dir = mkdtempSync(path.join(tmpdir(), 'rapor-'));
  const cover = path.join(dir, 'kapak.pdf');
  const body = path.join(dir, 'govde.pdf');
  await page.pdf({ ...base, path: cover, pageRanges: '1' });
  await page.pdf({ ...base, ...footer, path: body, pageRanges: '2-' });
  execFileSync('pdfunite', [cover, body, out]);
  rmSync(dir, { recursive: true, force: true });
} else {
  await page.pdf({ ...base, ...footer, path: out });
}
await browser.close();
console.log(out + ' yazıldı');
