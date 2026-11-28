"""Format kode untuk editor: clang-format (C/C++/Java/C#), ruff (Python), prettier (JS/TS/CSS/HTML/JSON/YAML/MD), gofmt.

Formatter membaca isi dari stdin dan menulis hasil ke stdout; tidak ada file yang ditulis. Proses dijalankan di
sandbox bubblewrap (proyek read-only, tanpa jaringan) karena konfigurasi proyek (mis. .prettierrc.js) bisa berisi kode.
Konfigurasi gaya milik proyek (.clang-format, pyproject.toml/ruff.toml, .prettierrc, …) dihormati; bila tidak ada,
dipakai gaya bawaan dengan lebar indentasi editor.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from backend.config import Settings
from backend.core.exceptions import AppError
from backend.core.logging import get_logger
from backend.core.sandbox import Limits, SandboxSpec, make_preexec, wrap

log = get_logger("format")

CLANG_EXT = {".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".java", ".cs", ".proto"}
PRETTIER_EXT = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".json", ".css", ".scss", ".less", ".html", ".htm",
                ".vue", ".yaml", ".yml", ".md", ".markdown", ".graphql"}
PY_EXT = {".py", ".pyi"}
GO_EXT = {".go"}
CLANG_STYLE_FILES = (".clang-format", "_clang-format")
PRETTIER_CONFIGS = (".prettierrc", ".prettierrc.json", ".prettierrc.yaml", ".prettierrc.yml", ".prettierrc.json5",
                    ".prettierrc.js", ".prettierrc.cjs", ".prettierrc.mjs", ".prettierrc.toml", "prettier.config.js",
                    "prettier.config.cjs", "prettier.config.mjs")
MAX_INPUT = 2 * 1024 * 1024
TIMEOUT = 25


@dataclass
class Tool:
    name: str
    argv: list[str]
    readonly: list[Path]


class FormatService:
    def __init__(self, settings: Settings):
        self.s = settings

    # ---------- lokasi formatter ----------
    def _venv(self) -> Path:
        return self.s.base_dir / ".venv"

    def _clang_format(self) -> Path | None:
        pyver = f"python{sys.version_info.major}.{sys.version_info.minor}"
        cand = self._venv() / "lib" / pyver / "site-packages" / "clang_format" / "data" / "bin" / "clang-format"
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
        exe = shutil.which("clang-format")
        return Path(os.path.realpath(exe)) if exe else None

    def _ruff(self) -> Path | None:
        cand = self._venv() / "bin" / "ruff"
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
        exe = shutil.which("ruff")
        return Path(os.path.realpath(exe)) if exe else None

    def _prettier(self) -> tuple[Path, Path] | None:
        node = shutil.which("node")
        js = self.s.base_dir / ".lsp" / "node_modules" / "prettier" / "bin" / "prettier.cjs"
        return (Path(os.path.realpath(node)), js) if node and js.is_file() else None

    @staticmethod
    def _gofmt() -> Path | None:
        exe = shutil.which("gofmt") or ("/usr/lib/go/bin/gofmt" if Path("/usr/lib/go/bin/gofmt").is_file() else None)
        return Path(os.path.realpath(exe)) if exe else None

    def status(self) -> dict:
        return {"clang-format": self._clang_format() is not None, "ruff": self._ruff() is not None,
                "prettier": self._prettier() is not None, "gofmt": self._gofmt() is not None,
                "extensions": sorted(CLANG_EXT | PRETTIER_EXT | PY_EXT | GO_EXT)}

    # ---------- pemilihan ----------
    @staticmethod
    def _has_config(root: Path, file: Path, names: tuple[str, ...]) -> bool:
        d = file.parent
        while True:
            if any((d / n).is_file() for n in names):
                return True
            if d == root or root not in d.parents:
                return False
            d = d.parent

    def _tool(self, root: Path, file: Path, tab_size: int) -> Tool:
        ext = file.suffix.lower()
        ro = [root]
        if ext in CLANG_EXT:
            exe = self._clang_format()
            if not exe:
                raise AppError("clang-format belum terpasang (jalankan scripts/install_runtimes.sh)", code="formatter_missing")
            style = ("file" if self._has_config(root, file, CLANG_STYLE_FILES)
                     else "{BasedOnStyle: LLVM, IndentWidth: %d, ColumnLimit: 100, AllowShortFunctionsOnASingleLine: Empty}"
                     % tab_size)
            return Tool("clang-format", [str(exe), f"--style={style}", f"--assume-filename={file}"],
                        ro + [exe.parent.parent.parent])
        if ext in PY_EXT:
            exe = self._ruff()
            if not exe:
                raise AppError("ruff belum terpasang (jalankan scripts/install_runtimes.sh)", code="formatter_missing")
            return Tool("ruff", [str(exe), "format", "--no-cache", "--stdin-filename", str(file), "-"], ro + [exe.parent.parent])
        if ext in PRETTIER_EXT:
            found = self._prettier()
            if not found:
                raise AppError("prettier belum terpasang (jalankan scripts/install_runtimes.sh)", code="formatter_missing")
            node, js = found
            argv = [str(node), str(js), "--stdin-filepath", str(file)]
            if not self._has_config(root, file, PRETTIER_CONFIGS):
                argv += ["--tab-width", str(tab_size)]
            return Tool("prettier", argv, ro + [self.s.base_dir / ".lsp"])
        if ext in GO_EXT:
            exe = self._gofmt()
            if not exe:
                raise AppError("gofmt belum terpasang (sudo apt install golang)", code="formatter_missing")
            return Tool("gofmt", [str(exe)], ro)
        raise AppError(f"Belum ada formatter untuk file {ext or file.name}", code="formatter_unsupported")

    # ---------- jalankan ----------
    async def format(self, root: Path, file: Path, content: str, tab_size: int = 4) -> dict:
        data = content.encode("utf-8")
        if len(data) > MAX_INPUT:
            raise AppError("File terlalu besar untuk diformat", code="file_too_large")
        tab_size = max(1, min(8, int(tab_size or 4)))
        tool = self._tool(root, file, tab_size)
        home = Path.home()
        # Hanya folder di $HOME yang perlu diikat (sistem /usr sudah read-only di sandbox); jangan pernah mengikat "/".
        tool.readonly = [p for p in tool.readonly if p == root or home in p.parents]
        cache = self.s.cache_dir / "format"
        cache.mkdir(parents=True, exist_ok=True)
        spec = SandboxSpec(cwd=file.parent if file.parent.is_dir() else root, writable=[cache],
                           readonly=[p for p in tool.readonly if p.exists()], network=False,
                           env={"HOME": str(cache), "XDG_CACHE_HOME": str(cache), "NO_COLOR": "1"})
        argv, env = wrap(tool.argv, spec, enabled=self.s.sandbox_enabled)
        limits = Limits(timeout=TIMEOUT, memory_mb=768, address_space_limit=False, cpu_seconds=TIMEOUT * 2, nice=5)
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=env, cwd=str(root), preexec_fn=make_preexec(limits))
        try:
            out, err = await asyncio.wait_for(proc.communicate(data), TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise AppError(f"{tool.name} terlalu lama (> {TIMEOUT} dtk)", code="formatter_timeout")
        if proc.returncode != 0:
            msg = (err or out).decode("utf-8", "replace").strip()
            msg = msg.replace(str(root) + "/", "").replace(str(root), ".")[-1500:]
            raise AppError(f"{tool.name} gagal: {msg or 'kode keluar ' + str(proc.returncode)}", code="format_failed")
        result = out.decode("utf-8", "replace")
        return {"content": result, "changed": result != content, "formatter": tool.name}
