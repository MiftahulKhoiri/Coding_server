// Fitur editor tambahan: penanda baris berubah (Git), snippet kode per bahasa.
import { StateField, StateEffect, RangeSet } from "@codemirror/state";
import { gutter, GutterMarker, EditorView } from "@codemirror/view";
import { snippetCompletion, snippet } from "@codemirror/autocomplete";
import { diffLines } from "diff";

// ---------- penanda Git (bandingkan dokumen dengan isi file di HEAD) ----------
class ChangeMarker extends GutterMarker {
  constructor(kind) { super(); this.kind = kind; }
  eq(o) { return o.kind === this.kind; }
  toDOM() {
    const el = document.createElement("div");
    el.className = "cm-git-" + this.kind;
    return el;
  }
}
const MARK = { added: new ChangeMarker("added"), modified: new ChangeMarker("modified"), deleted: new ChangeMarker("deleted") };

export const setGitMarks = StateEffect.define();
const gitMarks = StateField.define({
  create: () => RangeSet.empty,
  update(set, tr) {
    for (const e of tr.effects) if (e.is(setGitMarks)) return e.value;
    return tr.docChanged ? set.map(tr.changes) : set;
  },
});

/** Hitung penanda per baris: {line: "added"|"modified"|"deleted"} dari teks dasar (HEAD) ke teks sekarang. */
export function computeLineChanges(base, text) {
  const out = new Map();
  if (base === null || base === undefined) return out;
  let line = 1;
  const parts = diffLines(base, text);
  for (let i = 0; i < parts.length; i++) {
    const p = parts[i];
    if (!p.added && !p.removed) { line += p.count; continue; }
    if (p.removed) {
      const next = parts[i + 1];
      if (next && next.added) {  // diganti: baris lama dihapus lalu baris baru ditambah
        const common = Math.min(p.count, next.count);
        for (let k = 0; k < next.count; k++) out.set(line + k, k < common ? "modified" : "added");
        line += next.count;
        i++;
      } else {
        if (!out.has(line)) out.set(line, "deleted");
      }
      continue;
    }
    for (let k = 0; k < p.count; k++) out.set(line + k, "added");
    line += p.count;
  }
  return out;
}

export function gitMarksFor(state, base) {
  const changes = computeLineChanges(base, state.doc.toString());
  const ranges = [];
  for (const [ln, kind] of [...changes.entries()].sort((a, b) => a[0] - b[0])) {
    const n = Math.min(ln, state.doc.lines);
    ranges.push(MARK[kind].range(state.doc.line(n).from));
  }
  return RangeSet.of(ranges, true);
}

export const gitGutter = [
  gitMarks,
  gutter({ class: "cm-git-gutter", markers: (v) => v.state.field(gitMarks) }),
  EditorView.baseTheme({
    ".cm-git-gutter": { width: "4px", marginRight: "2px" },
    ".cm-git-gutter .cm-gutterElement": { padding: "0" },
    ".cm-git-added": { background: "#2ea043", width: "4px", height: "100%" },
    ".cm-git-modified": { background: "#3b82f6", width: "4px", height: "100%" },
    ".cm-git-deleted": { width: 0, height: 0, borderTop: "4px solid transparent", borderBottom: "4px solid transparent",
                         borderLeft: "5px solid #e5534b", marginTop: "-4px" },
  }),
];

// ---------- snippet (ketik awalan lalu pilih dari saran) ----------
const S = (label, detail, template) => Object.assign(snippetCompletion(template, { label, detail, type: "keyword", boost: -5 }),
  { template });
const SNIPPETS = {
  python: [
    S("def", "fungsi", "def ${name}(${args}):\n\t${pass}"),
    S("class", "kelas", "class ${Name}:\n\tdef __init__(self${, args}):\n\t\t${pass}"),
    S("ifmain", "if __name__ == '__main__'", "if __name__ == \"__main__\":\n\t${main()}"),
    S("for", "for … in", "for ${item} in ${items}:\n\t${pass}"),
    S("try", "try/except", "try:\n\t${pass}\nexcept ${Exception} as e:\n\t${raise}"),
    S("with", "with open", "with open(${path}, \"r\", encoding=\"utf-8\") as f:\n\t${data} = f.read()"),
  ],
  javascript: [
    S("func", "function", "function ${name}(${args}) {\n\t${}\n}"),
    S("arrow", "arrow function", "const ${name} = (${args}) => {\n\t${}\n};"),
    S("for", "for loop", "for (let ${i} = 0; ${i} < ${n}; ${i}++) {\n\t${}\n}"),
    S("forof", "for … of", "for (const ${item} of ${items}) {\n\t${}\n}"),
    S("class", "class", "class ${Name} {\n\tconstructor(${args}) {\n\t\t${}\n\t}\n}"),
    S("try", "try/catch", "try {\n\t${}\n} catch (err) {\n\tconsole.error(err);\n}"),
    S("log", "console.log", "console.log(${});"),
    S("asyncfn", "async function", "async function ${name}(${args}) {\n\t${}\n}"),
  ],
  c: [
    S("main", "int main", "#include <stdio.h>\n\nint main(void) {\n\t${}\n\treturn 0;\n}"),
    S("for", "for loop", "for (int ${i} = 0; ${i} < ${n}; ${i}++) {\n\t${}\n}"),
    S("printf", "printf", "printf(\"${%d}\\n\", ${x});"),
    S("struct", "struct", "typedef struct {\n\t${int x;}\n} ${Name};"),
  ],
  cpp: [
    S("main", "int main", "#include <iostream>\n\nint main() {\n\t${}\n\treturn 0;\n}"),
    S("for", "for loop", "for (int ${i} = 0; ${i} < ${n}; ++${i}) {\n\t${}\n}"),
    S("forr", "range for", "for (const auto& ${item} : ${items}) {\n\t${}\n}"),
    S("cout", "std::cout", "std::cout << ${} << '\\n';"),
    S("class", "class", "class ${Name} {\npublic:\n\t${Name}();\n\nprivate:\n\t${}\n};"),
    S("vector", "std::vector", "std::vector<${int}> ${v};"),
  ],
  java: [
    S("main", "public static void main", "public static void main(String[] args) {\n\t${}\n}"),
    S("sout", "System.out.println", "System.out.println(${});"),
    S("for", "for loop", "for (int ${i} = 0; ${i} < ${n}; ${i}++) {\n\t${}\n}"),
    S("class", "class", "public class ${Name} {\n\t${}\n}"),
  ],
  csharp: [
    S("main", "static void Main", "static void Main(string[] args)\n{\n\t${}\n}"),
    S("cw", "Console.WriteLine", "Console.WriteLine(${});"),
    S("for", "for loop", "for (int ${i} = 0; ${i} < ${n}; ${i}++)\n{\n\t${}\n}"),
  ],
  go: [
    S("main", "package main", "package main\n\nimport \"fmt\"\n\nfunc main() {\n\tfmt.Println(${})\n}"),
    S("func", "func", "func ${name}(${args}) ${error} {\n\t${}\n}"),
    S("iferr", "if err != nil", "if err != nil {\n\treturn ${err}\n}"),
    S("for", "for range", "for ${i}, ${v} := range ${items} {\n\t${}\n}"),
  ],
  php: [
    S("php", "<?php", "<?php\n\n${}"),
    S("function", "function", "function ${name}(${args})\n{\n\t${}\n}"),
    S("foreach", "foreach", "foreach (${$items} as ${$item}) {\n\t${}\n}"),
    S("echo", "echo", "echo ${};"),
  ],
  html: [
    S("html5", "kerangka HTML5", "<!DOCTYPE html>\n<html lang=\"id\">\n<head>\n\t<meta charset=\"UTF-8\">\n\t<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n\t<title>${Judul}</title>\n</head>\n<body>\n\t${}\n</body>\n</html>"),
    S("script", "<script>", "<script src=\"${app.js}\"><\/script>"),  // <\/ : bundel disisipkan di <script> inline
    S("link", "<link css>", "<link rel=\"stylesheet\" href=\"${style.css}\">"),
  ],
  shell: [
    S("bash", "#!/bin/bash", "#!/usr/bin/env bash\nset -euo pipefail\n\n${}"),
    S("if", "if", "if [ ${cond} ]; then\n\t${}\nfi"),
    S("for", "for", "for ${f} in ${*}; do\n\t${}\ndone"),
  ],
};
SNIPPETS.typescript = SNIPPETS.javascript;

/** Sumber completion snippet untuk bahasa tertentu (aktif setelah 2 huruf). */
export function snippetSource(lang) {
  const list = SNIPPETS[lang];
  if (!list) return () => null;
  return (ctx) => {
    const word = ctx.matchBefore(/\w+$/);
    if (!word || (word.text.length < 2 && !ctx.explicit)) return null;
    return { from: word.from, options: list, validFor: /^\w*$/ };
  };
}
export const SNIPPET_LANGS = Object.keys(SNIPPETS);

/** Daftar snippet bahasa (untuk menu "Sisipkan snippet"). */
export function snippetList(lang) {
  return (SNIPPETS[lang] || []).map((x) => ({ label: x.label, detail: x.detail, preview: x.template.replace(/\$\{([^}]*)\}/g, "$1") }));
}

/** Sisipkan snippet di kursor (placeholder bisa diisi berurutan dengan Tab). */
export function insertSnippet(view, lang, label) {
  const sn = (SNIPPETS[lang] || []).find((x) => x.label === label);
  if (!sn) return false;
  const r = view.state.selection.main;
  snippet(sn.template)(view, null, r.from, r.to);
  return true;
}
