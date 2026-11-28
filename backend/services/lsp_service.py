"""Language Server Protocol (LSP) untuk editor: clangd (C/C++), pyright (Python), typescript-language-server
(JavaScript/TypeScript), gopls (Go), intelephense (PHP), vscode-html/css/json-language-server, bash-language-server.

Satu proses language server per koneksi WebSocket (/ws/lsp), dijalankan di sandbox bubblewrap:
folder proyek READ-ONLY, jaringan diputus, $HOME kosong. Proxy ini:
* membingkai pesan JSON-RPC (Content-Length) <-> pesan WebSocket (satu JSON per pesan);
* menyamarkan path asli: klien memakai file:///workspace/..., server melihat path proyek sebenarnya;
* melengkapi `initialize` (rootUri, workspaceFolders, opsi clangd) dan menjawab permintaan server ke klien
  yang tidak relevan untuk editor ringan (workspace/configuration, registerCapability, progress).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from backend.config import Settings
from backend.core.exceptions import AppError, ServiceUnavailable
from backend.core.logging import get_logger
from backend.core.sandbox import Limits, SandboxSpec, make_preexec, require_sandbox, wrap

log = get_logger("lsp")

VIRTUAL_ROOT = "/workspace"
MAX_MESSAGE = 8 * 1024 * 1024
LANG_SERVER = {"c": "clangd", "cpp": "clangd", "python": "pyright", "javascript": "tsserver", "typescript": "tsserver",
               "go": "gopls", "php": "intelephense", "html": "html", "css": "css", "json": "json", "shell": "bash"}
# stub bawaan intelephense (fungsi/kelas PHP inti & ekstensi umum)
INTELEPHENSE_STUBS = ["apache", "bcmath", "bz2", "calendar", "com_dotnet", "Core", "ctype", "curl", "date", "dba", "dom",
                      "enchant", "exif", "FFI", "fileinfo", "filter", "fpm", "ftp", "gd", "gettext", "gmp", "hash", "iconv",
                      "imap", "intl", "json", "ldap", "libxml", "mbstring", "meta", "mysqli", "oci8", "odbc", "openssl",
                      "pcntl", "pcre", "PDO", "pdo_mysql", "pdo_pgsql", "pdo_sqlite", "pgsql", "Phar", "posix", "pspell",
                      "random", "readline", "Reflection", "session", "shmop", "SimpleXML", "snmp", "soap", "sockets",
                      "sodium", "SPL", "sqlite3", "standard", "superglobals", "sysvmsg", "sysvsem", "sysvshm", "tidy",
                      "tokenizer", "xml", "xmlreader", "xmlrpc", "xmlwriter", "xsl", "Zend OPcache", "zip", "zlib"]
# server berbasis Node di .lsp/node_modules: id -> (file JS, argumen)
NODE_SERVERS = {
    "tsserver": ("typescript-language-server/lib/cli.mjs", ["--stdio"]),
    "intelephense": ("intelephense/lib/intelephense.js", ["--stdio"]),
    "html": ("vscode-langservers-extracted/bin/vscode-html-language-server", ["--stdio"]),
    "css": ("vscode-langservers-extracted/bin/vscode-css-language-server", ["--stdio"]),
    "json": ("vscode-langservers-extracted/bin/vscode-json-language-server", ["--stdio"]),
    "bash": ("bash-language-server/out/cli.js", ["start"]),
}


@dataclass
class ServerInfo:
    id: str
    argv: list[str]
    readonly: list[Path]
    env: dict[str, str]


def _clangd_binary(settings: Settings) -> Path | None:
    """Binary clangd asli (paket pip 'clangd' di venv server, atau clangd sistem)."""
    pyver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    for cand in (settings.base_dir / ".venv" / "lib" / pyver / "site-packages" / "clangd" / "data" / "bin" / "clangd",):
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    for name in ("clangd", "clangd-19", "clangd-18", "clangd-17", "clangd-16", "clangd-15", "clangd-14"):
        exe = shutil.which(name)
        if exe and not exe.startswith(str(settings.base_dir / ".venv")):
            return Path(os.path.realpath(exe))
    return None


def _pyright(settings: Settings) -> tuple[Path, Path] | None:
    """(node, langserver.index.js) untuk pyright yang dipasang di .lsp/ (npm)."""
    node = shutil.which("node")
    js = settings.base_dir / ".lsp" / "node_modules" / "pyright" / "langserver.index.js"
    if node and js.is_file():
        return Path(os.path.realpath(node)), js
    return None


class LspService:
    def __init__(self, settings: Settings):
        self.s = settings
        self.active = 0
        self.max_sessions = int(os.environ.get("CS_LSP_MAX_SESSIONS", "6"))

    # ---------- ketersediaan ----------
    def server_for(self, language: str) -> ServerInfo | None:
        kind = LANG_SERVER.get(language)
        if kind == "clangd":
            exe = _clangd_binary(self.s)
            if not exe:
                return None
            ro = [exe.parent.parent] if str(exe).startswith(str(Path.home())) else []
            return ServerInfo("clangd", [str(exe), "--background-index=false", "--log=error", "-j=2",
                                         "--pch-storage=memory", "--header-insertion=never",
                                         "--completion-style=bundled", "--limit-results=60"], ro, {})
        if kind == "pyright":
            found = _pyright(self.s)
            if not found:
                return None
            node, js = found
            return ServerInfo("pyright", [str(node), "--max-old-space-size=512", str(js), "--stdio"],
                              [self.s.base_dir / ".lsp"], {})
        if kind in NODE_SERVERS:
            node = shutil.which("node")
            rel, args = NODE_SERVERS[kind]
            js = self.s.base_dir / ".lsp" / "node_modules" / rel
            if not node or not js.is_file():
                return None
            return ServerInfo(kind, [os.path.realpath(node), "--max-old-space-size=512", str(js), *args],
                              [self.s.base_dir / ".lsp"], {})
        if kind == "gopls":
            exe = self.s.base_dir / ".lsp" / "bin" / "gopls"
            go = shutil.which("go")
            if not exe.is_file() or not go:
                return None
            goroot = Path(os.path.realpath(go)).parent.parent
            ro = [self.s.base_dir / ".lsp"] + ([goroot] if str(goroot).startswith(str(Path.home())) else [])
            return ServerInfo("gopls", [str(exe)], ro, {"GOFLAGS": "-mod=mod", "GOPROXY": "off", "GOTOOLCHAIN": "local",
                                                        "PATH": f"{goroot / 'bin'}:/usr/local/bin:/usr/bin:/bin"})
        return None

    def status(self) -> dict:
        out = {}
        for lang in LANG_SERVER:
            info = self.server_for(lang)
            out[lang] = {"server": LANG_SERVER[lang], "available": info is not None}
        return {"languages": out, "active_sessions": self.active, "max_sessions": self.max_sessions}

    # ---------- sesi ----------
    async def start(self, language: str, project_dir: Path, project_id: str) -> "LspSession":
        info = self.server_for(language)
        if info is None:
            raise ServiceUnavailable(f"Language server untuk {language} belum terpasang (jalankan scripts/install_runtimes.sh)",
                                     code="lsp_unavailable")
        if self.active >= self.max_sessions:
            raise AppError("Terlalu banyak sesi language server aktif; tutup editor lain dulu", code="lsp_busy", status_code=429)
        require_sandbox(self.s)
        cache = self.s.cache_dir / "lsp" / info.id
        cache.mkdir(parents=True, exist_ok=True)
        env = {**info.env, "XDG_CACHE_HOME": str(cache), "HOME": str(cache)}
        spec = SandboxSpec(cwd=project_dir, writable=[cache], readonly=[project_dir, *info.readonly],
                           network=False, env=env)
        argv, env = wrap(info.argv, spec, enabled=self.s.sandbox_enabled)
        # proses hidup lama: batas waktu CPU total 2 jam (sesi idle ditutup jauh sebelum itu)
        limits = Limits(timeout=3600, memory_mb=1024, address_space_limit=False, cpu_seconds=7200, nice=10)
        proc = await asyncio.create_subprocess_exec(
            *argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            env=env, cwd=str(project_dir), preexec_fn=make_preexec(limits), limit=MAX_MESSAGE,
        )
        self.active += 1
        log.info("LSP %s mulai untuk %s (pid %s)", info.id, project_id, proc.pid)
        return LspSession(self, info, proc, project_dir, project_id, language)


class LspSession:
    def __init__(self, svc: LspService, info: ServerInfo, proc: asyncio.subprocess.Process, project_dir: Path,
                 project_id: str, language: str):
        self.svc, self.info, self.proc = svc, info, proc
        self.root = str(project_dir)
        self.project_id = project_id
        self.language = language
        self.last_activity = time.time()
        self._closed = False
        self._write_lock = asyncio.Lock()
        # intelephense menjawab kosong (dan terus kosong untuk dokumen itu) bila diminta sebelum indeks pertama selesai:
        # tahan permintaan klien sampai notifikasi "indexingEnded".
        self._indexed = asyncio.Event()
        if info.id != "intelephense":
            self._indexed.set()

    # ---------- penulisan path ----------
    def to_server(self, text: str) -> str:
        return (text.replace("file://" + VIRTUAL_ROOT + "/", "file://" + self.root + "/")
                    .replace('"file://' + VIRTUAL_ROOT + '"', '"file://' + self.root + '"'))

    def to_client(self, text: str) -> str:
        return text.replace(self.root, VIRTUAL_ROOT)

    def _init_options(self) -> dict:
        lsp_dir = self.svc.s.base_dir / ".lsp" / "node_modules"
        if self.info.id == "tsserver":
            return {"tsserver": {"path": str(lsp_dir / "typescript" / "lib" / "tsserver.js")},
                    "preferences": {"includeCompletionsForModuleExports": True}}
        if self.info.id == "intelephense":
            store = str(self.svc.s.cache_dir / "lsp" / "intelephense")
            return {"storagePath": store, "globalStoragePath": store, "clearCache": False}
        if self.info.id in ("html", "css", "json"):
            return {"provideFormatter": False, "embeddedLanguages": {"css": True, "javascript": True}}
        if self.info.id != "clangd":
            return {}
        # tanpa -std: clangd memilih C/C++ dari ekstensi file (satu sesi melayani .c dan .cpp)
        flags = ["-Wall", "-Wextra", f"-I{self.root}"]
        for name in ("include", "inc", "src"):
            if os.path.isdir(os.path.join(self.root, name)):
                flags.append(f"-I{os.path.join(self.root, name)}")
        opts: dict = {"fallbackFlags": flags, "clangdFileStatus": False}
        db = self._compile_db()
        if db:
            opts["compilationDatabasePath"] = db
        return opts

    def _config_for(self, section: str | None):
        """Jawaban workspace/configuration. intelephense butuh objek pengaturan (null = tanpa stub fungsi bawaan PHP)."""
        if self.info.id == "intelephense" and section in (None, "intelephense"):
            return {"stubs": INTELEPHENSE_STUBS, "files": {"maxSize": 1000000}, "telemetry": {"enabled": False},
                    "completion": {"insertUseDeclaration": True, "fullyQualifyGlobalConstantsAndFunctions": False}}
        return None

    def _compile_db(self) -> str | None:
        """compile_commands.json dari build CMake terakhir proyek ini (bila ada) atau di akar proyek."""
        if os.path.isfile(os.path.join(self.root, "compile_commands.json")):
            return self.root
        base = self.svc.s.cache_dir / "builds" / self.project_id
        cands = sorted(base.glob("*/_cmake_*/compile_commands.json"), key=lambda p: p.stat().st_mtime, reverse=True) \
            if base.is_dir() else []
        return str(cands[0].parent) if cands else None

    def prepare_from_client(self, msg: dict) -> dict:
        if msg.get("method") == "initialize":
            params = msg.setdefault("params", {})
            params["processId"] = None
            params["rootUri"] = "file://" + VIRTUAL_ROOT
            params["rootPath"] = VIRTUAL_ROOT
            params["workspaceFolders"] = [{"uri": "file://" + VIRTUAL_ROOT, "name": self.project_id}]
            opts = self._init_options()
            if opts:
                params["initializationOptions"] = {**opts, **(params.get("initializationOptions") or {})}
        return msg

    # ---------- IO ----------
    async def send(self, msg: dict) -> None:
        self.last_activity = time.time()
        if (not self._indexed.is_set() and "id" in msg and msg.get("method")
                and msg["method"] not in ("initialize", "shutdown")):
            try:
                await asyncio.wait_for(self._indexed.wait(), 30)
            except asyncio.TimeoutError:
                self._indexed.set()
        msg = self.prepare_from_client(msg)
        body = self.to_server(json.dumps(msg, ensure_ascii=False)).encode()
        if self.proc.stdin is None or self.proc.returncode is not None:
            raise AppError("Language server sudah berhenti", code="lsp_exited")
        async with self._write_lock:
            self.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
            await self.proc.stdin.drain()

    async def _read_raw(self) -> dict | None:
        assert self.proc.stdout is not None
        length = None
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                break
            name, _, value = line.decode("ascii", "replace").partition(":")
            if name.lower() == "content-length":
                length = int(value.strip())
        if length is None or length > MAX_MESSAGE:
            raise AppError("Pesan language server tidak valid", code="lsp_protocol")
        data = await self.proc.stdout.readexactly(length)
        return json.loads(self.to_client(data.decode("utf-8", "replace")))

    async def receive(self) -> dict | None:
        """Pesan berikutnya untuk klien. Permintaan server->klien yang umum dijawab di sini (tidak diteruskan)."""
        while True:
            msg = await self._read_raw()
            if msg is None:
                return None
            method = msg.get("method")
            if method and "id" in msg:  # request dari server
                result = None
                if method == "workspace/configuration":
                    result = [self._config_for((it or {}).get("section")) for it in (msg.get("params") or {}).get("items", [])]
                elif method == "workspace/workspaceFolders":
                    result = [{"uri": "file://" + VIRTUAL_ROOT, "name": self.project_id}]
                elif method not in ("client/registerCapability", "client/unregisterCapability",
                                    "window/workDoneProgress/create", "window/showMessageRequest",
                                    "workspace/semanticTokens/refresh", "workspace/inlayHint/refresh",
                                    "workspace/diagnostic/refresh", "workspace/codeLens/refresh"):
                    return msg  # biarkan klien yang memutuskan
                await self.send({"jsonrpc": "2.0", "id": msg["id"], "result": result})
                continue
            if method == "indexingEnded":
                self._indexed.set()
            if method in ("$/progress", "window/logMessage", "telemetry/event", "pyright/beginProgress",
                          "pyright/reportProgress", "pyright/endProgress", "textDocument/clangd.fileStatus"):
                continue
            self.last_activity = time.time()
            return msg

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.svc.active = max(0, self.svc.active - 1)
        try:
            if self.proc.returncode is None and self.proc.stdin is not None:
                try:
                    await asyncio.wait_for(self.send({"jsonrpc": "2.0", "id": "shutdown", "method": "shutdown"}), 1)
                    await asyncio.wait_for(self.send({"jsonrpc": "2.0", "method": "exit"}), 1)
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(self.proc.wait(), 2)
                except asyncio.TimeoutError:
                    from backend.core.process_manager import kill_tree
                    kill_tree(self.proc.pid)
                    await asyncio.wait_for(self.proc.wait(), 3)
        except Exception as e:
            log.warning("Menutup LSP: %s", e)
        log.info("LSP %s untuk %s ditutup", self.info.id, self.project_id)
