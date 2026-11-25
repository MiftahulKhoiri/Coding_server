// Terminal xterm.js untuk WebView Android. Kotlin memanggil CS_TERM.connect(wsUrl).
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";

const bridge = window.AndroidBridge || { onStatus(s) { console.log("status", s); }, onReady() {} };
const term = new Terminal({
  cursorBlink: true, fontSize: 13, scrollback: 5000, convertEol: false,
  fontFamily: "'JetBrains Mono','Fira Code',monospace",
  theme: { background: "#1e1e1e", foreground: "#d4d4d4" },
});
const fit = new FitAddon();
term.loadAddon(fit);
const host = document.getElementById("terminal");
term.open(host);

let ws = null;
let pingTimer = null;
let lastSize = "";

function send(obj) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)); }

// Sesuaikan kolom/baris dengan ukuran layar. WebView bisa belum punya ukuran saat halaman dimuat
// (dibuat sebelum ditempel ke layar): ukuran yang terlalu kecil diabaikan, dicoba lagi saat ukuran berubah.
function resize() {
  const dims = (() => { try { return fit.proposeDimensions(); } catch (e) { return null; } })();
  if (!dims || !dims.cols || !dims.rows || dims.cols < 10 || dims.rows < 3) return;
  if (dims.cols !== term.cols || dims.rows !== term.rows) term.resize(dims.cols, dims.rows);
  const key = term.cols + "x" + term.rows;
  if (key !== lastSize) { lastSize = key; send({ type: "resize", cols: term.cols, rows: term.rows }); }
}
let resizeTimer = null;
function resizeSoon() { clearTimeout(resizeTimer); resizeTimer = setTimeout(resize, 60); }
window.addEventListener("resize", resizeSoon);
if (window.ResizeObserver) new ResizeObserver(resizeSoon).observe(host);
resize();

// Ketukan (bukan geser untuk scroll) di mana pun pada area terminal -> fokus & keyboard muncul (lewat Kotlin).
let touchStart = null;
document.addEventListener("touchstart", (e) => {
  const t = e.touches[0]; touchStart = t ? { x: t.clientX, y: t.clientY, at: Date.now() } : null;
}, { passive: true });
document.addEventListener("touchend", (e) => {
  const t = e.changedTouches[0];
  if (!touchStart || !t) return;
  const moved = Math.abs(t.clientX - touchStart.x) + Math.abs(t.clientY - touchStart.y);
  if (moved < 12 && Date.now() - touchStart.at < 600) { term.focus(); bridge.onTap && bridge.onTap(); }
  touchStart = null;
}, { passive: true });

term.onData((d) => send({ type: "input", data: d }));

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
      HOME: "\x1b[H", END: "\x1b[F", CTRL_C: "\x03", CTRL_D: "\x04", CTRL_Z: "\x1a", CTRL_L: "\x0c" };
    if (map[k]) send({ type: "input", data: map[k] });
  },
  signal(s) { send({ type: "signal", signal: s }); },
  setFontSize(px) { term.options.fontSize = Number(px) || 13; resize(); },
  clear() { term.clear(); },
  focus() { term.focus(); },
  fit() { lastSize = ""; resize(); },
};
bridge.onReady();
