"""Engine C (dan dasar C++): satu file, multi-file otomatis, Makefile, atau CMake.

Urutan deteksi untuk file yang dijalankan (mencari dari folder file ke atas, maksimal sampai akar proyek):
1. CMakeLists.txt -> cmake (Ninja bila ada) + cmake --build; dijalankan: executable terbaru di build dir.
2. Makefile/makefile/GNUmakefile -> make; dijalankan: `make run` bila target `run:` ada, selain itu
   executable terbaru di folder Makefile.
3. Tanpa keduanya: semua file sumber (sebahasa) di folder file + subfolder dikompilasi bersama.
   File lain yang juga punya main() diabaikan (folder latihan berisi banyak program tetap jalan);
   bila file yang dibuka tidak punya main(), dipakai satu-satunya file yang punya main().
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from backend.core.exceptions import AppError
from backend.engines.base_engine import BaseEngine, EngineContext, Step, find_executable

MAKEFILES = ("GNUmakefile", "makefile", "Makefile")
SKIP_DIRS = {"build", "out", "bin", "obj", ".git", "node_modules", "CMakeFiles", "__pycache__", ".cs_build"}
MAX_SOURCES = 300
_MAIN = re.compile(r"^[ \t]*(?:(?:static|extern|inline|signed|unsigned)\s+)*(?:int|void|auto)\s+main\s*\(", re.M)
_COMMENTS = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def has_main(p: Path) -> bool:
    try:
        text = p.read_text(errors="replace")
    except OSError:
        return False
    return bool(_MAIN.search(_COMMENTS.sub("", text)))


def _find_up(start: Path, root: Path, names: tuple[str, ...]) -> Path | None:
    d = start
    while True:
        for n in names:
            if (d / n).is_file():
                return d / n
        if d == root or root not in d.parents:
            return None
        d = d.parent


def _newest_executable(d: Path, exclude: tuple[str, ...] = ("CMakeFiles",)) -> Path | None:
    best: tuple[float, Path] | None = None
    if not d.is_dir():
        return None
    for p in d.rglob("*"):
        if any(part in exclude or part.startswith(".") for part in p.relative_to(d).parts[:-1]):
            continue
        if not p.is_file() or p.is_symlink() or p.suffix in (".o", ".a", ".so", ".sh", ".py", ".txt", ".cmake", ".d"):
            continue
        if not os.access(p, os.X_OK):
            continue
        try:
            with p.open("rb") as f:
                if f.read(4) != b"\x7fELF":
                    continue
        except OSError:
            continue
        m = p.stat().st_mtime
        if best is None or m > best[0]:
            best = (m, p)
    return best[1] if best else None


class CEngine(BaseEngine):
    language_id = "c"
    name = "C (GCC)"
    extensions = (".c",)
    source_exts = (".c",)
    executables = ("gcc", "cc")
    compiler_flags = ("-std=c17", "-O2", "-Wall", "-Wextra")
    link_flags = ("-lm",)
    address_space_limit = True

    # ---------- deteksi mode ----------
    def mode(self, ctx: EngineContext) -> tuple[str, Path]:
        """('cmake', CMakeLists dir) | ('make', Makefile) | ('files', folder)."""
        start = ctx.file.parent
        cm = _find_up(start, ctx.project_dir, ("CMakeLists.txt",))
        mk = _find_up(start, ctx.project_dir, MAKEFILES)
        # pilih yang paling dekat dengan file; bila sama dekatnya, CMake didahulukan
        if cm and (not mk or len(cm.parent.parts) >= len(mk.parent.parts)):
            # CMakeLists di subfolder milik proyek induk: naik ke CMakeLists teratas
            top = cm.parent
            while top != ctx.project_dir and (top.parent / "CMakeLists.txt").is_file():
                top = top.parent
            return "cmake", top
        if mk:
            return "make", mk
        return "files", start

    def prepare_context(self, ctx: EngineContext) -> EngineContext:
        kind, where = self.mode(ctx)
        if kind == "cmake":
            key = hashlib.sha1(str(where).encode()).hexdigest()[:10]
            ctx.build_dir = ctx.build_dir.parent / f"_cmake_{key}"
        return ctx

    def _scan(self, root: Path) -> list[Path]:
        found: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith((".", "cmake-build")))
            for fn in sorted(filenames):
                if fn.endswith(self.source_exts):
                    found.append(Path(dirpath) / fn)
                    if len(found) > MAX_SOURCES:
                        raise AppError(f"Terlalu banyak file sumber (> {MAX_SOURCES}); pakai Makefile/CMake", code="too_many_sources")
        return found

    def source_root(self, ctx: EngineContext) -> Path:
        """Folder sumber: folder file; bila file tanpa main() dan foldernya juga tanpa main(), naik ke induk
        (maks. akar proyek) sampai ketemu folder yang punya main()."""
        root = ctx.file.parent
        if has_main(ctx.file):
            return root
        d = root
        while True:
            if any(has_main(p) for p in self._scan(d)):
                return d
            if d == ctx.project_dir or ctx.project_dir not in d.parents:
                return root
            d = d.parent

    def sources(self, ctx: EngineContext) -> list[Path]:
        """File sumber yang dikompilasi bersama dalam mode multi-file otomatis."""
        root = self.source_root(ctx)
        found = self._scan(root)
        if ctx.file not in found:
            found.insert(0, ctx.file)
        if len(found) == 1:
            return found
        mains = [p for p in found if has_main(p)]
        others = [p for p in found if p not in mains]
        if ctx.file in mains:
            return [ctx.file, *others]
        if len(mains) == 1:
            return [mains[0], *others]
        if not mains:
            return found  # tanpa main: build = cek kompilasi; run akan gagal di linker dengan pesan jelas
        names = ", ".join(str(p.relative_to(root)) for p in mains[:6])
        raise AppError(f"Ada beberapa main() ({names}). Buka file yang berisi main() yang ingin dijalankan.",
                       code="multiple_mains")

    def include_flags(self, ctx: EngineContext) -> list[str]:
        root = self.source_root(ctx)
        flags = [f"-I{root}"]
        for name in ("include", "inc"):
            if (root / name).is_dir():
                flags.append(f"-I{root / name}")
        return flags

    # ---------- langkah ----------
    def _make(self) -> str:
        exe = find_executable("make", "gmake")
        if not exe:
            raise AppError("make belum terpasang di server (sudo apt install make)", code="engine_unavailable", status_code=503)
        return exe

    def _cmake(self) -> str:
        exe = find_executable("cmake")
        if not exe:
            raise AppError("cmake belum terpasang di server (sudo apt install cmake)", code="engine_unavailable", status_code=503)
        return exe

    def build_steps(self, ctx: EngineContext) -> list[Step]:
        kind, where = self.mode(ctx)
        jobs = f"-j{max(1, min(os.cpu_count() or 2, 4) // 2)}"
        if kind == "cmake":
            cmake = self._cmake()
            gen = ["-G", "Ninja"] if find_executable("ninja") else []
            cfg = [cmake, "-S", str(where), "-B", str(ctx.build_dir), *gen,
                   "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]
            return [self.step("build", cfg, ctx, cwd=where),
                    self.step("build", [cmake, "--build", str(ctx.build_dir), jobs], ctx, cwd=where)]
        if kind == "make":
            return [self.step("build", [self._make(), "-C", str(where.parent), "-f", where.name, jobs], ctx, cwd=where.parent)]
        exe = self.require()
        srcs = [str(p) for p in self.sources(ctx)]
        out = str(ctx.build_dir / "app")
        return [self.step("build", [exe, *self.compiler_flags, *self.include_flags(ctx), "-o", out, *srcs, *self.link_flags], ctx)]

    def run_steps(self, ctx: EngineContext) -> list[Step]:
        kind, where = self.mode(ctx)
        steps = self.build_steps(ctx)
        if kind == "cmake":
            def resolve() -> list[str]:
                exe = _newest_executable(ctx.build_dir)
                if not exe:
                    raise AppError("Build CMake selesai tapi tidak ada executable (cek add_executable di CMakeLists.txt)",
                                   code="no_executable")
                return [str(exe), *ctx.args]
            run = self.step("run", ["<executable hasil cmake>"], ctx, cwd=where)
            run.resolve = resolve
            return steps + [run]
        if kind == "make":
            mk_dir = where.parent
            if re.search(r"^run\s*:", where.read_text(errors="replace"), re.M):
                argv = [self._make(), "-s", "-C", str(mk_dir), "-f", where.name, "run"]
                if ctx.args:
                    argv.append("ARGS=" + " ".join(ctx.args))
                return steps + [self.step("run", argv, ctx, cwd=mk_dir)]

            def resolve() -> list[str]:
                exe = _newest_executable(mk_dir, exclude=("CMakeFiles", "obj"))
                if not exe:
                    raise AppError("make selesai tapi executable tidak ditemukan; tambahkan target `run:` di Makefile",
                                   code="no_executable")
                return [str(exe), *ctx.args]
            run = self.step("run", ["<executable hasil make>"], ctx, cwd=mk_dir)
            run.resolve = resolve
            return steps + [run]
        return steps + [self.step("run", [str(ctx.build_dir / "app"), *ctx.args], ctx)]
