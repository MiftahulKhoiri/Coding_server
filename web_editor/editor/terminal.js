// Terminal xterm.js untuk WebView Android. Kotlin memanggil CS_TERM.connect(wsUrl) dan CS_TERM.setOptions({...}).
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { fontCss, whenFontReady } from "./fonts.js";

const bridge = window.AndroidBridge || { onStatus(s) { console.log("status", s); }, onReady() {} };

// Tema warna terminal (dipilih di Pengaturan tampilan terminal).
const THEMES = {
  dark: { background: "#1e1e1e", foreground: "#d4d4d4", cursor: "#ffffff", selectionBackground: "#264f78" },
  light: { background: "#fafafa", foreground: "#1f1f1f", cursor: "#333333", selectionBackground: "#add6ff",
           blue: "#0451a5", brightBlue: "#0451a5", green: "#116329", brightGreen: "#116329", yellow: "#795e26" },
  solarized: { background: "#002b36", foreground: "#93a1a1", cursor: "#93a1a1", selectionBackground: "#073642" },
  monokai: { background: "#272822", foreground: "#f8f8f2", cursor: "#f8f8f0", selectionBackground: "#49483e" },
  retro: { background: "#0a0f0a", foreground: "#33ff66", cursor: "#33ff66", selectionBackground: "#1f5f2f",
           blue: "#33ff66", brightBlue: "#66ff99" },
};

const term = new Terminal({
  cursorBlink: true, fontSize: 13, scrollback: 5000, convertEol: false, lineHeight: 1.0,
  fontFamily: fontCss("jetbrains"),
  theme: THEMES.dark,
});
const fit = new FitAddon();
term.loadAddon(fit);
const host = document.getElementById("terminal");
term.open(host);

let ws = null;
let pingTimer = null;
let lastSize = "";

function send(obj) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)); }

// Halaman tidak boleh bergeser: bila terminal sedikit lebih lebar dari layar, WebView menggulir ke kanan
// mengikuti kursor dan sisi kiri baris "terpotong".
function lockScroll() {
  if (window.scrollX || window.scrollY) window.scrollTo(0, 0);
  const se = document.scrollingElement;
  if (se && (se.scrollLeft || se.scrollTop)) { se.scrollLeft = 0; se.scrollTop = 0; }
  if (host.scrollLeft) host.scrollLeft = 0;
}
window.addEventListener("scroll", lockScroll, { passive: true });
host.addEventListener("scroll", lockScroll, { passive: true });

function screenWidth() {
  const s = term.element && term.element.querySelector(".xterm-screen");
  return s ? s.getBoundingClientRect().width : 0;
}

// Sesuaikan kolom/baris dengan ukuran layar. WebView bisa belum punya ukuran saat halaman dimuat
// (dibuat sebelum ditempel ke layar): ukuran yang terlalu kecil diabaikan, dicoba lagi saat ukuran berubah.
function resize() {
  const dims = (() => { try { return fit.proposeDimensions(); } catch (e) { return null; } })();
  if (!dims || !dims.cols || !dims.rows || dims.cols < 10 || dims.rows < 3) return;
  if (dims.cols !== term.cols || dims.rows !== term.rows) term.resize(dims.cols, dims.rows);
  // Pengaman: lebar huruf nyata di Android bisa sedikit lebih besar dari hasil ukur -> kurangi kolom
  // sampai seluruh layar terminal benar-benar muat.
  const avail = host.clientWidth;
  let guard = 0;
  while (avail > 0 && screenWidth() > avail + 0.5 && term.cols > 10 && guard++ < 20) term.resize(term.cols - 1, term.rows);
  lockScroll();
  const key = term.cols + "x" + term.rows;
  if (key !== lastSize) { lastSize = key; send({ type: "resize", cols: term.cols, rows: term.rows }); }
}
let resizeTimer = null;
function resizeSoon() { clearTimeout(resizeTimer); resizeTimer = setTimeout(resize, 60); }
window.addEventListener("resize", resizeSoon);
if (window.ResizeObserver) new ResizeObserver(resizeSoon).observe(host);
resize();
whenFontReady("jetbrains", () => { lastSize = ""; resizeSoon(); });

// ---- sentuhan: ketuk = fokus & keyboard; geser 1 jari = gulir (dengan momentum); cubit = ukuran huruf ----
// xterm.js hampir tidak punya gulir sentuh di Android (langkah kecil, tanpa momentum) -> ditangani sendiri.
// Layar alternatif (less, vim, top, man): geser = tombol ↑/↓ seperti Termux.
let touchStart = null;
let pinch = null;
let drag = null;      // {y, acc, lastY, lastT, v}
let fling = null;
const dist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
function cellHeight() {
  const rows = term.element && term.element.querySelector(".xterm-rows");
  const h = rows && rows.firstElementChild ? rows.firstElementChild.getBoundingClientRect().height : 0;
  return h > 4 ? h : Math.max(8, (host.clientHeight || 400) / Math.max(1, term.rows));
}
function scrollBy(lines) {
  if (!lines) return;
  if (term.buffer.active.type === "alternate") {
    const key = lines > 0 ? "\x1b[B" : "\x1b[A";
    for (let i = 0; i < Math.min(Math.abs(lines), 20); i++) send({ type: "input", data: key });
  } else term.scrollLines(lines);
}
function stopFling() { if (fling) { cancelAnimationFrame(fling); fling = null; } }
host.addEventListener("touchstart", (e) => {
  stopFling();
  if (e.touches.length === 2) {
    pinch = { d: dist(e.touches), size: term.options.fontSize };
    touchStart = null; drag = null;
    return;
  }
  const t = e.touches[0];
  touchStart = t && !pinch ? { x: t.clientX, y: t.clientY, at: Date.now() } : null;
  drag = t && !pinch ? { y: t.clientY, acc: 0, lastY: t.clientY, lastT: performance.now(), v: 0, active: false } : null;
}, { passive: true, capture: true });
host.addEventListener("touchmove", (e) => {
  if (pinch && e.touches.length === 2) {
    const size = Math.max(8, Math.min(28, Math.round(pinch.size * dist(e.touches) / pinch.d)));
    if (size !== term.options.fontSize) { term.options.fontSize = size; resizeSoon(); }
    e.preventDefault();
    return;
  }
  const t = e.touches[0];
  if (!drag || !t) return;
  if (!drag.active) {
    const dx = Math.abs(t.clientX - touchStart.x), dy = Math.abs(t.clientY - touchStart.y);
    if (dy < 8 || dy < dx) return;   // belum/bukan geser vertikal
    drag.active = true;
  }
  e.preventDefault();
  e.stopPropagation();              // jangan sampai ke penangan sentuh bawaan xterm
  const now = performance.now();
  const dy = drag.lastY - t.clientY;   // geser ke atas = lihat baris berikutnya
  drag.v = 0.8 * (dy / Math.max(1, now - drag.lastT)) + 0.2 * drag.v;  // px/ms, dihaluskan
  drag.lastY = t.clientY; drag.lastT = now;
  drag.acc += dy;
  const ch = cellHeight();
  const lines = Math.trunc(drag.acc / ch);
  if (lines) { scrollBy(lines); drag.acc -= lines * ch; }
}, { passive: false, capture: true });
host.addEventListener("touchend", (e) => {
  if (pinch) {
    if (e.touches.length === 0) {
      bridge.onFontSize && bridge.onFontSize(term.options.fontSize);
      pinch = null;
    }
    return;
  }
  const t = e.changedTouches[0];
  if (drag && drag.active) {
    // momentum: lanjutkan gulir dengan kecepatan yang melambat
    let v = drag.v, acc = drag.acc, last = performance.now();
    const ch = cellHeight();
    const step = (now) => {
      const dt = now - last; last = now;
      acc += v * dt;
      v *= Math.pow(0.995, dt);
      const lines = Math.trunc(acc / ch);
      if (lines) { scrollBy(lines); acc -= lines * ch; }
      fling = Math.abs(v) > 0.02 ? requestAnimationFrame(step) : null;
    };
    if (Math.abs(v) > 0.15) fling = requestAnimationFrame(step);
    drag = null; touchStart = null;
    return;
  }
  drag = null;
  if (!touchStart || !t) return;
  const moved = Math.abs(t.clientX - touchStart.x) + Math.abs(t.clientY - touchStart.y);
  if (moved < 12 && Date.now() - touchStart.at < 600) { term.focus(); bridge.onTap && bridge.onTap(); }
  touchStart = null;
}, { passive: true, capture: true });

term.onData((d) => send({ type: "input", data: d }));

function applyTheme(name) {
  const th = THEMES[name] || THEMES.dark;
  term.options.theme = th;
  document.documentElement.style.background = th.background;
  document.body.style.background = th.background;
}

window.CS_TERM = {
  connect(url) {
    if (ws) try { ws.close(); } catch (e) {}
    bridge.onStatus("connecting");
    ws = new WebSocket(url);
    ws.onopen = () => { bridge.onStatus("connected"); lastSize = ""; resize(); term.focus();
      clearInterval(pingTimer); pingTimer = setInterval(() => send({ type: "ping" }), 25000); };
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === "output") term.write(m.data);
      else if (m.type === "exit") { term.write(`\r\n\x1b[33m[sesi selesai, exit ${m.exit_code ?? "-"}]\x1b[0m\r\n`); bridge.onStatus("exited"); }
      else if (m.type === "error") { term.write(`\r\n\x1b[31m${m.message}\x1b[0m\r\n`); bridge.onStatus("error"); }
    };
    ws.onclose = () => { clearInterval(pingTimer); bridge.onStatus("disconnected"); };
    ws.onerror = () => bridge.onStatus("error");
  },
  disconnect() { if (ws) ws.close(); },
  sendText(t) { send({ type: "input", data: t }); },
  sendKey(k) {
    const map = { ESC: "\x1b", TAB: "\t", UP: "\x1b[A", DOWN: "\x1b[B", RIGHT: "\x1b[C", LEFT: "\x1b[D",
      HOME: "\x1b[H", END: "\x1b[F", PGUP: "\x1b[5~", PGDN: "\x1b[6~", CTRL_C: "\x03", CTRL_D: "\x04",
      CTRL_Z: "\x1a", CTRL_L: "\x0c", CTRL_A: "\x01", CTRL_E: "\x05", CTRL_R: "\x12", CTRL_U: "\x15", CTRL_W: "\x17" };
    if (map[k]) send({ type: "input", data: map[k] });
  },
  signal(s) { send({ type: "signal", signal: s }); },
  /** Pengaturan tampilan: {fontSize, lineHeight, theme, cursorStyle, cursorBlink, scrollback, fontFamily}. */
  setOptions(o) {
    if (o.fontSize) term.options.fontSize = Math.max(8, Math.min(28, Number(o.fontSize)));
    if (o.lineHeight) term.options.lineHeight = Math.max(1, Math.min(2, Number(o.lineHeight)));
    if (o.cursorStyle) term.options.cursorStyle = o.cursorStyle;
    if (o.cursorBlink !== undefined) term.options.cursorBlink = !!o.cursorBlink;
    if (o.scrollback) term.options.scrollback = Number(o.scrollback);
    if (o.theme) applyTheme(o.theme);
    if (o.fontFamily) whenFontReady(o.fontFamily, (fam) => { term.options.fontFamily = fam; lastSize = ""; resizeSoon(); });
    lastSize = "";
    resizeSoon();
  },
  setFontSize(px) { this.setOptions({ fontSize: px }); },
  clear() { term.clear(); },
  focus() { term.focus(); },
  fit() { lastSize = ""; resize(); },
};
bridge.onReady();
