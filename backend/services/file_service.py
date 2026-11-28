"""File manager yang terkunci di dalam folder proyek.

Mencegah path traversal (``..``, path absolut), symlink yang keluar dari proyek, dan
penulisan lewat symlink. Penulisan bersifat atomik (tmp + os.replace) dan setiap
perubahan/penghapusan disimpan ke riwayat sehingga bisa dibatalkan.
"""
from __future__ import annotations

import re
import fnmatch
import hashlib
import mimetypes
import os
import shutil
import stat
import time
import uuid
from pathlib import Path, PurePosixPath

from backend.config import Settings
from backend.core.exceptions import AppError, Conflict, NotFound, PathSecurityError
from backend.database.db import Database

TEXT_EXT = {
    ".py", ".js", ".mjs", ".cjs", ".ts", ".php", ".go", ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".java",
    ".cs", ".sql", ".html", ".htm", ".css", ".json", ".yaml", ".yml", ".xml", ".md", ".txt", ".sh", ".bash",
    ".http", ".csv", ".ini", ".toml", ".cfg", ".env", ".gitignore", ".mod", ".sum", ".csproj", ".kt", ".gradle",
}
LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".ts": "typescript",
    ".php": "php", ".go": "go", ".c": "c", ".h": "c", ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".java": "java", ".cs": "csharp", ".sql": "sql", ".html": "html", ".htm": "html", ".css": "css",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".xml": "xml", ".md": "markdown", ".sh": "shell",
    ".bash": "shell", ".http": "http", ".kt": "kotlin",
}
MAX_TREE_ENTRIES = 5000


def detect_language(path: str) -> str:
    return LANG_BY_EXT.get(PurePosixPath(path).suffix.lower(), "text")


class FileService:
    def __init__(self, settings: Settings, db: Database):
        self.s = settings
        self.db = db

    # ---------- keamanan path ----------
    @staticmethod
    def normalize(rel: str) -> str:
        if rel is None:
            rel = ""
        if "\x00" in rel:
            raise PathSecurityError("Path mengandung karakter terlarang")
        rel = rel.replace("\\", "/").strip()
        if rel.startswith("/"):
            rel = rel.lstrip("/")
        parts = []
        for part in rel.split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                raise PathSecurityError("Path traversal ('..') tidak diizinkan")
            parts.append(part)
        return "/".join(parts)

    def resolve(self, root: Path, rel: str, *, must_exist: bool = False, allow_root: bool = True,
                follow_last: bool = True) -> Path:
        """follow_last=False: komponen terakhir boleh symlink (untuk hapus/rename link itu sendiri)."""
        root = root.resolve()
        norm = self.normalize(rel)
        if not norm and not allow_root:
            raise PathSecurityError("Operasi pada folder akar proyek tidak diizinkan")
        target = root / norm if norm else root
        parts = PurePosixPath(norm).parts if norm else ()
        if not follow_last and parts:
            parent = self.resolve(root, "/".join(parts[:-1]), allow_root=True)
            target = parent / parts[-1]
            if must_exist and not target.exists() and not target.is_symlink():
                raise NotFound(f"'{norm}' tidak ditemukan")
            return target
        # Periksa setiap komponen: symlink tidak boleh mengarah keluar proyek.
        cur = root
        for part in parts:
            cur = cur / part
            if cur.is_symlink():
                real = cur.resolve()
                if real != root and root not in real.parents:
                    raise PathSecurityError("Symlink mengarah ke luar workspace")
        real = target.resolve()
        if real != root and root not in real.parents:
            raise PathSecurityError("Path berada di luar workspace")
        if must_exist and not target.exists() and not target.is_symlink():
            raise NotFound(f"'{norm or '/'}' tidak ditemukan")
        return target

    @staticmethod
    def rel_of(root: Path, p: Path) -> str:
        return str(p.relative_to(root)).replace(os.sep, "/") if p != root else ""

    # ---------- info ----------
    def info(self, root: Path, rel: str) -> dict:
        p = self.resolve(root, rel, must_exist=True)
        return self._entry(root, p)

    def _entry(self, root: Path, p: Path) -> dict:
        st = p.lstat()
        is_dir = stat.S_ISDIR(st.st_mode)
        rel = self.rel_of(root, p)
        return {
            "name": p.name if rel else "/",
            "path": rel,
            "type": "folder" if is_dir else ("symlink" if stat.S_ISLNK(st.st_mode) else "file"),
            "size": 0 if is_dir else st.st_size,
            "modified": st.st_mtime,
            "extension": "" if is_dir else p.suffix.lower(),
            "language": "" if is_dir else detect_language(p.name),
            "mime": None if is_dir else mimetypes.guess_type(p.name)[0],
        }

    def tree(self, root: Path, rel: str = "", depth: int = 1, show_hidden: bool = True) -> dict:
        base = self.resolve(root, rel, must_exist=True)
        if not base.is_dir():
            raise AppError("Bukan folder", code="not_a_folder")
        count = 0

        def walk(d: Path, level: int) -> list[dict]:
            nonlocal count
            items = []
            try:
                entries = sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            except OSError:
                return items
            for e in entries:
                if not show_hidden and e.name.startswith("."):
                    continue
                if e.name == ".git" and e.is_dir():
                    node = self._entry(root, e)
                    node["children"] = None
                    items.append(node)
                    continue
                count += 1
                if count > MAX_TREE_ENTRIES:
                    break
                node = self._entry(root, e)
                if node["type"] == "folder":
                    node["children"] = walk(e, level + 1) if level < depth else None
                items.append(node)
            return items

        node = self._entry(root, base)
        node["children"] = walk(base, 1)
        node["truncated"] = count > MAX_TREE_ENTRIES
        return node

    # ---------- baca/tulis ----------
    def read(self, root: Path, rel: str) -> dict:
        p = self.resolve(root, rel, must_exist=True)
        if p.is_dir():
            raise AppError("Tidak bisa membaca folder", code="is_folder")
        size = p.stat().st_size
        if size > self.s.max_file_size_bytes:
            raise AppError(f"File terlalu besar ({size} byte) untuk dibuka di editor", code="file_too_large")
        raw = p.read_bytes()
        info = self._entry(root, p)
        if b"\x00" in raw[:8192]:
            return {**info, "binary": True, "content": None, "sha256": hashlib.sha256(raw).hexdigest()}
        try:
            content = raw.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            content = raw.decode("latin-1")
            encoding = "latin-1"
        return {**info, "binary": False, "encoding": encoding, "content": content,
                "sha256": hashlib.sha256(raw).hexdigest()}

    def _snapshot(self, project_id: str, root: Path, p: Path, action: str, actor: dict | None, actor_type: str, note: str = "") -> None:
        if not p.is_file() or p.is_symlink() or p.stat().st_size > self.s.max_file_size_bytes:
            return
        data = p.read_bytes()
        d = self.s.history_dir / project_id
        d.mkdir(parents=True, exist_ok=True)
        name = uuid.uuid4().hex
        (d / name).write_bytes(data)
        self.db.execute(
            "INSERT INTO file_history(project_id, path, action, snapshot, sha256, size, actor_id, actor_type, note, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (project_id, self.rel_of(root, p), action, name, hashlib.sha256(data).hexdigest(), len(data),
             actor.get("id") if actor else None, actor_type, note, time.time()),
        )
        self._prune_history(project_id, self.rel_of(root, p))

    HISTORY_KEEP = 50  # versi per file (simpan otomatis editor membuat banyak versi)

    def _prune_history(self, project_id: str, rel: str) -> None:
        old = self.db.all("SELECT id, snapshot FROM file_history WHERE project_id=? AND path=? ORDER BY id DESC LIMIT -1 OFFSET ?",
                          (project_id, rel, self.HISTORY_KEEP))
        for r in old:
            try:
                (self.s.history_dir / project_id / r["snapshot"]).unlink(missing_ok=True)
            except OSError:
                pass
            self.db.execute("DELETE FROM file_history WHERE id=?", (r["id"],))

    def write(self, project_id: str, root: Path, rel: str, content: str, *, actor: dict | None = None,
              actor_type: str = "user", expected_sha256: str | None = None, create_only: bool = False, note: str = "") -> dict:
        p = self.resolve(root, rel, allow_root=False)
        data = content.encode("utf-8")
        if len(data) > self.s.max_file_size_bytes:
            raise AppError("Konten terlalu besar", code="file_too_large")
        if p.is_symlink():
            raise PathSecurityError("Tidak boleh menulis lewat symlink")
        if p.exists():
            if p.is_dir():
                raise Conflict("Sudah ada folder dengan nama itu")
            if create_only:
                raise Conflict("File sudah ada")
            if expected_sha256:
                current = hashlib.sha256(p.read_bytes()).hexdigest()
                if current != expected_sha256:
                    raise Conflict("File sudah diubah di tempat lain (konflik). Muat ulang dulu.", code="write_conflict",
                                   details={"current_sha256": current})
            self._snapshot(project_id, root, p, "write", actor, actor_type, note)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.parent / f".{p.name}.{uuid.uuid4().hex[:8]}.tmp"
        mode = p.stat().st_mode & 0o777 if p.exists() else 0o644
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)
        finally:
            if tmp.exists():
                tmp.unlink()
        return {**self._entry(root, p), "sha256": hashlib.sha256(data).hexdigest()}

    def create(self, project_id: str, root: Path, rel: str, kind: str, content: str = "", actor: dict | None = None) -> dict:
        if kind == "folder":
            p = self.resolve(root, rel, allow_root=False)
            if p.exists():
                raise Conflict("Sudah ada")
            p.mkdir(parents=True)
            return self._entry(root, p)
        return self.write(project_id, root, rel, content, actor=actor, create_only=True)

    def delete(self, project_id: str, root: Path, rel: str, recursive: bool = False, actor: dict | None = None, actor_type: str = "user") -> None:
        p = self.resolve(root, rel, must_exist=True, allow_root=False, follow_last=False)
        if p.is_symlink():
            p.unlink()
            return
        if p.is_dir():
            if any(p.iterdir()) and not recursive:
                raise Conflict("Folder tidak kosong; kirim recursive=true untuk menghapus isinya", code="folder_not_empty")
            for f in sorted(p.rglob("*")):
                if f.is_file() and not f.is_symlink():
                    self._snapshot(project_id, root, f, "delete", actor, actor_type)
            shutil.rmtree(p)
        else:
            self._snapshot(project_id, root, p, "delete", actor, actor_type)
            p.unlink()

    def rename(self, root: Path, rel: str, new_name: str) -> dict:
        if "/" in new_name or "\\" in new_name or new_name in ("", ".", ".."):
            raise PathSecurityError("Nama baru tidak valid")
        src = self.resolve(root, rel, must_exist=True, allow_root=False, follow_last=False)
        dst = self.resolve(root, self.rel_of(root, src.parent) + "/" + new_name, allow_root=False, follow_last=False)
        if dst.exists():
            raise Conflict("Nama tujuan sudah dipakai")
        src.rename(dst)
        return self._entry(root, dst)

    def move(self, root: Path, rel: str, dest_rel: str, copy: bool = False, overwrite: bool = False) -> dict:
        src = self.resolve(root, rel, must_exist=True, allow_root=False)
        dst = self.resolve(root, dest_rel, allow_root=True)
        if dst.is_dir():
            dst = dst / src.name
            dst = self.resolve(root, self.rel_of(root, dst))
        if src.is_dir() and (dst == src or src in dst.parents):
            raise Conflict("Tidak bisa memindah folder ke dalam dirinya sendiri")
        if dst.exists():
            if not overwrite:
                raise Conflict("Tujuan sudah ada")
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        if copy:
            if src.is_dir():
                shutil.copytree(src, dst, symlinks=True)
            else:
                shutil.copy2(src, dst, follow_symlinks=False)
        else:
            shutil.move(str(src), str(dst))
        return self._entry(root, dst)

    LIST_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache", "build",
                      ".gradle", ".cs_build", ".cs-build"}

    def list_files(self, root: Path, limit: int = 5000) -> dict:
        """Semua file proyek (path relatif) untuk Buka file cepat. Symlink tidak diikuti."""
        out: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in self.LIST_SKIP_DIRS and not (Path(dirpath) / d).is_symlink())
            for name in sorted(filenames):
                out.append(self.rel_of(root, Path(dirpath) / name))
                if len(out) >= limit:
                    return {"files": out, "truncated": True}
        return {"files": out, "truncated": False}

    # ---------- cari & ganti di seluruh proyek ----------
    @staticmethod
    def _pattern(query: str, regex: bool, case_sensitive: bool, whole_word: bool) -> "re.Pattern[str]":
        if not query or len(query) > 500:
            raise AppError("Kata kunci kosong atau terlalu panjang", code="bad_query")
        src = query if regex else re.escape(query)
        if whole_word:
            src = rf"(?<![\w]){src}(?![\w])"
        try:
            return re.compile(src, 0 if case_sensitive else re.IGNORECASE)
        except re.error as e:
            raise AppError(f"Regex tidak valid: {e}", code="bad_regex")

    def _text_files(self, root: Path, paths: list[str] | None = None):
        if paths is not None:
            for rel in paths:
                p = self.resolve(root, rel, allow_root=False)
                if p.is_file() and not p.is_symlink():
                    yield p
            return
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in self.LIST_SKIP_DIRS and not (Path(dirpath) / d).is_symlink())
            for name in sorted(filenames):
                p = Path(dirpath) / name
                if p.is_symlink() or p.suffix.lower() not in TEXT_EXT and name not in ("Makefile", "Dockerfile", "CMakeLists.txt"):
                    continue
                if p.stat().st_size < 2_000_000:
                    yield p

    def grep(self, root: Path, query: str, *, regex: bool = False, case_sensitive: bool = False, whole_word: bool = False,
             limit: int = 1000) -> dict:
        pat = self._pattern(query, regex, case_sensitive, whole_word)
        matches: list[dict] = []
        files = 0
        for p in self._text_files(root):
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            hit = False
            for i, line in enumerate(text.splitlines(), 1):
                for m in pat.finditer(line):
                    if m.end() == m.start():
                        continue
                    hit = True
                    matches.append({"path": self.rel_of(root, p), "line": i, "column": m.start() + 1,
                                    "length": m.end() - m.start(), "text": line.strip()[:300],
                                    "offset": len(line) - len(line.lstrip())})
                    if len(matches) >= limit:
                        return {"matches": matches, "files": files + 1, "truncated": True}
            files += hit
        return {"matches": matches, "files": files, "truncated": False}

    def replace_all(self, project_id: str, root: Path, query: str, replacement: str, *, regex: bool = False,
                    case_sensitive: bool = False, whole_word: bool = False, paths: list[str] | None = None,
                    actor: dict | None = None) -> dict:
        pat = self._pattern(query, regex, case_sensitive, whole_word)
        changed: list[dict] = []
        total = 0
        for p in self._text_files(root, paths):
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            try:
                new, n = pat.subn(replacement if regex else (lambda _m: replacement), text)
            except (re.error, IndexError) as e:
                raise AppError(f"Pengganti tidak valid: {e}", code="bad_regex")
            if n and new != text:
                rel = self.rel_of(root, p)
                self.write(project_id, root, rel, new, actor=actor, note=f"ganti semua: {query[:60]}")
                changed.append({"path": rel, "count": n})
                total += n
        return {"files": changed, "total": total}

    def search(self, root: Path, query: str, *, content: bool = False, path: str = "", limit: int = 200) -> list[dict]:
        base = self.resolve(root, path, must_exist=True)
        q = query.lower()
        pattern = query if any(c in query for c in "*?[") else None
        results: list[dict] = []
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__")]
            dp = Path(dirpath)
            for name in dirnames + filenames:
                full = dp / name
                if content:
                    # Jangan pernah membaca lewat symlink: link bisa menunjuk ke luar proyek
                    # (mis. ~/.ssh/id_rsa) dan isinya akan bocor lewat hasil pencarian.
                    if full.is_symlink():
                        continue
                    if name in filenames and full.suffix.lower() in TEXT_EXT and full.stat().st_size < 2_000_000:
                        try:
                            for i, line in enumerate(full.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                                if q in line.lower():
                                    results.append({**self._entry(root, full), "line": i, "text": line.strip()[:300]})
                                    if len(results) >= limit:
                                        return results
                        except OSError:
                            pass
                else:
                    hit = fnmatch.fnmatch(name.lower(), pattern.lower()) if pattern else q in name.lower()
                    if hit:
                        results.append(self._entry(root, full))
                        if len(results) >= limit:
                            return results
        return results

    # ---------- riwayat (undo) ----------
    def history(self, project_id: str, rel: str | None = None, limit: int = 100) -> list[dict]:
        if rel:
            return self.db.all(
                "SELECT id, path, action, sha256, size, actor_id, actor_type, note, created_at FROM file_history "
                "WHERE project_id=? AND path=? ORDER BY id DESC LIMIT ?", (project_id, self.normalize(rel), limit))
        return self.db.all(
            "SELECT id, path, action, sha256, size, actor_id, actor_type, note, created_at FROM file_history "
            "WHERE project_id=? ORDER BY id DESC LIMIT ?", (project_id, limit))

    def history_content(self, project_id: str, history_id: int) -> tuple[dict, str]:
        row = self.db.one("SELECT * FROM file_history WHERE id=? AND project_id=?", (history_id, project_id))
        if not row or not row["snapshot"]:
            raise NotFound("Versi tidak ditemukan")
        data = (self.s.history_dir / project_id / row["snapshot"]).read_bytes()
        return row, data.decode("utf-8", errors="replace")

    def restore(self, project_id: str, root: Path, history_id: int, actor: dict | None) -> dict:
        row, content = self.history_content(project_id, history_id)
        return self.write(project_id, root, row["path"], content, actor=actor, note=f"restore dari versi #{history_id}")
