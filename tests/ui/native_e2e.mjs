// Native messaging end to end, like a user with HyperGet installed but closed:
// load the full extension (pinned ID), register the helper in the browser
// profile, open a video page, click "Download this video", pick 720p, and
// check HyperGet was started by the helper and finished the download.
// usage: HYPEGET_HOME=<dir> node tests/ui/native_e2e.mjs <page-url> <ext-dir> <profile-dir> <shot.png>
import { createRequire } from "module";
import fs from "fs"; import path from "path";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const [pageUrl, ext, profile, shot] = process.argv.slice(2);
const home = process.env.HYPEGET_HOME;

const ctx = await chromium.launchPersistentContext(profile, {
  channel: "chromium", headless: true, viewport: { width: 1000, height: 640 },
  args: [`--disable-extensions-except=${ext}`, `--load-extension=${ext}`],
  env: { ...process.env, HYPEGET_APP_ARGS: "--headless" },
});
let [sw] = ctx.serviceWorkers();
if (!sw) sw = await ctx.waitForEvent("serviceworker");
const extId = new URL(sw.url()).host;
console.log("extension id:", extId);
console.log("app running before:", fs.existsSync(path.join(home, "runtime.json")));

const page = await ctx.newPage();
await page.goto(pageUrl);
await page.waitForTimeout(800);
const box = await page.locator("video").boundingBox();
await page.mouse.move(box.x + 300, box.y + 200);
await page.waitForTimeout(300);
await page.mouse.click(box.x + box.width - 90, box.y + 25);
// first click may need to start HyperGet: wait for the quality list
let ok = false;
for (let i = 0; i < 40 && !ok; i++) { await page.waitForTimeout(500); ok = fs.existsSync(path.join(home, "runtime.json")); }
await page.waitForTimeout(2500);
await page.screenshot({ path: shot });
await page.mouse.click(box.x + box.width - 200, box.y + 25 + 36 + 46 + 34 + 17);   // 720p row
await page.waitForTimeout(2500);
const rt = JSON.parse(fs.readFileSync(path.join(home, "runtime.json"), "utf8"));
const st = await (await fetch(`http://127.0.0.1:${rt.port}/api/state`, { headers: { "X-HyperGet": "1" } })).json();
console.log("app started by helper:", ok, "pid", rt.pid);
console.log(JSON.stringify(st.downloads.map((d) => ({ name: d.filename, quality: d.quality, status: d.status }))));
// popup status through native messaging
const pop = await ctx.newPage();
await pop.goto(`chrome-extension://${extId}/popup.html`);
await pop.waitForTimeout(1200);
console.log("popup status:", await pop.locator("#status").innerText());
await ctx.close();
process.kill(rt.pid, "SIGTERM");
