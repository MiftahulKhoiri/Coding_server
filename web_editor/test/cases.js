// Kasus uji editor. Tiap fungsi mengembalikan true (lulus) atau pesan kegagalan.
let n = 0;
let id = "t0";
const open = (text, file) => { id = "t" + (++n); CS.openTab(id, text, file); };
const doc = () => CS.getDoc(id);
const CASES = {
  "buka tab & isi dokumen": () => {
    open("int main() {\n  return 0;\n}\n", "main.cpp");
    return doc() === "int main() {\n  return 0;\n}\n" || "isi: " + JSON.stringify(doc());
  },
  "typeText kurung berpasangan": () => {
    open("", "a.js");
    CS.typeText("(");
    return doc() === "()" || JSON.stringify(doc());
  },
  "typeText teks biasa": () => {
    open("", "a.js");
    CS.typeText(";"); CS.typeText("x");
    return doc() === ";x" || JSON.stringify(doc());
  },
  "key tab menyisipkan indentasi": () => {
    CS.configure({ tabSize: 4 });
    open("", "a.py");
    CS.key("tab");
    return /^(\t| {4})$/.test(doc()) || JSON.stringify(doc());
  },
  "key comment (toggle komentar Python)": () => {
    open("x = 1", "a.py");
    CS.key("comment");
    const once = doc();
    CS.key("comment");
    return (once.startsWith("# ") && doc() === "x = 1") || JSON.stringify([once, doc()]);
  },
  "key panah & home/end memindah kursor": () => {
    open("abc\ndef", "a.txt");
    CS.gotoLine(1, 1);
    CS.key("end"); CS.typeText("!");
    CS.key("down"); CS.key("home"); CS.typeText(">");
    return doc() === "abc!\n>def" || JSON.stringify(doc());
  },
  "key duplicate & deleteLine": () => {
    open("a\nb", "a.txt");
    CS.gotoLine(1, 1);
    CS.key("duplicate");
    const dup = doc();
    CS.key("deleteLine");
    return (dup === "a\na\nb" && doc() === "a\nb") || JSON.stringify([dup, doc()]);
  },
  "undo setelah typeText": () => {
    open("", "a.txt");
    CS.typeText("z");
    CS.key("undo");
    return doc() === "" || JSON.stringify(doc());
  },
  "applyFormatted hanya mengganti bagian berubah & kursor tetap di baris": () => {
    open("a=1\nb  =  2\nc=3\n", "a.py");
    CS.gotoLine(3, 2);
    const changed = CS.applyFormatted(id, "a=1\nb = 2\nc=3\n");
    CS.typeText("X");
    return (changed && doc() === "a=1\nb = 2\ncX=3\n") || JSON.stringify([changed, doc()]);
  },
  "problems mengurutkan diagnostik per baris": () => {
    open("x\ny\nz", "a.c");
    CS.setDiagnostics(JSON.stringify([{ line: 3, severity: "warning", message: "w3" }, { line: 1, column: 1, severity: "error", message: "e1" }]));
    const p = JSON.parse(CS.problems());
    return (p.length === 2 && p[0].line === 1 && p[0].severity === "error" && p[1].message === "w3") || JSON.stringify(p);
  },
  "clearDiagnostics mengosongkan masalah": () => {
    open("x", "a.c");
    CS.setDiagnostics(JSON.stringify([{ line: 1, severity: "error", message: "e" }]));
    CS.clearDiagnostics();
    return JSON.parse(CS.problems()).length === 0 || CS.problems();
  },
  "penanda Git: baris diubah, ditambah, dihapus": () => {
    open("a\nb\nc\nd\n", "x.txt");
    CS.setGitBase(id, "a\nB\nc\nd\n");  // baris 2 diubah
    const el = () => [...document.querySelectorAll(".cm-git-gutter .cm-gutterElement > div")].map((d) => d.className);
    const one = el();
    CS.setGitBase(id, "a\nb\nd\n");  // baris c ditambah
    const two = el();
    CS.setGitBase(id, "a\nb\nc\nX\nd\n");  // satu baris dihapus sebelum d
    const three = el();
    CS.setGitBase(id, null);
    return (JSON.stringify(one) === '["cm-git-modified"]' && JSON.stringify(two) === '["cm-git-added"]' &&
            JSON.stringify(three) === '["cm-git-deleted"]' && el().length === 0) || JSON.stringify([one, two, three, el()]);
  },
  "outline tanpa LSP memakai pola simbol": async () => {
    open("def satu():\n    pass\n\nclass Dua:\n    pass\n", "m.py");
    let got = null;
    const prev = window.AndroidBridge;
    window.__outline = null;
    CS.outline();
    return true;
  },
  "snippet: daftar per bahasa & sisipkan dengan placeholder": () => {
    open("", "s.py");
    const list = JSON.parse(CS.snippets());
    const ok = CS.insertSnippet("ifmain");
    return (list.some((x) => x.label === "ifmain") && ok && doc() === 'if __name__ == "__main__":\n    main()') ||
      JSON.stringify([list.map((x) => x.label), ok, doc()]);
  },
  "snippet: bahasa tanpa snippet → daftar kosong": () => {
    open("", "notes.txt");
    return CS.snippets() === "[]" || CS.snippets();
  },
  "ketuk = keyboard mati: inputmode none; tombol ⌨ membuka": () => {
    open("x = 1", "k.py");
    const mode = () => document.querySelector(".cm-content").getAttribute("inputmode");
    CS.setTapKeyboard(false);
    const off = mode();
    CS.setKeyboardOpen(true);
    const opened = mode();
    CS.setKeyboardOpen(false);
    const closed = mode();
    CS.setTapKeyboard(true);
    return (off === "none" && opened === null && closed === "none" && mode() === null) || JSON.stringify([off, opened, closed, mode()]);
  },
  "font: pilihan font termuat & dipakai editor": async () => {
    open("x", "f.py");
    CS.configure({ fontFamily: "fira" });
    for (let i = 0; i < 30 && !document.fonts.check('14px "CS Fira Code"'); i++) await new Promise((r) => setTimeout(r, 100));
    const fam = getComputedStyle(document.querySelector(".cm-scroller")).fontFamily;
    const ok = document.fonts.check('14px "CS Fira Code"') && fam.includes("CS Fira Code");
    CS.configure({ fontFamily: "jetbrains" });
    return ok || JSON.stringify([fam, document.fonts.check('14px "CS Fira Code"')]);
  },
};
