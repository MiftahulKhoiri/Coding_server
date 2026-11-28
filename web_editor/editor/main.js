// Editor CODING_SERVER untuk WebView Android. API global: window.CS (dipanggil dari Kotlin
// lewat evaluateJavascript). Callback ke Kotlin lewat objek AndroidBridge (addJavascriptInterface).
import { EditorState, Compartment, EditorSelection } from "@codemirror/state";
import {
  EditorView, keymap, lineNumbers, highlightActiveLineGutter, highlightSpecialChars, drawSelection,
  dropCursor, rectangularSelection, crosshairCursor, highlightActiveLine, placeholder,
} from "@codemirror/view";
import {
  defaultKeymap, history, historyKeymap, indentWithTab, undo, redo, undoDepth, redoDepth,
  cursorCharLeft, cursorCharRight, cursorLineUp, cursorLineDown, cursorLineBoundaryBackward, cursorLineBoundaryForward,
  indentMore, indentLess, insertTab, toggleComment, selectLine, copyLineDown, deleteLine,
} from "@codemirror/commands";
import {
  indentOnInput, syntaxHighlighting, defaultHighlightStyle, bracketMatching, foldGutter, foldKeymap,
  foldAll, unfoldAll, indentUnit,
} from "@codemirror/language";
import { searchKeymap, highlightSelectionMatches, openSearchPanel, closeSearchPanel, search } from "@codemirror/search";
import {
  autocompletion, completionKeymap, closeBrackets, closeBracketsKeymap, completeAnyWord, insertBracket, startCompletion,
} from "@codemirror/autocomplete";
import { lintKeymap, setDiagnostics, lintGutter, forEachDiagnostic } from "@codemirror/lint";
import { oneDark } from "@codemirror/theme-one-dark";
import { detectLanguage, languageExtension, SYMBOL_PATTERNS } from "./languages.js";
import { LspManager, applyDiagnosticsTo } from "./lsp.js";

// Android WebView: CodeMirror memakai API EditContext bila tersedia. Pada sebagian WebView/keyboard
// (Gboard, SwiftKey) input lewat EditContext tidak sampai ke editor sehingga "tidak bisa mengetik".
// Paksa jalur contenteditable biasa yang sudah teruji di semua WebView.
EditorView.EDIT_CONTEXT = false;

const bridge = window.AndroidBridge || {
  onReady() {}, onChange() {}, onSave() {}, onRun() {}, onCursor() {},
};
const callBridge = (name, ...args) => { try { return typeof bridge[name] === "function" ? bridge[name](...args) : undefined; } catch { return undefined; } };

const langConf = new Compartment();
const themeConf = new Compartment();
const wrapConf = new Compartment();
const fontConf = new Compartment();
const readOnlyConf = new Compartment();
const indentConf = new Compartment();

let settings = { theme: "dark", fontSize: 14, wordWrap: false, tabSize: 4, textColor: "", backgroundColor: "" };
const tabs = new Map(); // id -> { state, lang, filename, savedVersion }
let current = null;
let suppress = false;

// ---------- LSP (clangd / pyright di server) ----------
function stateOf(id) {
  if (id === current) return view.state;
  const t = tabs.get(id);
  return t ? t.state : null;
}
const lsp = new LspManager({
  getConfig() {
    const raw = callBridge("lspConfig");
    try { return raw ? JSON.parse(raw) : null; } catch { return null; }
  },
  getState: stateOf,
  applyDiagnostics(id, diags) {
    if (id === current) {
      suppress = true; view.dispatch(setDiagnostics(view.state, diags)); suppress = false; tabs.get(id).state = view.state;
      notifyProblems(); return;
    }
    const t = tabs.get(id);
    if (t) t.state = applyDiagnosticsTo(t.state, diags);
  },
  onStatus(text) { callBridge("onLspStatus", text); },
});

// Completion: LSP bila tersedia untuk tab aktif, selain itu kata-kata di dokumen.
async function lspCompletion(ctx) {
  if (!current || !lsp.supports(current)) return null;
  return lsp.completion(current, ctx.state, ctx.pos, ctx.explicit);
}
function wordCompletion(ctx) {
  return current && lsp.supports(current) ? null : completeAnyWord(ctx);
}

// Panel info sederhana (hover/definisi) di bawah editor — WebView sentuh tidak punya "hover".
function showInfo(text) {
  let el = document.getElementById("cs-info");
  if (!el) {
    el = document.createElement("div");
    el.id = "cs-info";
    el.style.cssText = "position:fixed;left:6px;right:6px;bottom:6px;max-height:38vh;overflow:auto;z-index:50;" +
      "padding:10px 12px;border-radius:10px;font:13px/1.45 'JetBrains Mono',monospace;white-space:pre-wrap;" +
      "box-shadow:0 4px 18px rgba(0,0,0,.45)";
    el.addEventListener("click", () => { el.style.display = "none"; });
    document.body.appendChild(el);
  }
  const dark = settings.theme === "dark";
  el.style.background = dark ? "#21252b" : "#f3f3f3";
  el.style.color = dark ? "#d7dae0" : "#202124";
  el.style.border = "1px solid " + (dark ? "#3e4451" : "#cccccc");
  el.textContent = text + "\n\n(ketuk untuk menutup)";
  el.style.display = "block";
}

function fontTheme(size) {
  return EditorView.theme({
    "&": { fontSize: size + "px", height: "100%" },
    ".cm-scroller": { fontFamily: "'JetBrains Mono','Fira Code',monospace", lineHeight: "1.5" },
    ".cm-content": { paddingBottom: "40vh" },
  });
}
const lightTheme = EditorView.theme({
  "&": { backgroundColor: "#ffffff", color: "#202124" },
  ".cm-scroller": { backgroundColor: "#ffffff" },
  ".cm-content": { color: "#202124", caretColor: "#000000" },
  ".cm-line": { color: "#202124" },
  ".cm-gutters": { backgroundColor: "#f5f5f5", color: "#666666", borderRight: "1px solid #dddddd" },
}, { dark: false });

function customColorsTheme() {
  const fg = settings.textColor || (settings.theme === "dark" ? "#abb2bf" : "#202124");
  const bg = settings.backgroundColor || (settings.theme === "dark" ? "#282c34" : "#ffffff");
  return EditorView.theme({
    "&": { color: fg, backgroundColor: bg },
    ".cm-scroller": { backgroundColor: bg },
    ".cm-content": { color: fg },
    ".cm-gutters": { backgroundColor: bg },
    ".cm-cursor": { borderLeftColor: fg },
  }, { dark: settings.theme === "dark" });
}

const placeholderExt = placeholder("Belum ada file terbuka. Buka file dari Project Explorer atau tekan + untuk membuat file baru.");

function baseExtensions(lang, editable = true) {
  return [
    lineNumbers(), highlightActiveLineGutter(), highlightSpecialChars(), history(), foldGutter(), drawSelection(),
    dropCursor(), EditorState.allowMultipleSelections.of(true), indentOnInput(),
    syntaxHighlighting(defaultHighlightStyle, { fallback: true }), bracketMatching(), closeBrackets(),
    autocompletion({ override: null, activateOnTyping: true }),
    EditorState.languageData.of(() => [{ autocomplete: lspCompletion }, { autocomplete: wordCompletion }]),
    rectangularSelection(), crosshairCursor(), highlightActiveLine(), highlightSelectionMatches(), lintGutter(),
    search({ top: true }),
    keymap.of([
      { key: "Mod-s", preventDefault: true, run: () => { bridge.onSave(current || ""); return true; } },
      { key: "Mod-Enter", preventDefault: true, run: () => { bridge.onRun(current || ""); return true; } },
      { key: "F12", run: () => { gotoDefinition(); return true; } },
      indentWithTab, ...closeBracketsKeymap, ...defaultKeymap, ...searchKeymap, ...historyKeymap, ...foldKeymap,
      ...completionKeymap, ...lintKeymap,
    ]),
    langConf.of(languageExtension(lang)),
    themeConf.of([settings.theme === "dark" ? oneDark : lightTheme, customColorsTheme()]),
    wrapConf.of(settings.wordWrap ? EditorView.lineWrapping : []),
    fontConf.of(fontTheme(settings.fontSize)),
    readOnlyConf.of([EditorState.readOnly.of(!editable), EditorView.editable.of(editable)]),
    editable ? [] : placeholderExt,
    indentConf.of([indentUnit.of(" ".repeat(settings.tabSize)), EditorState.tabSize.of(settings.tabSize)]),
    EditorView.updateListener.of((u) => {
      if (u.docChanged && !suppress && current) {
        const t = tabs.get(current);
        bridge.onChange(current, isDirty(current));
        if (t) t.state = u.state;
        lsp.change(current);
        let typed = "";
        u.changes.iterChanges((_a, _b, _c, _d, ins) => { typed = ins.toString(); });
        if (typed === "(" || typed === "()" || typed === ",") scheduleSignature();
        else if (typed === ")" || typed === ";") hideSignature();
      }
      if (u.selectionSet && sigLine !== null && u.state.doc.lineAt(u.state.selection.main.head).number !== sigLine) hideSignature();
      if (u.selectionSet && current) {
        const pos = u.state.selection.main.head;
        const line = u.state.doc.lineAt(pos);
        bridge.onCursor(line.number, pos - line.from + 1);
      }
    }),
  ];
}

const view = new EditorView({
  state: EditorState.create({ doc: "", extensions: baseExtensions("text", false) }),
  parent: document.getElementById("editor"),
});

function saveCurrentState() {
  if (current && tabs.has(current)) tabs.get(current).state = view.state;
}

function isDirty(id) {
  const t = tabs.get(id);
  if (!t) return false;
  const st = id === current ? view.state : t.state;
  return st.doc.toString() !== t.savedText;
}

function reconfigureAll() {
  view.dispatch({
    effects: [
      themeConf.reconfigure([settings.theme === "dark" ? oneDark : lightTheme, customColorsTheme()]),
      wrapConf.reconfigure(settings.wordWrap ? EditorView.lineWrapping : []),
      fontConf.reconfigure(fontTheme(settings.fontSize)),
      indentConf.reconfigure([indentUnit.of(" ".repeat(settings.tabSize)), EditorState.tabSize.of(settings.tabSize)]),
    ],
  });
  document.body.className = settings.theme;
}

function symbols(id) {
  const t = tabs.get(id || current);
  if (!t) return [];
  const pats = SYMBOL_PATTERNS[t.lang] || [];
  const doc = (id === current || !id ? view.state : t.state).doc;
  const out = [];
  for (let i = 1; i <= doc.lines; i++) {
    const text = doc.line(i).text;
    for (const p of pats) {
      const m = p.exec(text);
      if (m && m[1] && !["if", "for", "while", "switch", "return", "catch"].includes(m[1])) {
        out.push({ name: m[1], line: i, text: text.trim().slice(0, 120) });
        break;
      }
    }
  }
  return out;
}

function gotoLine(line, col) {
  const doc = view.state.doc;
  const ln = doc.line(Math.max(1, Math.min(line, doc.lines)));
  const pos = Math.min(ln.from + Math.max(0, (col || 1) - 1), ln.to);
  view.dispatch({ selection: EditorSelection.cursor(pos), scrollIntoView: true });
  view.focus();
}

function wordAtCursor() {
  const pos = view.state.selection.main.head;
  const w = view.state.wordAt(pos);
  return w ? view.state.sliceDoc(w.from, w.to) : "";
}

async function lspDefinition() {
  const id = current;
  const def = await lsp.definition(id, view.state, view.state.selection.main.head);
  if (!def) { if (!regexDefinition()) showInfo("Definisi tidak ditemukan"); return; }
  if (def.sameFile) { gotoLine(def.line, def.column); return; }
  if (def.path) { callBridge("onOpenFile", def.path, def.line, def.column); return; }
  showInfo("Definisi ada di luar proyek:\n" + def.uri.replace("file://", "") + ":" + def.line);
}

function gotoDefinition() {
  if (current && lsp.supports(current)) { lspDefinition(); return true; }
  return regexDefinition();
}

async function hoverAtCursor() {
  if (!current || !lsp.supports(current)) { showInfo("Info simbol butuh language server (C/C++/Python, proyek terbuka)."); return false; }
  const text = await lsp.hover(current, view.state, view.state.selection.main.head);
  showInfo(text || "Tidak ada info untuk simbol di kursor");
  return true;
}

function regexDefinition() {
  const word = wordAtCursor();
  if (!word) return false;
  const hit = symbols(current).find((s) => s.name === word);
  if (hit) { gotoLine(hit.line); return true; }
  return false;
}

// ---------- masalah, rename, petunjuk parameter ----------
function problemList() {
  const out = [];
  const st = view.state;
  forEachDiagnostic(st, (d, from) => {
    const line = st.doc.lineAt(from);
    out.push({ line: line.number, column: from - line.from + 1, severity: d.severity, message: d.message });
  });
  const rank = { error: 0, warning: 1, info: 2, hint: 3 };
  return out.sort((a, b) => a.line - b.line || (rank[a.severity] ?? 9) - (rank[b.severity] ?? 9));
}
function notifyProblems() {
  const list = current ? problemList() : [];
  callBridge("onProblems", list.filter((p) => p.severity === "error").length, list.filter((p) => p.severity === "warning").length);
}
function findTab(path) {
  for (const id of tabs.keys()) if (id.endsWith(":" + path)) return id;
  return null;
}
function applyEditsToTab(id, edits) {
  const t = tabs.get(id);
  const st = id === current ? view.state : t.state;
  const doc = st.doc;
  const pos = (l, c) => Math.min(doc.line(Math.min(l + 1, doc.lines)).from + c, doc.length);
  const changes = edits.map((e) => ({ from: pos(e.startLine, e.startChar), to: pos(e.endLine, e.endChar), insert: e.newText }))
    .sort((a, b) => a.from - b.from);
  if (id === current) view.dispatch({ changes, userEvent: "input.rename" });
  else { t.state = t.state.update({ changes }).state; bridge.onChange(id, isDirty(id)); lsp.change(id); }
}
let sigTimer = null;
let sigLine = null;
function sigEl() {
  let el = document.getElementById("cs-sig");
  if (!el) {
    el = document.createElement("div");
    el.id = "cs-sig";
    el.style.cssText = "position:fixed;left:6px;right:6px;top:4px;z-index:60;padding:6px 10px;border-radius:8px;" +
      "font:12.5px/1.4 'JetBrains Mono',monospace;white-space:pre-wrap;display:none;box-shadow:0 2px 10px rgba(0,0,0,.35)";
    el.addEventListener("click", hideSignature);
    document.body.appendChild(el);
  }
  const dark = settings.theme === "dark";
  el.style.background = dark ? "#2c313a" : "#fffbe6";
  el.style.color = dark ? "#d7dae0" : "#202124";
  el.style.border = "1px solid " + (dark ? "#4b5263" : "#e0d9a8");
  return el;
}
function hideSignature() { clearTimeout(sigTimer); sigLine = null; const el = document.getElementById("cs-sig"); if (el) el.style.display = "none"; }
function scheduleSignature() {
  if (!current || !lsp.supports(current)) return;
  clearTimeout(sigTimer);
  sigTimer = setTimeout(async () => {
    const id = current;
    const pos = view.state.selection.main.head;
    const r = await lsp.signatureHelp(id, view.state, pos);
    if (id !== current) return;
    if (!r) { hideSignature(); return; }
    const el = sigEl();
    el.textContent = "";
    const [a, b] = r.active || [0, 0];
    const parts = [r.label.slice(0, a), r.label.slice(a, b), r.label.slice(b)];
    parts.forEach((txt, i) => {
      const span = document.createElement("span");
      span.textContent = txt;
      if (i === 1 && txt) { span.style.fontWeight = "bold"; span.style.textDecoration = "underline"; span.style.color = settings.theme === "dark" ? "#e5c07b" : "#9a6700"; }
      el.appendChild(span);
    });
    if (r.more) el.appendChild(document.createTextNode(`   (+${r.more - 1} versi lain)`));
    el.style.display = "block";
    sigLine = view.state.doc.lineAt(pos).number;
  }, 150);
}

const KEY_COMMANDS = {
  left: cursorCharLeft, right: cursorCharRight, up: cursorLineUp, down: cursorLineDown,
  home: cursorLineBoundaryBackward, end: cursorLineBoundaryForward,
  tab: (v) => (v.state.selection.ranges.some((r) => !r.empty) ? indentMore(v) : insertTab(v)),
  untab: indentLess, comment: toggleComment, selectLine, duplicate: copyLineDown, deleteLine,
  undo, redo, complete: startCompletion,
};

window.CS = {
  version: "1.0.0",
  openTab(id, text, filename, lang) {
    saveCurrentState();
    const language = lang || detectLanguage(filename);
    const state = EditorState.create({ doc: text || "", extensions: baseExtensions(language) });
    tabs.set(id, { state, lang: language, filename, savedText: text || "" });
    this.switchTab(id);
    lsp.open(id, language, text || "");
    return language;
  },
  switchTab(id) {
    if (!tabs.has(id)) return false;
    saveCurrentState();
    current = id;
    suppress = true;
    view.setState(tabs.get(id).state);
    reconfigureAll();
    suppress = false;
    hideSignature();
    notifyProblems();
    view.focus();
    return true;
  },
  closeTab(id) {
    lsp.close(id);
    tabs.delete(id);
    if (current === id) {
      current = null;
      const next = tabs.keys().next();
      if (!next.done) this.switchTab(next.value);
      else { suppress = true; view.setState(EditorState.create({ doc: "", extensions: baseExtensions("text", false) })); suppress = false; }
    }
    return true;
  },
  hasTab(id) { return tabs.has(id); },
  getDoc(id) {
    const t = tabs.get(id || current);
    if (!t) return null;
    return ((id || current) === current ? view.state : t.state).doc.toString();
  },
  setDoc(id, text, markSaved) {
    const t = tabs.get(id);
    if (!t) return false;
    if (id === current) {
      suppress = true;
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } });
      suppress = false;
      t.state = view.state;
    } else {
      t.state = t.state.update({ changes: { from: 0, to: t.state.doc.length, insert: text } }).state;
    }
    if (markSaved) t.savedText = text;
    lsp.change(id);
    return true;
  },
  markSaved(id) {
    const t = tabs.get(id || current);
    if (t) t.savedText = this.getDoc(id || current);
    bridge.onChange(id || current, false);
  },
  isDirty(id) { return isDirty(id || current); },
  renameTab(oldId, newId, filename) {
    const t = tabs.get(oldId);
    if (!t) return false;
    lsp.close(oldId);
    tabs.delete(oldId);
    t.filename = filename;
    tabs.set(newId, t);
    if (current === oldId) current = newId;
    lsp.open(newId, t.lang, (newId === current ? view.state : t.state).doc.toString());
    return true;
  },
  setLanguage(lang) {
    const t = tabs.get(current);
    if (t) t.lang = lang;
    view.dispatch({ effects: langConf.reconfigure(languageExtension(lang)) });
  },
  setTheme(theme) { settings.theme = theme === "light" ? "light" : "dark"; reconfigureAll(); },
  setColors(textColor, backgroundColor) { settings.textColor = textColor || ""; settings.backgroundColor = backgroundColor || ""; reconfigureAll(); },
  setFontSize(px) { settings.fontSize = Math.max(8, Math.min(40, Number(px) || 14)); reconfigureAll(); },
  setWordWrap(on) { settings.wordWrap = !!on; reconfigureAll(); },
  setTabSize(n) { settings.tabSize = Math.max(1, Math.min(8, Number(n) || 4)); reconfigureAll(); },
  setReadOnly(on) { view.dispatch({ effects: readOnlyConf.reconfigure([EditorState.readOnly.of(!!on), EditorView.editable.of(!on)]) }); },
  hasFocus() { return view.hasFocus; },
  configure(json) { Object.assign(settings, typeof json === "string" ? JSON.parse(json) : json); reconfigureAll(); },
  undo() { return undo(view); },
  redo() { return redo(view); },
  canUndo() { return undoDepth(view.state) > 0; },
  canRedo() { return redoDepth(view.state) > 0; },
  openSearch() { openSearchPanel(view); },
  closeSearch() { closeSearchPanel(view); },
  foldAll() { foldAll(view); },
  unfoldAll() { unfoldAll(view); },
  gotoLine,
  gotoDefinition,
  hover() { hoverAtCursor(); return true; },
  showInfo,
  lspReset() { lsp.reset(); return true; },
  lspActive() { return !!(current && lsp.supports(current)); },
  symbols(id) { return JSON.stringify(symbols(id)); },
  insert(text) { view.dispatch(view.state.replaceSelection(text)); view.focus(); },
  // Baris tombol ekstra di atas keyboard HP: ketik karakter (kurung otomatis berpasangan) atau perintah.
  typeText(text) {
    if (!current) return false;
    if (text.length === 1) {
      const tr = insertBracket(view.state, text);
      if (tr) { view.dispatch(tr); view.focus(); return true; }
    }
    view.dispatch(view.state.replaceSelection(text), { scrollIntoView: true });
    view.focus();
    return true;
  },
  key(name) {
    if (!current) return false;
    const cmd = KEY_COMMANDS[name];
    const ok = cmd ? cmd(view) : false;
    view.focus();
    return !!ok;
  },
  focus() { view.focus(); },
  // diagnostics: [{line, column?, endLine?, endColumn?, severity: error|warning|info, message}]
  setDiagnostics(json) {
    const items = typeof json === "string" ? JSON.parse(json) : json;
    const doc = view.state.doc;
    const diags = items.filter((d) => d.line >= 1 && d.line <= doc.lines).map((d) => {
      const l = doc.line(d.line);
      const from = Math.min(l.from + Math.max(0, (d.column || 1) - 1), l.to);
      const el = d.endLine && d.endLine <= doc.lines ? doc.line(d.endLine) : l;
      const to = d.endColumn ? Math.min(el.from + d.endColumn - 1, el.to) : l.to;
      return { from, to: Math.max(from, to), severity: d.severity || "error", message: d.message || "" };
    });
    view.dispatch(setDiagnostics(view.state, diags));
    notifyProblems();
    return diags.length;
  },
  clearDiagnostics() { view.dispatch(setDiagnostics(view.state, [])); notifyProblems(); },
  /** Daftar masalah (error/peringatan) file aktif, urut baris: JSON [{line, column, severity, message}]. */
  problems() { return JSON.stringify(problemList()); },
  /** Ganti isi dokumen dengan hasil format; hanya bagian yang berubah diganti agar kursor & undo tetap wajar. */
  applyFormatted(id, text) {
    const t = tabs.get(id);
    if (!t) return false;
    const st = id === current ? view.state : t.state;
    const old = st.doc.toString();
    if (old === text) return false;
    let a = 0;
    while (a < old.length && a < text.length && old[a] === text[a]) a++;
    let b = 0;
    while (b < old.length - a && b < text.length - a && old[old.length - 1 - b] === text[text.length - 1 - b]) b++;
    const change = { from: a, to: old.length - b, insert: text.slice(a, text.length - b) };
    if (id === current) view.dispatch({ changes: change, userEvent: "input.format" });
    else { t.state = t.state.update({ changes: change }).state; bridge.onChange(id, isDirty(id)); lsp.change(id); }
    return true;
  },
  /** Cari semua referensi simbol di kursor; hasil lewat bridge.onReferences(json). */
  // filesJson (opsional): [{path, text, lang}] file proyek lain yang dibuka dulu di LSP (C/C++: clangd hanya tahu file terbuka).
  findReferences(filesJson) {
    if (!current || !lsp.supports(current)) { showInfo("Cari referensi butuh language server untuk bahasa ini."); return false; }
    const id = current;
    const word = wordAtCursor();
    const pos = view.state.selection.main.head;
    lsp.preload(id, filesJson ? JSON.parse(filesJson) : []).then(() => lsp.references(id, stateOf(id), pos)).then((r) => {
      if (!r || r.error) { showInfo("Referensi tidak ditemukan" + (r && r.error ? ": " + r.error : "")); return; }
      const out = r.map((x) => {
        const tid = x.path ? findTab(x.path) : null;
        let text = "";
        if (tid) { const d = (tid === current ? view.state : tabs.get(tid).state).doc; if (x.line <= d.lines) text = d.line(x.line).text.trim(); }
        return { ...x, text: text.slice(0, 160) };
      });
      callBridge("onReferences", JSON.stringify({ symbol: word, items: out }));
    });
    return true;
  },
  /** Ganti nama simbol di kursor (LSP). Tab terbuka diubah langsung; file lain dikirim ke Kotlin (onRenameEdits). */
  renameSymbol(newName, filesJson) {
    if (!current || !lsp.supports(current)) { showInfo("Ganti nama butuh language server untuk bahasa ini."); return false; }
    const id = current;
    const pos = view.state.selection.main.head;
    lsp.preload(id, filesJson ? JSON.parse(filesJson) : []).then(() => lsp.rename(id, stateOf(id), pos, newName)).then((r) => {
      if (!r || r.error) { showInfo("Ganti nama gagal" + (r && r.error ? ": " + r.error : "")); return; }
      const remote = {};
      let local = 0, count = 0;
      for (const [path, edits] of Object.entries(r.edits)) {
        count += edits.length;
        const tid = findTab(path);
        if (tid) { applyEditsToTab(tid, edits); local++; } else remote[path] = edits;
      }
      lsp.dropGhosts(id);
      callBridge("onRenameEdits", JSON.stringify({ newName, files: Object.keys(r.edits).length, edits: count, local, remote }));
    });
    return true;
  },
  currentWord() { return wordAtCursor(); },
  /** Server LSP tab aktif ("clangd" / "pyright" / …) atau "" bila tidak ada. */
  lspServer() { const d = current && lsp.docFor(current); return d && lsp.supports(current) ? d.server : ""; },
};

// WebView tertentu melaporkan viewport yang valid tetapi ukuran CSS html/body = 0.
// Tetapkan tinggi eksplisit dari viewport aktual agar rantai layout tidak bergantung
// pada percentage-height dari containing block yang tidak terukur.
function syncEditorViewport() {
  const vv = window.visualViewport;
  const height = Math.max(1, Math.round((vv && vv.height) || window.innerHeight || document.documentElement.clientHeight || 1));
  const width = Math.max(1, Math.round((vv && vv.width) || window.innerWidth || document.documentElement.clientWidth || 1));
  const html = document.documentElement;
  const body = document.body;
  const root = document.getElementById("editor");
  html.style.setProperty("height", height + "px", "important");
  html.style.setProperty("min-height", height + "px", "important");
  html.style.setProperty("width", width + "px", "important");
  body.style.setProperty("height", height + "px", "important");
  body.style.setProperty("min-height", height + "px", "important");
  body.style.setProperty("width", width + "px", "important");
  if (root) {
    root.style.setProperty("height", height + "px", "important");
    root.style.setProperty("min-height", "0px", "important");
    root.style.setProperty("width", width + "px", "important");
    root.style.setProperty("flex", "0 0 " + height + "px", "important");
  }
  if (view && view.dom) {
    view.dom.style.setProperty("height", height + "px", "important");
    view.dom.style.setProperty("min-height", "0px", "important");
    view.dom.style.setProperty("width", "100%", "important");
  }
}
window.addEventListener("resize", syncEditorViewport, { passive: true });
if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", syncEditorViewport, { passive: true });
}
document.addEventListener("DOMContentLoaded", syncEditorViewport, { once: true });
syncEditorViewport();

// Ketukan di area kosong di bawah teks tetap memberi fokus (memunculkan keyboard).
document.getElementById("editor").addEventListener("touchend", () => { if (current && !view.hasFocus) view.focus(); });
document.body.className = settings.theme;
bridge.onReady();
