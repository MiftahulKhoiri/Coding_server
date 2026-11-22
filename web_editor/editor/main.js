// Editor CODING_SERVER untuk WebView Android. API global: window.CS (dipanggil dari Kotlin
// lewat evaluateJavascript). Callback ke Kotlin lewat objek AndroidBridge (addJavascriptInterface).
import { EditorState, Compartment, EditorSelection } from "@codemirror/state";
import {
  EditorView, keymap, lineNumbers, highlightActiveLineGutter, highlightSpecialChars, drawSelection,
  dropCursor, rectangularSelection, crosshairCursor, highlightActiveLine, placeholder,
} from "@codemirror/view";
import { defaultKeymap, history, historyKeymap, indentWithTab, undo, redo, undoDepth, redoDepth } from "@codemirror/commands";
import {
  indentOnInput, syntaxHighlighting, defaultHighlightStyle, bracketMatching, foldGutter, foldKeymap,
  foldAll, unfoldAll, indentUnit,
} from "@codemirror/language";
import { searchKeymap, highlightSelectionMatches, openSearchPanel, closeSearchPanel, search } from "@codemirror/search";
import {
  autocompletion, completionKeymap, closeBrackets, closeBracketsKeymap, completeAnyWord,
} from "@codemirror/autocomplete";
import { lintKeymap, setDiagnostics, lintGutter } from "@codemirror/lint";
import { oneDark } from "@codemirror/theme-one-dark";
import { detectLanguage, languageExtension, SYMBOL_PATTERNS } from "./languages.js";

// Android WebView: CodeMirror memakai API EditContext bila tersedia. Pada sebagian WebView/keyboard
// (Gboard, SwiftKey) input lewat EditContext tidak sampai ke editor sehingga "tidak bisa mengetik".
// Paksa jalur contenteditable biasa yang sudah teruji di semua WebView.
EditorView.EDIT_CONTEXT = false;

const bridge = window.AndroidBridge || {
  onReady() {}, onChange() {}, onSave() {}, onRun() {}, onCursor() {}, onLog(m) { console.log(m); },
};

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
    EditorState.languageData.of(() => [{ autocomplete: completeAnyWord }]),
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
      }
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

function gotoDefinition() {
  const word = wordAtCursor();
  if (!word) return false;
  const hit = symbols(current).find((s) => s.name === word);
  if (hit) { gotoLine(hit.line); return true; }
  return false;
}

window.CS = {
  version: "1.0.0",
  openTab(id, text, filename, lang) {
    saveCurrentState();
    const language = lang || detectLanguage(filename);
    const state = EditorState.create({ doc: text || "", extensions: baseExtensions(language) });
    tabs.set(id, { state, lang: language, filename, savedText: text || "" });
    this.switchTab(id);
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
    view.focus();
    return true;
  },
  closeTab(id) {
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
    tabs.delete(oldId);
    t.filename = filename;
    tabs.set(newId, t);
    if (current === oldId) current = newId;
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
  symbols(id) { return JSON.stringify(symbols(id)); },
  insert(text) { view.dispatch(view.state.replaceSelection(text)); view.focus(); },
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
    return diags.length;
  },
  clearDiagnostics() { view.dispatch(setDiagnostics(view.state, [])); },
};

// Diagnostik input Android: status fokus, DOM editor, dan event IME.
function editorRuntimeDiag(eventName) {
  const root = document.getElementById("editor");
  const cm = document.querySelector(".cm-editor");
  const scroller = document.querySelector(".cm-scroller");
  const content = document.querySelector(".cm-content");
  const editable = document.querySelector(".cm-content[contenteditable='true']");
  const text = view.state.doc.toString();
  const dimensions = (el) => {
    if (!el) return "none";
    const r = el.getBoundingClientRect();
    return Math.round(r.width) + "x" + Math.round(r.height);
  };
  const status = "EDITOR_DIAG:runtime event=" + (eventName || "check") +
    ", viewport=" + window.innerWidth + "x" + window.innerHeight +
    ", html=" + dimensions(document.documentElement) +
    ", body=" + dimensions(document.body) +
    ", root=" + dimensions(root) +
    ", cm=" + dimensions(cm) +
    ", scroller=" + dimensions(scroller) +
    ", content=" + !!content + ", editable=" + !!editable +
    ", focus=" + view.hasFocus + ", active=" + (document.activeElement ? document.activeElement.className : "none") +
    ", chars=" + text.length;
  bridge.onLog(status);
  return status;
}
document.addEventListener("focusin", e => { if (e.target && e.target.closest && e.target.closest(".cm-content")) editorRuntimeDiag("focusin"); }, true);
document.addEventListener("beforeinput", e => { if (e.target && e.target.closest && e.target.closest(".cm-content")) editorRuntimeDiag("beforeinput:" + e.inputType); }, true);
document.addEventListener("input", e => { if (e.target && e.target.closest && e.target.closest(".cm-content")) editorRuntimeDiag("input"); }, true);
document.addEventListener("keydown", e => { if (e.target && e.target.closest && e.target.closest(".cm-content")) editorRuntimeDiag("keydown:" + e.key); }, true);

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
  editorRuntimeDiag("viewport-sync");
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
