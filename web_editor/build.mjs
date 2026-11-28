// Bundel editor & terminal menjadi satu file HTML mandiri (tanpa CDN) untuk aset Android.
import * as esbuild from "esbuild";
import fs from "node:fs";
import path from "node:path";

const out = path.resolve("dist");
const androidAssets = path.resolve("../android/app/src/main/assets/web");
fs.mkdirSync(out, { recursive: true });

async function bundle(entry) {
  const r = await esbuild.build({ entryPoints: [entry], bundle: true, minify: true, format: "iife", write: false,
    target: ["chrome80"], legalComments: "none", loader: { ".css": "css" } });
  // JS disisipkan di <script> inline: teks "</script" di dalam string akan menutup tag lebih awal.
  return r.outputFiles[0].text.replace(/<\/(script)/gi, "<\\/$1");
}

const editorJs = await bundle("editor/main.js");
const termJs = await bundle("editor/terminal.js");
const xtermCss = fs.readFileSync("node_modules/@xterm/xterm/css/xterm.css", "utf8");
const tpl = (name) => fs.readFileSync(path.join("src", name), "utf8");
const editorHtml = tpl("editor.html").replace("/*__JS__*/", () => editorJs);
const termHtml = tpl("terminal.html").replace("/*__CSS__*/", () => xtermCss).replace("/*__JS__*/", () => termJs);

for (const dir of [out, androidAssets]) {
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, "editor.html"), editorHtml);
  fs.writeFileSync(path.join(dir, "terminal.html"), termHtml);
}
console.log(`editor.html ${(editorHtml.length / 1024).toFixed(0)} KB, terminal.html ${(termHtml.length / 1024).toFixed(0)} KB`);
