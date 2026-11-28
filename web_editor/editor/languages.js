// Pemetaan bahasa -> ekstensi CodeMirror.
import { StreamLanguage } from "@codemirror/language";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { php } from "@codemirror/lang-php";
import { go } from "@codemirror/lang-go";
import { cpp } from "@codemirror/lang-cpp";
import { java } from "@codemirror/lang-java";
import { sql, SQLite } from "@codemirror/lang-sql";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { json } from "@codemirror/lang-json";
import { xml } from "@codemirror/lang-xml";
import { yaml } from "@codemirror/lang-yaml";
import { markdown } from "@codemirror/lang-markdown";
import { csharp, kotlin } from "@codemirror/legacy-modes/mode/clike";
import { shell } from "@codemirror/legacy-modes/mode/shell";
import { http } from "@codemirror/legacy-modes/mode/http";

const EXT = {
  py: "python", js: "javascript", mjs: "javascript", cjs: "javascript", ts: "typescript", tsx: "typescript", jsx: "javascript", mts: "typescript", cts: "typescript", php: "php",
  go: "go", c: "c", h: "c", cpp: "cpp", cc: "cpp", cxx: "cpp", hpp: "cpp", java: "java", cs: "csharp",
  sql: "sql", html: "html", htm: "html", css: "css", scss: "css", json: "json", jsonc: "json", xml: "xml", csproj: "xml", yaml: "yaml",
  yml: "yaml", md: "markdown", sh: "shell", bash: "shell", http: "http", kt: "kotlin",
};

export function detectLanguage(filename) {
  const m = /\.([^.]+)$/.exec(filename || "");
  return (m && EXT[m[1].toLowerCase()]) || "text";
}

export function languageExtension(lang) {
  switch (lang) {
    case "python": return python();
    case "javascript": return javascript();
    case "typescript": return javascript({ typescript: true });
    case "php": return php();
    case "go": return go();
    case "c": case "cpp": return cpp();
    case "java": return java();
    case "csharp": return StreamLanguage.define(csharp);
    case "kotlin": return StreamLanguage.define(kotlin);
    case "sql": return sql({ dialect: SQLite });
    case "html": return html();
    case "css": return css();
    case "json": return json();
    case "xml": return xml();
    case "yaml": return yaml();
    case "markdown": return markdown();
    case "shell": return StreamLanguage.define(shell);
    case "http": return StreamLanguage.define(http);
    default: return [];
  }
}

// Pola definisi sederhana untuk "document symbols" & "go to definition" (bukan language server).
export const SYMBOL_PATTERNS = {
  python: [/^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)/, /^\s*class\s+([A-Za-z_]\w*)/],
  javascript: [/function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(/, /^\s*class\s+([A-Za-z_$][\w$]*)/,
    /^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>/],
  php: [/function\s+([A-Za-z_]\w*)\s*\(/, /^\s*(?:abstract\s+|final\s+)?class\s+([A-Za-z_]\w*)/],
  go: [/^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(/, /^type\s+([A-Za-z_]\w*)\s+/],
  c: [/^[A-Za-z_][\w\s\*]*?\b([A-Za-z_]\w*)\s*\([^;]*\)\s*\{?\s*$/, /^\s*(?:typedef\s+)?struct\s+([A-Za-z_]\w*)/],
  cpp: [/^[A-Za-z_][\w\s\*&:<>,]*?\b([A-Za-z_]\w*)\s*\([^;]*\)\s*(?:const\s*)?\{?\s*$/, /^\s*(?:class|struct)\s+([A-Za-z_]\w*)/],
  java: [/^\s*(?:public|private|protected|static|\s)*(?:class|interface|enum|record)\s+([A-Za-z_]\w*)/,
    /^\s*(?:public|private|protected|static|final|synchronized|\s)+[\w<>\[\], ]+\s+([A-Za-z_]\w*)\s*\([^;]*$/],
  csharp: [/^\s*(?:public|private|internal|protected|static|sealed|abstract|partial|\s)*(?:class|interface|struct|enum|record)\s+([A-Za-z_]\w*)/,
    /^\s*(?:public|private|internal|protected|static|async|override|virtual|\s)+[\w<>\[\], ?]+\s+([A-Za-z_]\w*)\s*\(/],
  sql: [/^\s*CREATE\s+(?:TABLE|VIEW|INDEX|TRIGGER)\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?([A-Za-z_]\w*)/i],
  shell: [/^\s*(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\)\s*\{?/],
};
