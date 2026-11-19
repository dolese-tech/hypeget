const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1360, height: 880 }, deviceScaleFactor: 2 });
  for (const n of process.argv.slice(2)) {
    await p.goto('file://' + process.cwd() + '/' + n + '.html'); await p.waitForTimeout(250);
    await p.locator('.frame').screenshot({ path: '../' + n + '.png' });
  }
  await b.close();
})();
