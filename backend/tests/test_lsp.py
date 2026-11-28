"""Language server nyata (clangd/pyright) lewat /ws/lsp di sandbox. Dilewati bila servernya tidak terpasang."""
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
        c.shutdown()


def test_lsp_rejects_bad_language(client, token, project):
    with client.websocket_connect(f"/ws/lsp?project_id={project}&language=cobol&token={token}") as ws:
        m = ws.receive_json()
        assert m["method"] == "cs/error" and m["params"]["code"] == "lsp_unavailable"
