"""Language server nyata (clangd/pyright) lewat /ws/lsp di sandbox. Dilewati bila servernya tidak terpasang."""
import time

import pytest

from backend.config import get_settings
from backend.services.lsp_service import LspService

SVC = LspService(get_settings())
URI = "file:///workspace/"


def lsp_available(lang):
    return SVC.server_for(lang) is not None


class Client:
    def __init__(self, ws):
        self.ws, self.next_id, self.notes = ws, 1, []

    def request(self, method, params):
        rid = self.next_id
        self.next_id += 1
        self.ws.send_json({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        while True:
            m = self.ws.receive_json()
            if m.get("id") == rid and "method" not in m:
                return m
            self.notes.append(m)

    def notify(self, method, params):
        self.ws.send_json({"jsonrpc": "2.0", "method": method, "params": params})

    def wait_note(self, method, pred=lambda m: True, limit=400):
        for m in list(self.notes):
            if m.get("method") == method and pred(m):
                self.notes.remove(m)
                return m
        for _ in range(limit):
            m = self.ws.receive_json()
            if m.get("method") == method and pred(m):
                return m
            self.notes.append(m)
        raise AssertionError(f"tidak menerima {method}")

    def init(self):
        ready = self.ws.receive_json()
        assert ready["method"] == "cs/ready", ready
        r = self.request("initialize", {"capabilities": {"textDocument": {
            "publishDiagnostics": {}, "completion": {"completionItem": {"snippetSupport": False}},
            "hover": {"contentFormat": ["plaintext", "markdown"]}, "definition": {}}}})
        assert "capabilities" in r["result"], r
        self.notify("initialized", {})
        return r

    def shutdown(self):
        """Tutup rapi seperti editor: shutdown + exit, lalu tunggu server menutup WS. Tanpa ini TestClient
        membatalkan handler yang masih membereskan proses language server (tes kadang gagal CancelledError)."""
        self.request("shutdown", None)
        self.notify("exit", None)
        self.wait_note("cs/exit")
        assert self.ws.receive()["type"] == "websocket.close"


def put(client, auth, project, path, content):
    assert client.put("/api/v1/files/write", json={"project_id": project, "path": path, "content": content},
                      headers=auth).status_code == 200


def test_lsp_status(client, auth):
    st = client.get("/api/v1/lsp/status", headers=auth).json()
    assert set(st["languages"]) >= {"c", "cpp", "python"}


@pytest.mark.skipif(not lsp_available("cpp"), reason="clangd tidak terpasang")
def test_clangd_diagnostics_completion_definition(client, auth, token, project):
    put(client, auth, project, "src/util.h", "#pragma once\nint tambah(int a, int b);\n")
    put(client, auth, project, "src/util.cpp", '#include "util.h"\nint tambah(int a, int b) { return a + b; }\n')
    text = '#include "util.h"\n#include <string>\nint main() {\n  std::string nama = "pi";\n  int x = tambah(1, 2);\n  return y;\n}\n'
    with client.websocket_connect(f"/ws/lsp?project_id={project}&language=cpp&token={token}") as ws:
        c = Client(ws)
        c.init()
        uri = URI + "src/main.cpp"
        c.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "cpp", "version": 1, "text": text}})
        diag = c.wait_note("textDocument/publishDiagnostics", lambda m: m["params"]["uri"] == uri and m["params"]["diagnostics"])
        msgs = " | ".join(d["message"] for d in diag["params"]["diagnostics"])
        assert "y" in msgs, msgs                      # 'use of undeclared identifier y'
        assert "/home/" not in str(diag), diag        # path asli disamarkan
        # sinkronisasi perubahan (didChange) lalu completion anggota std::string setelah "nama."
        text2 = text.replace("  return y;", "  nama.\n  return 0;")
        c.notify("textDocument/didChange", {"textDocument": {"uri": uri, "version": 2}, "contentChanges": [{"text": text2}]})
        r = c.request("textDocument/completion", {"textDocument": {"uri": uri}, "position": {"line": 5, "character": 7}})
        items = r["result"]["items"] if isinstance(r["result"], dict) else r["result"]
        labels = {i["label"].strip().split("(")[0] for i in items}
        assert "size" in labels or "length" in labels, list(labels)[:20]
        # go-to-definition ke deklarasi di header lain (lintas file)
        r = c.request("textDocument/definition", {"textDocument": {"uri": uri}, "position": {"line": 4, "character": 11}})
        locs = r["result"] if isinstance(r["result"], list) else [r["result"]]
        assert any(l["uri"].startswith(URI + "src/util") for l in locs), locs
        # hover
        r = c.request("textDocument/hover", {"textDocument": {"uri": uri}, "position": {"line": 4, "character": 11}})
        assert "tambah" in str(r["result"])
        # referensi & ganti nama lintas file (header + sumber), petunjuk parameter
        # editor membuka file C/C++ proyek lainnya di LSP dulu (clangd tanpa background index hanya tahu file terbuka)
        for path, body in (("src/util.h", "#pragma once\nint tambah(int a, int b);\n"),
                           ("src/util.cpp", '#include "util.h"\nint tambah(int a, int b) { return a + b; }\n')):
            c.notify("textDocument/didOpen", {"textDocument": {"uri": URI + path, "languageId": "cpp", "version": 1,
                                                               "text": body}})
            c.wait_note("textDocument/publishDiagnostics", lambda m, p=path: m["params"]["uri"] == URI + p)
        r = c.request("textDocument/references", {"textDocument": {"uri": uri}, "position": {"line": 4, "character": 11},
                                                  "context": {"includeDeclaration": True}})
        files = {l["uri"] for l in r["result"]}
        assert uri in files and any(f.endswith("src/util.h") for f in files), files
        r = c.request("textDocument/rename", {"textDocument": {"uri": uri}, "position": {"line": 4, "character": 11},
                                              "newName": "jumlah"})
        changes = r["result"].get("changes") or {d["textDocument"]["uri"]: d["edits"] for d in r["result"]["documentChanges"]}
        assert uri in changes and all(e["newText"] == "jumlah" for es in changes.values() for e in es), changes
        assert all(u.startswith(URI) for u in changes), changes  # path asli disamarkan
        c.notify("textDocument/didChange", {"textDocument": {"uri": uri, "version": 3},
                                            "contentChanges": [{"text": text2.replace("tambah(1, 2)", "tambah(1, ")}]})
        r = c.request("textDocument/signatureHelp", {"textDocument": {"uri": uri}, "position": {"line": 4, "character": 20}})
        sig = r["result"]["signatures"][0]
        assert "tambah" in sig["label"] and r["result"].get("activeParameter", sig.get("activeParameter")) == 1, r
        c.shutdown()


@pytest.mark.skipif(not lsp_available("python"), reason="pyright tidak terpasang")
def test_pyright_diagnostics_and_completion(client, auth, token, project):
    put(client, auth, project, "lib/hitung.py", "def kuadrat(n: int) -> int:\n    return n * n\n")
    text = "from lib.hitung import kuadrat\nimport os\n\nhasil: str = kuadrat(3)\nos.pa\n"
    with client.websocket_connect(f"/ws/lsp?project_id={project}&language=python&token={token}") as ws:
        c = Client(ws)
        c.init()
        uri = URI + "main.py"
        c.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "python", "version": 1, "text": text}})
        diag = c.wait_note("textDocument/publishDiagnostics", lambda m: m["params"]["uri"] == uri and m["params"]["diagnostics"])
        msgs = " | ".join(d["message"] for d in diag["params"]["diagnostics"])
        assert "int" in msgs and "str" in msgs, msgs  # type mismatch terdeteksi
        r = c.request("textDocument/completion", {"textDocument": {"uri": uri}, "position": {"line": 4, "character": 5}})
        items = r["result"]["items"] if isinstance(r["result"], dict) else r["result"]
        assert "path" in {i["label"] for i in items}
        r = c.request("textDocument/definition", {"textDocument": {"uri": uri}, "position": {"line": 3, "character": 15}})
        locs = r["result"] if isinstance(r["result"], list) else [r["result"]]
        assert any(l.get("uri", l.get("targetUri", "")) == URI + "lib/hitung.py" for l in locs), locs
        r = c.request("textDocument/references", {"textDocument": {"uri": uri}, "position": {"line": 3, "character": 15},
                                                  "context": {"includeDeclaration": True}})
        assert any(l["uri"] == URI + "lib/hitung.py" for l in r["result"]), r
        r = c.request("textDocument/rename", {"textDocument": {"uri": uri}, "position": {"line": 3, "character": 15},
                                              "newName": "pangkat2"})
        res = r["result"]
        changes = res.get("changes") or {d["textDocument"]["uri"]: d["edits"] for d in res.get("documentChanges", [])
                                         if "textDocument" in d}
        assert URI + "lib/hitung.py" in changes and uri in changes, res
        c.shutdown()


CASES = [
    # (bahasa ws, languageId, path, isi, jenis uji, posisi/pesan, harapan)
    ("typescript", "typescript", "app.ts", 'const n: number = "x";\nMath.', "diag", None, "not assignable"),
    ("typescript", "typescript", "app.ts", "const s = 'abc';\nMath.", "complete", (1, 5), "max"),
    ("go", "go", "main.go", 'package main\n\nimport "fmt"\n\nfunc main() {\n\tfmt.\n}\n', "complete", (5, 5), "Println"),
    ("go", "go", "main.go", "package main\n\nfunc main() {\n\tx := 1\n\tprintln(y)\n}\n", "diag", None, "undefined"),
    ("php", "php", "index.php", "<?php\n$y = str_rep", "complete", (1, 12), "str_replace"),
    ("html", "html", "index.html", "<html><body><di", "complete", (0, 15), "div"),
    ("css", "css", "style.css", "a { colr: red; }\n", "diag", None, "Unknown property"),
    ("json", "json", "data.json", '{"a": }\n', "diag", None, "Value expected"),
    ("shell", "shellscript", "run.sh", "#!/bin/bash\nech", "complete", (1, 3), "echo"),
]


@pytest.mark.parametrize("lang,lang_id,path,text,kind,pos,expect", CASES, ids=[f"{c[0]}-{c[4]}" for c in CASES])
def test_more_language_servers(client, auth, token, project, lang, lang_id, path, text, kind, pos, expect):
    if not lsp_available(lang):
        pytest.skip(f"language server {lang} tidak terpasang")
    if lang == "go":
        put(client, auth, project, "go.mod", "module contoh\n\ngo 1.21\n")
    put(client, auth, project, path, text)
    with client.websocket_connect(f"/ws/lsp?project_id={project}&language={lang}&token={token}") as ws:
        c = Client(ws)
        c.init()
        uri = URI + path
        c.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": lang_id, "version": 1, "text": text}})
        if kind == "diag":
            d = c.wait_note("textDocument/publishDiagnostics", lambda m: m["params"]["uri"] == uri and m["params"]["diagnostics"])
            msgs = " | ".join(x["message"] for x in d["params"]["diagnostics"])
            assert expect.lower() in msgs.lower(), msgs
            assert "/home/" not in str(d), d
        else:
            labels = set()
            for _ in range(6):  # server butuh waktu memuat proyek/stdlib pertama kali
                r = c.request("textDocument/completion", {"textDocument": {"uri": uri}, "context": {"triggerKind": 1},
                                                          "position": {"line": pos[0], "character": pos[1]}})
                res = r.get("result") or []
                items = res.get("items", []) if isinstance(res, dict) else res
                labels = {i["label"].strip() for i in items}
                if any(expect in lab for lab in labels):
                    break
                time.sleep(1)
            assert any(expect in lab for lab in labels), sorted(labels)[:30]
        c.shutdown()


def test_lsp_rejects_bad_language(client, token, project):
    with client.websocket_connect(f"/ws/lsp?project_id={project}&language=cobol&token={token}") as ws:
        m = ws.receive_json()
        assert m["method"] == "cs/error" and m["params"]["code"] == "lsp_unavailable"
