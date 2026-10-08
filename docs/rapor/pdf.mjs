// rapor.html → A4 PDF (sayfa numaralı alt bilgiyle).
//   python3 docs/rapor/olustur.py && node docs/rapor/pdf.mjs
// playwright-core ve Chromium gerekir: PLAYWRIGHT_CORE (modül yolu) ve CHROME (çalıştırılabilir)
// ortam değişkenleriyle verilir; verilmezse modül normal yoldan aranır, tarayıcıyı Playwright seçer.
import { createRequire } from 'module';
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
await page.pdf({
  path: out, format: 'A4', preferCSSPageSize: true, printBackground: true, displayHeaderFooter: true,
  headerTemplate: '<span></span>',
  footerTemplate: '<div style="width:100%;font-family:monospace;font-size:7pt;color:#6B6558;padding:0 17mm;'
    + 'display:flex;justify-content:space-between"><span>MEŞVERET · Analiz, Tasarım ve Politikalar</span>'
    + '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',
});
await browser.close();
console.log(out + ' yazıldı');
