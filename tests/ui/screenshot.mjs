// Render the UI at 1280x800 with the mockup's data and save a screenshot.
// usage: node tests/ui/screenshot.mjs <base-url> <out.png> [--live] [--dark] [--scale=1]
import { createRequire } from "module";
import { mockState } from "./mock_state.mjs";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const [base, out] = process.argv.slice(2);
const live = process.argv.includes("--live");
const dark = process.argv.includes("--dark");
const scale = +(process.argv.find((a) => a.startsWith("--scale="))?.split("=")[1] || 1);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: scale });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
await page.addInitScript((theme) => {
  window.pywebview = { api: {} };   // show the window controls like the native app
  try { localStorage.setItem("hg-ui", JSON.stringify({ theme })); } catch {}
}, dark ? "dark" : "light");
if (!live) {
  await page.route("**/api/state", (r) => r.fulfill({ json: mockState }));
}
await page.goto(base);
await page.waitForSelector(".row", { timeout: 5000 }).catch(() => {});
if (!live) {
  await page.click('.row[data-id="ubuntu-24.04-desktop.iso"]');
}
await page.waitForTimeout(900);
await page.screenshot({ path: out });
await browser.close();
if (errors.length) { console.error("page errors:\n" + errors.join("\n")); process.exit(1); }
console.log("saved", out);
