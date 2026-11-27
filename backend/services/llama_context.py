"""Ukuran konteks model llama-server (mode router) lewat file preset INI.

llama-server router membaca `--models-preset FILE` dan memuat ulang file itu lewat `GET /models?reload=1`
tanpa restart: model yang pengaturannya berubah dibongkar, lalu dimuat lagi dengan konteks baru saat dipakai.

PENTING: argumen baris perintah router (mis. `-c 8192` di service) SELALU mengalahkan preset. Karena itu
status() memeriksa proses router lokal dan memberi peringatan beserta perintah perbaikannya.

File ini dikelola penuh oleh CODING_SERVER (ditulis ulang utuh setiap simpan):
    version = 1
    [*]
    c = 16384                     ; bawaan semua model
    [Qwen2.5-Coder-7B-Instruct-Q4_K_M]
    c = 16384                     ; khusus model ini
"""
from __future__ import annotations

import configparser
import os
import time
from pathlib import Path

import httpx
import psutil

from backend.core.exceptions import AppError
from backend.services.ai_providers import http_client

CTX_MIN, CTX_MAX, CTX_STEP = 2048, 131072, 256
HEADER = ("; Dikelola oleh CODING_SERVER (Model AI → AI Agent → Konteks model). Perubahan manual akan ditimpa.\n"
          "; Dipakai llama-server: --models-preset {path}\n")


def check_ctx(v: int | None) -> int | None:
    if v is None:
        return None
    v = int(v)
    if v < CTX_MIN or v > CTX_MAX or v % CTX_STEP:
        raise AppError(f"Ukuran konteks harus {CTX_MIN}–{CTX_MAX} dan kelipatan {CTX_STEP}", code="bad_ctx")
    return v


def read_presets(path: Path) -> dict:
    """{'default': int|None, 'models': {nama: int}} dari file preset (kosong bila belum ada)."""
    out: dict = {"default": None, "models": {}}
    if not path.is_file():
        return out
    cp = configparser.ConfigParser(inline_comment_prefixes=(";", "#"), strict=False, interpolation=None)
    try:
        cp.read_string("[__top__]\n" + path.read_text(encoding="utf-8"))
    except (configparser.Error, OSError):
        return out

    def ctx_of(sec) -> int | None:
        for k in ("c", "ctx-size", "LLAMA_ARG_CTX_SIZE"):
            if k in sec:
                try:
                    return int(sec[k])
                except ValueError:
                    return None
        return None

    for name in cp.sections():
        if name == "__top__":
            continue
        v = ctx_of(cp[name])
        if name == "*":
            out["default"] = v
        elif v:
            out["models"][name] = v
    return out


def write_presets(path: Path, default: int | None, models: dict[str, int]) -> None:
    lines = [HEADER.format(path=path), "version = 1", ""]
    if default:
        lines += ["[*]", f"c = {default}", ""]
    for name in sorted(models):
        if "]" in name or "\n" in name:
            raise AppError(f"Nama model tidak valid: {name!r}", code="bad_model")
        lines += [f"[{name}]", f"c = {models[name]}", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, path)


def router_process(port: int | None = None) -> dict | None:
    """Proses llama-server router di mesin ini (bila ada): argumen penting untuk diagnosis."""
    for p in psutil.process_iter(["cmdline"]):
        cmd = p.info.get("cmdline") or []
        if not cmd or "llama-server" not in os.path.basename(cmd[0]) or "--models-dir" not in cmd \
                and "--models-preset" not in cmd:
            continue
        if port is not None and "--port" in cmd and cmd[cmd.index("--port") + 1] != str(port):
            continue
        preset = cmd[cmd.index("--models-preset") + 1] if "--models-preset" in cmd[:-1] else None
        cli_ctx = None
        for flag in ("-c", "--ctx-size"):
            if flag in cmd[:-1]:
                cli_ctx = cmd[cmd.index(flag) + 1]
        return {"pid": p.pid, "cmdline": " ".join(cmd), "preset": preset, "cli_ctx": cli_ctx}
    return None


async def router_models(base: str, reload: bool = False) -> list[dict]:
    """Model di router + ukuran konteks yang BENAR-BENAR dipakai (dari argumen proses model)."""
    async with http_client(30) as c:
        try:
            r = await c.get(f"{base}/models" + ("?reload=1" if reload else ""))
        except httpx.HTTPError as e:
            raise AppError(f"Tidak bisa menghubungi llama-server: {e}", code="ai_unreachable", status_code=502)
    if not r.is_success:
        raise AppError(f"llama-server menjawab {r.status_code} untuk /models (bukan mode router?)", code="ai_error",
                       status_code=502)
    out = []
    for m in r.json().get("data", []):
        st = m.get("status") or {}
        args = st.get("args") or []
        ctx = None
        for flag in ("--ctx-size", "-c"):
            if flag in args[:-1]:
                try:
                    ctx = int(args[args.index(flag) + 1])
                except ValueError:
                    pass
        out.append({"id": m["id"], "status": st.get("value"), "ctx": ctx})
    return out


class LlamaContextService:
    def __init__(self, settings, ai):
        self.s = settings
        self.ai = ai

    @property
    def path(self) -> Path:
        return self.s.llama_presets_file

    def _router(self, cid: str) -> tuple[dict, str]:
        row, _ = self.ai.provider(cid)
        if row["kind"] != "llama_router":
            raise AppError("Pengaturan konteks hanya untuk koneksi llama-server (mode router)", code="not_router")
        return row, row["base_url"]

    async def status(self, cid: str) -> dict:
        row, base = self._router(cid)
        presets = read_presets(self.path)
        models = await router_models(base)
        port = None
        try:
            port = int(base.rsplit(":", 1)[1].split("/")[0])
        except (IndexError, ValueError):
            pass
        proc = router_process(port)
        problems = []
        if proc is None:
            problems.append("Proses llama-server router tidak ditemukan di mesin ini; file preset hanya berlaku bila "
                            "router berjalan di Pi yang sama.")
        else:
            if proc["preset"] != str(self.path):
                problems.append(f"Router belum memakai file preset ini. Tambahkan: --models-preset {self.path}")
            if proc["cli_ctx"]:
                problems.append(f"Router dijalankan dengan -c {proc['cli_ctx']}; argumen ini MENGALAHKAN preset. "
                                "Hapus -c dari perintah/service llama-server.")
        for m in models:
            m["configured"] = presets["models"].get(m["id"]) or presets["default"]
            m["override"] = presets["models"].get(m["id"])
        return {"connection_id": cid, "preset_file": str(self.path), "default_ctx": presets["default"],
                "models": models, "router": proc, "problems": problems, "ready": not problems,
                "limits": {"min": CTX_MIN, "max": CTX_MAX, "step": CTX_STEP},
                "fix_command": self.fix_command(proc)}

    def fix_command(self, proc: dict | None) -> str:
        """Perintah sekali-jalan (butuh sudo) untuk service systemd llama-server."""
        unit = "/etc/systemd/system/llama-server.service"
        return (f"sudo sed -i -E 's/ (-c|--ctx-size) [0-9]+//; /--models-preset/! "
                f"s#^(ExecStart=.*llama-server)#\\1 --models-preset {self.path}#' {unit} && "
                "sudo systemctl daemon-reload && sudo systemctl restart llama-server")

    async def save(self, cid: str, default_ctx: int | None, models: dict[str, int | None] | None,
                   busy: bool) -> dict:
        row, base = self._router(cid)
        if busy:
            raise AppError("Ada task AI Agent yang sedang berjalan. Jeda/tunggu selesai dulu: model yang konteksnya "
                           "berubah akan dimuat ulang.", code="agent_busy", status_code=409)
        cur = read_presets(self.path)
        default = check_ctx(default_ctx) if default_ctx is not None else cur["default"]
        merged = dict(cur["models"])
        for name, v in (models or {}).items():
            if v is None or v == 0:
                merged.pop(name, None)  # ikut bawaan
            else:
                merged[name] = check_ctx(v)
        write_presets(self.path, default, merged)
        await router_models(base, reload=True)  # router membaca ulang preset; model yang berubah dibongkar
        return await self.status(cid)

    def ctx_for(self, model: str) -> int | None:
        """Konteks yang dikonfigurasi untuk model (dipakai agen untuk anggaran riwayat)."""
        p = read_presets(self.path)
        return p["models"].get(model) or p["default"]
