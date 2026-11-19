// End-to-end: load the extension, hover the video, pick a quality, check HyperGet got it.
// usage: node tests/ui/extension_e2e.mjs <page-url> <hyperget-port> <screenshot.png>
import { createRequire } from "module";
import os from "os"; import fs from "fs"; import path from "path";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const [pageUrl, port, shot] = process.argv.slice(2);
const ext = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../../extension");
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "hg-ext-"));
const ctx = await chromium.launchPersistentContext(dir, {
  channel: "chromium", headless: true, viewport: { width: 1000, height: 640 },
  args: [`--disable-extensions-except=${ext}`, `--load-extension=${ext}`],
});
let [sw] = ctx.serviceWorkers();
if (!sw) sw = await ctx.waitForEvent("serviceworker");
await sw.evaluate((p) => chrome.storage.local.set({ port: +p }), port);
const page = await ctx.newPage();
await page.goto(pageUrl);
await page.waitForTimeout(800);
const box = await page.locator("video").boundingBox();
await page.mouse.move(box.x + 300, box.y + 200);
await page.waitForTimeout(400);
// button lives in a closed shadow root: click by position (top-right of the video)
await page.mouse.click(box.x + box.width - 90, box.y + 25);
await page.waitForTimeout(2500);
await page.screenshot({ path: shot });
// pick 720p: second option row in the menu (menu ~36px below button, rows ~34px)
const before = await (await fetch(`http://127.0.0.1:${port}/api/state`, { headers: { "X-HyperGet": "1" } })).json();
await page.mouse.click(box.x + box.width - 200, box.y + 25 + 36 + 46 + 34 + 17);
await page.waitForTimeout(1500);
const after = await (await fetch(`http://127.0.0.1:${port}/api/state`, { headers: { "X-HyperGet": "1" } })).json();
const added = after.downloads.filter((d) => !before.downloads.some((b) => b.id === d.id));
console.log(JSON.stringify(added.map((d) => ({ name: d.filename, quality: d.quality, kind: d.kind, status: d.status, page: d.page_url }))));
await ctx.close();
