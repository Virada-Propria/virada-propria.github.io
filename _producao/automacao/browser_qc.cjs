const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
(async () => {
  const [run, port] = process.argv.slice(2);
  const routes = JSON.parse(fs.readFileSync(path.join(run, 'browser-input.json'), 'utf8'));
  const origin = `http://127.0.0.1:${port}`;
  let browser;
  try { browser = await chromium.launch({channel: 'msedge', headless: true, args: ['--disable-gpu']}); }
  catch { browser = await chromium.launch({headless: true}); }
  const checks = [];
  fs.mkdirSync(path.join(run, 'screenshots'), {recursive: true});
  try {
    for (const width of [390, 1440]) {
      const page = await browser.newPage({viewport: {width, height: 900}});
      await page.route('**/*', route => route.request().url().startsWith(origin + '/') ? route.continue() : route.abort());
      for (let i = 0; i < routes.length; i++) {
        const route = routes[i];
        const response = await page.goto(origin + route, {waitUntil: 'networkidle'});
        // Load below-the-fold lazy images without bypassing the page's own loading behavior.
        await page.evaluate(async () => {
          for (const img of document.images) { img.scrollIntoView(); await new Promise(r => setTimeout(r, 50)); }
          await Promise.all([...document.images].map(img => img.decode().catch(() => {})));
          scrollTo(0, 0);
        });
        const metrics = await page.evaluate(() => ({
          overflow: document.documentElement.scrollWidth > innerWidth + 1,
          brokenImages: [...document.images].filter(x => !x.complete || !x.naturalWidth).map(x => x.getAttribute('src')),
          headerPosition: getComputedStyle(document.querySelector('header')).position,
          h1: document.querySelectorAll('h1').length
        }));
        const screenshot = `screenshots/${i}-${width}.png`;
        await page.screenshot({path: path.join(run, screenshot), fullPage: true, animations: 'disabled', timeout: 15000});
        checks.push({route, width, ...metrics, screenshot, ok: response.status() === 200 && !metrics.overflow && !metrics.brokenImages.length && !['sticky', 'fixed'].includes(metrics.headerPosition) && metrics.h1 === 1});
      }
      await page.close();
    }
  } finally { await browser.close(); }
  fs.writeFileSync(path.join(run, 'browser.json'), JSON.stringify({checks, note: 'Rede externa bloqueada no teste; fonte pode usar fallback. Capturas ainda exigem inspeção visual.'}, null, 2));
})().catch(error => { console.error(error); process.exit(1); });
