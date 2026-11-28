// Klien LSP ringan untuk CodeMirror 6 di WebView. Server: /ws/lsp di CODING_SERVER (clangd, pyright),
// satu WebSocket per jenis server per proyek. URI file memakai akar virtual file:///workspace/.
import { setDiagnostics } from "@codemirror/lint";

const SERVER_OF = {
  c: "clangd", cpp: "clangd", python: "pyright", javascript: "tsserver", typescript: "tsserver", go: "gopls",
  php: "intelephense", html: "html", css: "css", json: "json", shell: "bash",
};
const WS_LANG = {
  clangd: "cpp", pyright: "python", tsserver: "typescript", gopls: "go", intelephense: "php", html: "html", css: "css",
  json: "json", bash: "shell",
};
const LANGUAGE_ID = { shell: "shellscript" };  // languageId LSP yang berbeda dari nama bahasa editor
const ROOT = "file:///workspace/";
const KIND = {
  1: "text", 2: "method", 3: "function", 4: "function", 5: "property", 6: "variable", 7: "class", 8: "interface",
  9: "namespace", 10: "property", 11: "constant", 12: "enum", 13: "keyword", 14: "keyword", 15: "text",
  17: "text", 19: "namespace", 20: "enum", 21: "constant", 22: "class", 23: "type", 25: "type",
};
const SYMBOL_KIND = { 2: "modul", 3: "namespace", 4: "paket", 5: "kelas", 6: "metode", 7: "properti", 8: "field",
  9: "konstruktor", 10: "enum", 11: "interface", 12: "fungsi", 13: "variabel", 14: "konstanta", 22: "anggota enum",
  23: "struct", 26: "tipe" };
const SEVERITY = { 1: "error", 2: "warning", 3: "info", 4: "hint" };

export function uriOfPath(path) {
  return ROOT + path.split("/").map(encodeURIComponent).join("/");
}
export function pathOfUri(uri) {
  if (!uri || !uri.startsWith(ROOT)) return null;
  return uri.slice(ROOT.length).split("/").map(decodeURIComponent).join("/");
}

// posisi CodeMirror <-> LSP (baris 0-based, karakter UTF-16 = indeks string JS)
export function toLsp(doc, pos) {
  const line = doc.lineAt(pos);
  return { line: line.number - 1, character: pos - line.from };
}
export function fromLsp(doc, p) {
  const n = Math.min(Math.max(p.line + 1, 1), doc.lines);
  const line = doc.line(n);
  return Math.min(line.from + Math.max(0, p.character), line.to);
}

class Connection {
  constructor(mgr, server, cfg) {
    this.mgr = mgr;
    this.server = server;
    this.projectId = cfg.projectId;
    this.nextId = 1;
    this.pending = new Map();
    this.ready = false;
    this.closed = false;
    this.queue = [];
    this.capabilities = {};
    const url = `${cfg.wsBase}ws/lsp?project_id=${encodeURIComponent(cfg.projectId)}&language=${WS_LANG[server]}` +
      `&token=${encodeURIComponent(cfg.token || "")}`;
    this.ws = new WebSocket(url);
    this.ws.onmessage = (e) => this.onMessage(e.data);
    this.ws.onclose = () => this.onClose();
    this.ws.onerror = () => {};
  }

  rawSend(msg) {
    if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }
  notify(method, params) {
    const m = { jsonrpc: "2.0", method, params };
    if (this.ready || method === "initialized") this.rawSend(m); else this.queue.push(m);
  }
  request(method, params, timeoutMs = 5000) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error("timeout")); }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      const m = { jsonrpc: "2.0", id, method, params };
      if (this.ready || method === "initialize") this.rawSend(m); else this.queue.push(m);
    });
  }

  async onMessage(text) {
    let msg;
    try { msg = JSON.parse(text); } catch { return; }
    if (msg.method === "cs/ready") { this.initialize(); return; }
    if (msg.method === "cs/error" || msg.method === "cs/exit") {
      this.mgr.status(`${this.server}: ${(msg.params && msg.params.message) || "tidak tersedia"}`);
      this.failed = msg.method === "cs/error" && msg.params && msg.params.code === "lsp_unavailable";
      return;
    }
    if (msg.id !== undefined && !msg.method) {
      const p = this.pending.get(msg.id);
      if (p) {
        clearTimeout(p.timer);
        this.pending.delete(msg.id);
        if (msg.error) p.reject(new Error(msg.error.message || "error")); else p.resolve(msg.result);
      }
      return;
    }
    if (msg.id !== undefined && msg.method) {  // request server->klien yang tidak ditangani proxy
      this.rawSend({ jsonrpc: "2.0", id: msg.id, result: null });
      return;
    }
    if (msg.method === "textDocument/publishDiagnostics") this.mgr.onDiagnostics(msg.params);
  }

  async initialize() {
    try {
      const res = await this.request("initialize", {
        capabilities: {
          textDocument: {
            synchronization: { didSave: false, dynamicRegistration: false },
            publishDiagnostics: { relatedInformation: false },
            completion: { completionItem: { snippetSupport: false, documentationFormat: ["plaintext"] }, contextSupport: true },
            hover: { contentFormat: ["plaintext", "markdown"] },
            definition: { linkSupport: false },
            signatureHelp: { signatureInformation: { documentationFormat: ["plaintext"], parameterInformation: { labelOffsetSupport: true } } },
            references: {},
            rename: { prepareSupport: false },
          },
          workspace: { configuration: true, workspaceFolders: true },
          general: { positionEncodings: ["utf-16"] },
        },
        clientInfo: { name: "CODING_SERVER editor" },
      }, 30000);
      this.capabilities = (res && res.capabilities) || {};
      this.rawSend({ jsonrpc: "2.0", method: "initialized", params: {} });
      this.ready = true;
      const q = this.queue; this.queue = [];
      q.forEach((m) => this.rawSend(m));
      this.mgr.status(`${this.server} aktif`);
      this.mgr.reopenAll(this);
    } catch (e) {
      this.mgr.status(`${this.server}: gagal inisialisasi (${e.message})`);
    }
  }

  onClose() {
    this.closed = true;
    this.ready = false;
    for (const p of this.pending.values()) { clearTimeout(p.timer); p.reject(new Error("closed")); }
    this.pending.clear();
    this.mgr.onConnectionClosed(this);
  }

  close() { this.closed = true; try { this.ws.close(); } catch { /* sudah tertutup */ } }
}

export class LspManager {
  // host: { getConfig(): {wsBase, token, projectId, enabled}, getTab(id), getState(id), applyDiagnostics(id, diags),
  //         onStatus(text) }
  constructor(host) {
    this.host = host;
    this.conns = new Map();     // server -> Connection
    this.docs = new Map();      // tabId -> {uri, lang, server, version, timer}
    this.retries = new Map();   // server -> jumlah percobaan ulang
    this.ghosts = new Map();    // uri -> server: file proyek yang dibuka di LSP tanpa tab (untuk referensi/rename C/C++)
    this.diagWaiters = new Map(); // uri -> [resolve]
  }

  /** Tutup semua file tanpa tab (isinya bisa basi setelah rename menulis file di server). */
  dropGhosts(tabId) {
    const d = this.docs.get(tabId);
    const c = d && this.conns.get(d.server);
    for (const [uri, sv] of this.ghosts) {
      if (d && sv !== d.server) continue;
      this.ghosts.delete(uri);
      if (c && c.ready) c.notify("textDocument/didClose", { textDocument: { uri } });
    }
  }

  /** Buka file proyek lain di language server (tanpa tab) lalu tunggu selesai dianalisis (diagnostik pertama). */
  async preload(tabId, files, timeoutMs = 12000) {
    const d = this.docs.get(tabId);
    const c = d && this.conns.get(d.server);
    if (!c || !c.ready || !files || !files.length) return 0;
    const open = new Set([...this.docs.values()].map((x) => x.uri));
    const waits = [];
    for (const f of files) {
      const uri = uriOfPath(f.path);
      if (open.has(uri) || this.ghosts.has(uri)) continue;
      this.ghosts.set(uri, d.server);
      waits.push(new Promise((res) => { const l = this.diagWaiters.get(uri) || []; l.push(res); this.diagWaiters.set(uri, l); }));
      c.notify("textDocument/didOpen", { textDocument: { uri, languageId: f.lang || d.lang, version: 1, text: f.text } });
    }
    if (waits.length) await Promise.race([Promise.all(waits), new Promise((r) => setTimeout(r, timeoutMs))]);
    return waits.length;
  }

  status(text) { try { this.host.onStatus(text); } catch { /* opsional */ } }

  docFor(tabId) { return this.docs.get(tabId); }

  supports(tabId) {
    const d = this.docs.get(tabId);
    if (!d) return false;
    const c = this.conns.get(d.server);
    return !!(c && c.ready);
  }

  connection(server) {
    const cfg = this.host.getConfig();
    if (!cfg || !cfg.enabled || !cfg.wsBase || !cfg.projectId) return null;
    let c = this.conns.get(server);
    if (c && c.projectId !== cfg.projectId) { c.close(); c = null; }
    if (!c || (c.closed && !c.failed)) {
      c = new Connection(this, server, cfg);
      this.conns.set(server, c);
    }
    return c.failed ? null : c;
  }

  open(tabId, lang, text) {
    const server = SERVER_OF[lang];
    const cfg = this.host.getConfig();
    if (!server || !cfg || !cfg.enabled || !cfg.projectId || !tabId.startsWith(cfg.projectId + ":")) return;
    const path = tabId.slice(cfg.projectId.length + 1);
    const doc = { uri: uriOfPath(path), lang, server, version: 1, timer: null };
    this.docs.set(tabId, doc);
    const c = this.connection(server);
    if (this.ghosts.has(doc.uri)) {  // dulu dibuka tanpa tab: tutup dulu agar isinya diganti versi tab
      this.ghosts.delete(doc.uri);
      if (c && c.ready) c.notify("textDocument/didClose", { textDocument: { uri: doc.uri } });
    }
    if (c && c.ready) this.sendOpen(c, doc, text);
  }

  sendOpen(c, doc, text) {
    c.notify("textDocument/didOpen", { textDocument: { uri: doc.uri, languageId: LANGUAGE_ID[doc.lang] || doc.lang, version: doc.version, text } });
  }

  reopenAll(c) {
    for (const [id, d] of this.docs) {
      if (d.server !== c.server) continue;
      const st = this.host.getState(id);
      if (st) this.sendOpen(c, d, st.doc.toString());
    }
  }

  change(tabId) {
    const d = this.docs.get(tabId);
    if (!d) return;
    clearTimeout(d.timer);
    d.timer = setTimeout(() => this.flush(tabId), 350);
  }

  flush(tabId) {
    const d = this.docs.get(tabId);
    if (!d) return;
    clearTimeout(d.timer);
    d.timer = null;
    const c = this.conns.get(d.server);
    const st = this.host.getState(tabId);
    if (!c || !c.ready || !st) return;
    d.version += 1;
    c.notify("textDocument/didChange", { textDocument: { uri: d.uri, version: d.version }, contentChanges: [{ text: st.doc.toString() }] });
  }

  close(tabId) {
    const d = this.docs.get(tabId);
    if (!d) return;
    clearTimeout(d.timer);
    this.docs.delete(tabId);
    const c = this.conns.get(d.server);
    if (c && c.ready) c.notify("textDocument/didClose", { textDocument: { uri: d.uri } });
    if (![...this.docs.values()].some((x) => x.server === d.server) && c) {  // tidak ada file lagi: hemat RAM Pi
      this.conns.delete(d.server);
      for (const [u, sv] of this.ghosts) if (sv === d.server) this.ghosts.delete(u);
      c.close();
    }
  }

  reset() {  // proyek/token berganti
    for (const c of this.conns.values()) c.close();
    this.conns.clear();
    this.ghosts.clear();
    const tabs = [...this.docs.entries()];
    this.docs.clear();
    for (const [id, d] of tabs) {
      const st = this.host.getState(id);
      if (st) this.open(id, d.lang, st.doc.toString());
    }
  }

  onConnectionClosed(c) {
    if (this.conns.get(c.server) !== c) return;
    this.conns.delete(c.server);
    for (const [u, sv] of this.ghosts) if (sv === c.server) this.ghosts.delete(u);
    if (c.failed || ![...this.docs.values()].some((d) => d.server === c.server)) return;
    const n = (this.retries.get(c.server) || 0) + 1;
    this.retries.set(c.server, n);
    if (n > 5) { this.status(`${c.server}: terputus`); return; }
    setTimeout(() => {
      const nc = this.connection(c.server);
      if (nc) this.retries.set(c.server, nc.ready ? 0 : n);
    }, Math.min(30000, 1500 * n));
  }

  onDiagnostics(params) {
    const w = this.diagWaiters.get(params.uri);
    if (w) { this.diagWaiters.delete(params.uri); w.forEach((res) => res()); }
    for (const [id, d] of this.docs) {
      if (d.uri !== params.uri) continue;
      const st = this.host.getState(id);
      if (!st) continue;
      const doc = st.doc;
      const diags = (params.diagnostics || []).map((x) => {
        const from = fromLsp(doc, x.range.start);
        const to = Math.max(from, fromLsp(doc, x.range.end));
        const src = x.source ? `[${x.source}] ` : "";
        return { from, to: to === from ? Math.min(from + 1, doc.length) : to,
                 severity: SEVERITY[x.severity] === "hint" ? "info" : (SEVERITY[x.severity] || "error"),
                 message: src + x.message };
      });
      this.host.applyDiagnostics(id, diags);
    }
  }

  // ---------- fitur ----------
  async completion(tabId, state, pos, explicit) {
    const d = this.docs.get(tabId);
    const c = d && this.conns.get(d.server);
    if (!c || !c.ready) return null;
    if (d.timer) this.flush(tabId);
    const before = state.sliceDoc(Math.max(0, pos - 2), pos);
    const word = /[\w$]*$/.exec(state.sliceDoc(Math.max(0, pos - 60), pos))[0];
    const trigger = before.endsWith(".") || before.endsWith("->") || before.endsWith("::");
    if (!explicit && !word && !trigger) return null;
    let res;
    try {
      res = await c.request("textDocument/completion", {
        textDocument: { uri: d.uri }, position: toLsp(state.doc, pos),
        context: trigger && !word ? { triggerKind: 2, triggerCharacter: before.slice(-1) } : { triggerKind: 1 },
      }, 4000);
    } catch { return null; }
    const items = Array.isArray(res) ? res : (res && res.items) || [];
    const options = items.slice(0, 150).map((it, i) => {
      const insert = (it.textEdit && it.textEdit.newText) || it.insertText || it.label;
      return {
        label: (it.label || "").trim(),
        apply: insert.replace(/\$\{\d+:([^}]*)\}/g, "$1").replace(/\$\d+/g, ""),
        type: KIND[it.kind] || "text",
        detail: it.detail ? String(it.detail).slice(0, 60) : undefined,
        info: it.documentation ? (typeof it.documentation === "string" ? it.documentation : it.documentation.value) : undefined,
        // pertahankan urutan relevansi dari server (CodeMirror mengurutkan ulang per skor kecocokan)
        boost: it.preselect ? 99 : Math.max(-99, 40 - Math.floor(i / 3)),
      };
    });
    return { from: pos - word.length, options, validFor: /^[\w$]*$/ };
  }

  async hover(tabId, state, pos) {
    const d = this.docs.get(tabId);
    const c = d && this.conns.get(d.server);
    if (!c || !c.ready) return null;
    if (d.timer) this.flush(tabId);
    try {
      const r = await c.request("textDocument/hover", { textDocument: { uri: d.uri }, position: toLsp(state.doc, pos) }, 5000);
      if (!r || !r.contents) return null;
      const parts = Array.isArray(r.contents) ? r.contents : [r.contents];
      return parts.map((p) => (typeof p === "string" ? p : p.value || "")).join("\n\n")
        .replace(/```\w*\n?/g, "").replace(/\n{3,}/g, "\n\n").trim();
    } catch { return null; }
  }

  async definition(tabId, state, pos) {
    const d = this.docs.get(tabId);
    const c = d && this.conns.get(d.server);
    if (!c || !c.ready) return null;
    if (d.timer) this.flush(tabId);
    try {
      const r = await c.request("textDocument/definition", { textDocument: { uri: d.uri }, position: toLsp(state.doc, pos) }, 6000);
      const list = Array.isArray(r) ? r : r ? [r] : [];
      if (!list.length) return null;
      const loc = list[0];
      const uri = loc.uri || loc.targetUri;
      const range = loc.range || loc.targetSelectionRange || loc.targetRange;
      return { uri, path: pathOfUri(uri), line: range.start.line + 1, column: range.start.character + 1, sameFile: uri === d.uri };
    } catch { return null; }
  }

  conn(tabId) {
    const d = this.docs.get(tabId);
    const c = d && this.conns.get(d.server);
    if (!c || !c.ready) return null;
    if (d.timer) this.flush(tabId);
    return { d, c };
  }

  /** Semua pemakaian simbol di kursor: [{path, uri, line, column}] (path null = di luar proyek). */
  async references(tabId, state, pos) {
    const x = this.conn(tabId);
    if (!x) return null;
    try {
      const r = await x.c.request("textDocument/references", {
        textDocument: { uri: x.d.uri }, position: toLsp(state.doc, pos), context: { includeDeclaration: true },
      }, 10000);
      return (r || []).map((l) => ({ uri: l.uri, path: pathOfUri(l.uri), line: l.range.start.line + 1,
                                      column: l.range.start.character + 1 }));
    } catch (e) { return { error: e.message }; }
  }

  /** Ganti nama simbol: {path: [{startLine, startChar, endLine, endChar, newText}]} (0-based, UTF-16). */
  async rename(tabId, state, pos, newName) {
    const x = this.conn(tabId);
    if (!x) return null;
    let r;
    try {
      r = await x.c.request("textDocument/rename", {
        textDocument: { uri: x.d.uri }, position: toLsp(state.doc, pos), newName,
      }, 15000);
    } catch (e) { return { error: e.message }; }
    if (!r) return { error: "Simbol di kursor tidak bisa diganti nama" };
    const out = {};
    const add = (uri, edits) => {
      const path = pathOfUri(uri);
      if (!path) return;  // file di luar proyek (header sistem) tidak pernah diubah
      out[path] = (out[path] || []).concat(edits.map((e) => ({
        startLine: e.range.start.line, startChar: e.range.start.character,
        endLine: e.range.end.line, endChar: e.range.end.character, newText: e.newText })));
    };
    if (r.changes) for (const [uri, edits] of Object.entries(r.changes)) add(uri, edits);
    if (r.documentChanges) for (const dc of r.documentChanges) if (dc.textDocument && dc.edits) add(dc.textDocument.uri, dc.edits);
    return { edits: out };
  }

  /** Simbol dokumen (outline): [{name, kind, detail, depth, line, endLine}] — line 1-based. */
  async documentSymbols(tabId) {
    const x = this.conn(tabId);
    if (!x) return null;
    let r;
    try {
      r = await x.c.request("textDocument/documentSymbol", { textDocument: { uri: x.d.uri } }, 8000);
    } catch { return null; }
    const out = [];
    const walk = (list, depth) => {
      for (const s of list || []) {
        if (s.location) {  // SymbolInformation (datar)
          out.push({ name: s.name, kind: SYMBOL_KIND[s.kind] || "", detail: s.containerName || "", depth: s.containerName ? 1 : 0,
                     line: s.location.range.start.line + 1, endLine: s.location.range.end.line + 1 });
        } else {
          out.push({ name: s.name, kind: SYMBOL_KIND[s.kind] || "", detail: s.detail || "", depth,
                     line: (s.selectionRange || s.range).start.line + 1, startLine: s.range.start.line + 1,
                     endLine: s.range.end.line + 1 });
          walk(s.children, depth + 1);
        }
      }
    };
    walk(r, 0);
    return out;
  }

  /** Petunjuk parameter: {label, active: [from, to] | null} atau null. */
  async signatureHelp(tabId, state, pos) {
    const x = this.conn(tabId);
    if (!x) return null;
    try {
      const r = await x.c.request("textDocument/signatureHelp", { textDocument: { uri: x.d.uri }, position: toLsp(state.doc, pos) }, 4000);
      if (!r || !r.signatures || !r.signatures.length) return null;
      const sig = r.signatures[r.activeSignature || 0] || r.signatures[0];
      const ap = sig.activeParameter ?? r.activeParameter ?? 0;
      const param = sig.parameters && sig.parameters[ap];
      let active = null;
      if (param) {
        if (Array.isArray(param.label)) active = param.label;
        else { const i = sig.label.indexOf(param.label); if (i >= 0) active = [i, i + param.label.length]; }
      }
      return { label: sig.label, active, more: r.signatures.length > 1 ? r.signatures.length : 0 };
    } catch { return null; }
  }
}

export function applyDiagnosticsTo(state, diags) {
  return state.update(setDiagnostics(state, diags)).state;
}
