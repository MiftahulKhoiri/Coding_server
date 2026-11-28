// Uji editor (CodeMirror + API window.CS) di Chromium headless: `node test/run.mjs` (setelah `npm run build`).
// Setiap kasus di cases.js dijalankan di halaman dist/editor.html; hasil dibaca dari DOM (--dump-dom).
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const html = fs.readFileSync(path.join(root, "dist/editor.html"), "utf8");
const cases = fs.readFileSync(path.join(root, "test/cases.js"), "utf8");
const harness = `<script>
window.__results = [];
window.addEventListener("load", async () => {
  ${cases}
  for (const [name, fn] of Object.entries(CASES)) {
    try { const r = await fn(); window.__results.push({ name, ok: r === true, detail: r === true ? "" : String(r) }); }
    catch (e) { window.__results.push({ name, ok: false, detail: String(e && e.stack || e) }); }
  }
  const pre = document.createElement("pre"); pre.id = "__out";
  pre.textContent = "@@RES" + "ULT@@" + JSON.stringify(window.__results) + "@@E" + "ND@@";
  document.body.appendChild(pre);
});
</script>`;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "cs-editor-test-"));
const page = path.join(root, "dist", "__test.html");  // di dist/ agar fonts/ (relatif) ikut termuat
const at = html.lastIndexOf("</body>");
fs.writeFileSync(page, html.slice(0, at) + harness + html.slice(at));
const chrome = process.env.CHROME || ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]
  .find((p) => fs.existsSync(p));
if (!chrome) { console.log("SKIP: Chromium tidak ditemukan"); process.exit(0); }
const dom = execFileSync(chrome, ["--headless=new", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=15000",
  "--user-data-dir=" + path.join(tmp, "profile"), "--dump-dom", "file://" + page], { encoding: "utf8", maxBuffer: 64 << 20 });
fs.rmSync(tmp, { recursive: true, force: true });
fs.rmSync(page, { force: true });
const m = dom.match(/@@RESULT@@(.*?)@@END@@/s);
if (!m) { console.error("Tidak ada hasil dari halaman uji"); process.exit(2); }
const results = JSON.parse(m[1].replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&"));
let failed = 0;
for (const r of results) {
  console.log(`${r.ok ? "OK  " : "GAGAL"} ${r.name}${r.ok ? "" : "  → " + r.detail}`);
  if (!r.ok) failed++;
}
console.log(`${results.length - failed}/${results.length} lulus`);
process.exit(failed ? 1 : 0);
