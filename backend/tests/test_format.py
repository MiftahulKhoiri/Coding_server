"""Format kode di sandbox: clang-format, ruff, prettier, gofmt (dilewati bila formatter tidak terpasang)."""
import pytest

from backend.config import get_settings
from backend.services.format_service import FormatService

ST = FormatService(get_settings()).status()


def fmt(client, auth, project, path, content, tab=4):
    return client.post("/api/v1/files/format", json={"project_id": project, "path": path, "content": content,
                                                      "tab_size": tab}, headers=auth)


@pytest.mark.skipif(not ST["clang-format"], reason="clang-format tidak terpasang")
def test_format_cpp_default_and_project_style(client, auth, project):
    r = fmt(client, auth, project, "src/main.cpp", "int main(){int x=1;if(x){return 0;}return 1;}\n")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["formatter"] == "clang-format" and out["changed"] is True
    assert "int main() {\n    int x = 1;" in out["content"], out["content"]
    # gaya milik proyek (.clang-format) dihormati: IndentWidth 2
    client.put("/api/v1/files/write", json={"project_id": project, "path": ".clang-format",
                                            "content": "BasedOnStyle: LLVM\nIndentWidth: 2\n"}, headers=auth)
    out = fmt(client, auth, project, "src/main.cpp", "int main(){int x=1;return x;}\n").json()
    assert "int main() {\n  int x = 1;" in out["content"], out["content"]


@pytest.mark.skipif(not ST["ruff"], reason="ruff tidak terpasang")
def test_format_python_and_syntax_error(client, auth, project):
    r = fmt(client, auth, project, "a.py", "x=[1,2 ,3]\ndef f( a ):\n  return a\n")
    assert r.status_code == 200, r.text
    assert r.json()["content"] == "x = [1, 2, 3]\n\n\ndef f(a):\n    return a\n"
    bad = fmt(client, auth, project, "a.py", "def f(:\n")
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "format_failed"
    assert "/home/" not in bad.json()["error"]["message"]  # path asli disamarkan


@pytest.mark.skipif(not ST["prettier"], reason="prettier tidak terpasang")
def test_format_js_json(client, auth, project):
    out = fmt(client, auth, project, "web/app.js", "const a={b:1,c:[1,2]};function f(){return a}\n", tab=2).json()
    assert out["content"] == "const a = { b: 1, c: [1, 2] };\nfunction f() {\n  return a;\n}\n", out
    out = fmt(client, auth, project, "data.json", '{"a":1,"b":[true,null]}').json()
    assert out["content"] == '{ "a": 1, "b": [true, null] }\n', out


@pytest.mark.skipif(not ST["gofmt"], reason="gofmt tidak terpasang")
def test_format_go(client, auth, project):
    out = fmt(client, auth, project, "main.go", "package main\nfunc main(){\nprintln(1)\n}\n").json()
    assert out["content"] == "package main\n\nfunc main() {\n\tprintln(1)\n}\n", out


def test_format_unsupported_and_traversal(client, auth, project):
    r = fmt(client, auth, project, "notes.txt", "x")
    assert r.status_code == 400 and r.json()["error"]["code"] == "formatter_unsupported"
    assert fmt(client, auth, project, "../../etc/x.py", "x").status_code in (400, 403)
