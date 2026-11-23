"""Ekstrak perubahan file dari jawaban AI dan terapkan ke isi file.

Format yang diminta ke model (lihat EDIT_PROTOCOL):

1. Ganti/buat file utuh:
       ```python file=src/main.py
       ...isi lengkap...
       ```
2. Ubah sebagian (lebih hemat token, cocok untuk file besar):
       ```edit file=src/main.py
       <<<<<<< SEARCH
       baris lama persis
       =======
       baris baru
       >>>>>>> REPLACE
       ```

Model lokal kecil sering tidak patuh 100 %, jadi parser juga menerima `path=`, `file:`, dan judul
seperti "File: src/main.py" atau "### `src/main.py`" tepat di atas blok kode. Blok tanpa nama file
diabaikan (dianggap contoh/penjelasan, bukan editan).
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

EDIT_PROTOCOL = """
ATURAN MENGUBAH FILE PROYEK (wajib diikuti bila kamu memperbaiki/mengubah/membuat file):
- Tulis perubahan sebagai blok kode dengan atribut file=PATH (path relatif dari akar proyek, persis seperti judul file konteks).
- Perubahan kecil pada file yang sudah ada: pakai blok `edit` berisi satu atau lebih SEARCH/REPLACE:
```edit file=src/contoh.py
<<<<<<< SEARCH
baris lama yang PERSIS ada di file (cukup beberapa baris yang unik)
=======
baris pengganti
>>>>>>> REPLACE
```
- File baru atau perubahan besar: tulis isi file LENGKAP: ```python file=src/baru.py ... ```
- Jangan pernah menyingkat isi dengan "..." atau "kode lain tetap sama" di dalam blok file=.
- Blok kode tanpa file= dianggap contoh saja dan tidak akan diterapkan.
""".strip()

_FENCE = re.compile(r"^(?P<indent>[ \t]{0,3})(?P<ticks>`{3,}|~{3,})(?P<info>[^\n`]*)\n(?P<body>.*?)^(?P=indent)(?P=ticks)[ \t]*$",
                    re.M | re.S)
_ATTR = re.compile(r"""(?:^|\s)(?:file|path|filename)\s*[=:]\s*["']?([^\s"']+)["']?""", re.I)
_HEADING = re.compile(r"""(?:file|berkas|path)\s*[:=]\s*`?([\w./\\-]+\.\w+)`?\s*\**\s*:?\s*$|^#{1,6}\s*`?([\w./\\-]+\.\w+)`?\s*:?\s*$|^\**`([\w./\\-]+\.\w+)`\**\s*:?\s*$""",
                      re.I)
_SR = re.compile(r"^<{5,9} ?SEARCH[^\n]*\n(?P<search>.*?)^={5,9}[ \t]*\n(?P<replace>.*?)^>{5,9} ?REPLACE[^\n]*$", re.M | re.S)
_LAZY = re.compile(r"^\s*(#|//|/\*|<!--|--)?\s*\.{3}\s*(?:(kode|code|sisa|rest|existing|lainnya|yang lain|unchanged)[^\n]*)?$|"
                   r"(tetap sama|tidak berubah|rest of (the )?(code|file)|existing code)", re.I | re.M)


@dataclass
class Edit:
    path: str
    kind: str                     # "full" | "replace"
    content: str = ""             # untuk full
    blocks: list[tuple[str, str]] = field(default_factory=list)  # untuk replace: (search, replace)


def _path_from_heading(text_before: str) -> str | None:
    lines = [l.strip() for l in text_before.rstrip().splitlines() if l.strip()]
    if not lines:
        return None
    m = _HEADING.search(lines[-1])
    if not m:
        return None
    return next(g for g in m.groups() if g)


def parse_edits(answer: str) -> list[Edit]:
    """Temukan blok kode yang ditujukan ke file tertentu. Editan ke file yang sama digabung berurutan."""
    out: list[Edit] = []
    last_end = 0
    for m in _FENCE.finditer(answer):
        info, body = m.group("info").strip(), m.group("body")
        before = answer[last_end:m.start()]
        last_end = m.end()
        am = _ATTR.search(info)
        path = am.group(1) if am else _path_from_heading(before)
        if not path:
            continue
        path = path.replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        blocks = [(b.group("search"), b.group("replace")) for b in _SR.finditer(body)]
        if blocks:
            out.append(Edit(path, "replace", blocks=blocks))
        elif info.split()[:1] == ["edit"] or "<<<<<<<" in body:
            continue  # blok edit rusak: lebih aman diabaikan daripada menimpa file
        else:
            out.append(Edit(path, "full", content=body))
    return out


class EditError(Exception):
    pass


def _norm(line: str) -> str:
    return line.rstrip()


def _find_block(lines: list[str], search: list[str], strip_indent: bool) -> int:
    """Indeks awal search di lines (-1 bila tidak ada, -2 bila lebih dari satu kecocokan)."""
    key = (lambda l: _norm(l).strip()) if strip_indent else _norm
    target = [key(l) for l in search]
    n = len(target)
    hits = [i for i in range(len(lines) - n + 1) if [key(l) for l in lines[i:i + n]] == target]
    if not hits:
        return -1
    return hits[0] if len(hits) == 1 else -2


def apply_replace(original: str, blocks: list[tuple[str, str]]) -> str:
    """Terapkan SEARCH/REPLACE berurutan. Toleran terhadap spasi di akhir baris dan indentasi."""
    text = original
    for idx, (search, replace) in enumerate(blocks, 1):
        if not search.strip():
            # SEARCH kosong = tambahkan di akhir file (pola umum untuk file baru/sisipan)
            text = text + ("" if not text or text.endswith("\n") else "\n") + replace
            continue
        if search in text:
            if text.count(search) > 1:
                raise EditError(f"Blok #{idx}: teks SEARCH muncul lebih dari sekali, perlu konteks lebih unik")
            text = text.replace(search, replace, 1)
            continue
        lines = text.splitlines(keepends=True)
        s_lines = search.splitlines()
        r_lines = replace.splitlines()
        for strip_indent in (False, True):
            i = _find_block(lines, s_lines, strip_indent)
            if i == -2:
                raise EditError(f"Blok #{idx}: teks SEARCH muncul lebih dari sekali, perlu konteks lebih unik")
            if i >= 0:
                if strip_indent:  # samakan indentasi dengan file asli
                    def ind(l: str) -> str:
                        return l[:len(l) - len(l.lstrip())]
                    delta_src, delta_dst = ind(s_lines[0]), ind(lines[i].rstrip("\r\n"))
                    r_lines = [delta_dst + l[len(delta_src):] if l.startswith(delta_src) else l for l in r_lines]
                eol = "\r\n" if lines[i].endswith("\r\n") else "\n"
                tail_eol = lines[i + len(s_lines) - 1].endswith(("\n", "\r"))
                new = "".join(l + eol for l in r_lines)
                if not tail_eol and new.endswith(eol):
                    new = new[: -len(eol)]
                lines[i:i + len(s_lines)] = [new]
                text = "".join(lines)
                break
        else:
            first = s_lines[0].strip()[:60] if s_lines else ""
            raise EditError(f"Blok #{idx}: teks SEARCH tidak ditemukan di file (\"{first}\")")
    return text


def looks_truncated(content: str) -> bool:
    """Isi file 'lengkap' yang ternyata disingkat model ('... kode lain tetap sama')."""
    return bool(_LAZY.search(content))


def unified_diff(path: str, old: str, new: str, max_lines: int = 400) -> tuple[str, int, int]:
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), f"a/{path}", f"b/{path}", lineterm="", n=2))
    adds = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    dels = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"... ({len(lines) - max_lines} baris diff lagi)"]
    return "\n".join(lines), adds, dels
