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
};
