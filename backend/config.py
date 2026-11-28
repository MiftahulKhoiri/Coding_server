"""Konfigurasi CODING_SERVER.

Semua nilai bisa diatur lewat environment variable berawalan ``CS_`` atau lewat file
``deployment/configuration/coding_server.env`` (format KEY=VALUE). Environment menang.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VERSION = "1.7.0"


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def _bool(v: str | None, default: bool) -> bool:
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    base_dir: Path
    host: str = "0.0.0.0"
    port: int = 8800
    workspace_dir: Path = field(default=Path())
    projects_dir: Path = field(default=Path())
    metadata_dir: Path = field(default=Path())
    database_dir: Path = field(default=Path())
    history_dir: Path = field(default=Path())
    data_dir: Path = field(default=Path())
    cache_dir: Path = field(default=Path())
    logs_dir: Path = field(default=Path())
    backups_dir: Path = field(default=Path())

    secret_key: str = ""
    access_token_minutes: int = 720
    refresh_token_days: int = 30
    admin_username: str = "admin"
    # Sandi akun admin utama (root). Bila diisi, sandi root DISINKRONKAN ke nilai ini setiap server
    # start, jadi akun admin selalu bisa dipakai untuk pemulihan. Bila kosong: dipakai file
    # metadata/initial_admin_password.txt (dibuat saat pertama kali), lalu sandi root tidak disentuh.
    admin_password: str = ""

    # Eksekusi & sumber daya
    max_concurrent_jobs: int = 2
    max_queued_jobs: int = 20
    run_timeout: int = 60
    build_timeout: int = 300
    memory_limit_mb: int = 1024
    min_free_memory_mb: int = 512
    output_limit_bytes: int = 1_000_000
    max_file_size_bytes: int = 10_000_000
    sandbox: str = "auto"  # auto | bwrap | none
    sandbox_network: bool = False  # akses jaringan untuk program yang dijalankan
    # Akses jaringan KHUSUS langkah instal dependensi (pip/npm/go/composer) yang perintahnya disusun
    # server. Program pengguna tetap tanpa jaringan (sandbox_network) meski ini aktif.
    install_network: bool = True
    install_timeout: int = 900
    terminal_network: bool = False
    terminal_idle_timeout: int = 1800
    max_terminal_sessions: int = 6

    # HTTP client
    http_allow_private: bool = False
    http_timeout: int = 30

    # Backup
    backup_retention: int = 7

    # AI provider (OpenAI-compatible, mis. llama-server)
    ai_base_url: str = ""
    ai_model: str = ""
    ai_api_key: str = ""

    # AI Coding Agent
    agent_max_concurrent: int = 1   # model lokal = bottleneck RAM; satu task aktif sekaligus
    agent_max_steps: int = 100
    agent_model_timeout: int = 1800  # detik per jawaban model (model besar di CPU Pi bisa lambat)
    agent_task_timeout: int = 21600  # detik per sesi berjalan (6 jam; task berjalan di latar belakang)

    # Profil model (file JSON per model, ikut repo) + sinkron otomatis ke GitHub
    model_profiles_dir: Path = field(default=Path())
    # File preset llama-server router (ukuran konteks per model), dibaca router via --models-preset.
    llama_presets_file: Path = field(default=Path())
    model_profiles_git: bool = True

    rate_limit_login_per_minute: int = 10
    rate_limit_api_per_minute: int = 600  # per token; tes menaikkannya karena polling cepat
    cors_origins: str = ""

    @property
    def sandbox_enabled(self) -> bool:
        if self.sandbox == "none":
            return False
        from backend.core.sandbox import bwrap_available

        if self.sandbox == "bwrap":
            return True
        return bwrap_available()

    def ensure_dirs(self) -> None:
        for p in (
            self.workspace_dir,
            self.projects_dir,
            self.metadata_dir,
            self.database_dir,
            self.history_dir,
            self.data_dir,
            self.cache_dir,
            self.logs_dir,
            self.backups_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)


def _secret_from_file(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return path.read_text().strip()
    key = secrets.token_urlsafe(48)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key)
    return key


def build_settings(env: dict[str, str] | None = None) -> Settings:
    base = Path(os.environ.get("CS_BASE_DIR", str(BASE_DIR))).resolve()
    merged = _load_env_file(base / "deployment" / "configuration" / "coding_server.env")
    merged.update({k: v for k, v in os.environ.items() if k.startswith("CS_")})
    if env:
        merged.update(env)

    def g(name: str, default: str | None = None) -> str | None:
        return merged.get("CS_" + name.upper(), default)

    ws = Path(g("workspace_dir") or base / "workspace").resolve()
    s = Settings(base_dir=base)
    s.host = g("host", s.host)
    s.port = int(g("port", str(s.port)))
    s.workspace_dir = ws
    s.projects_dir = ws / "projects"
    s.metadata_dir = ws / "metadata"
    s.database_dir = ws / "database"
    s.history_dir = ws / "history"
    s.data_dir = ws / "data"
    s.cache_dir = ws / "cache"
    s.logs_dir = Path(g("logs_dir") or base / "logs").resolve()
    s.backups_dir = Path(g("backups_dir") or base / "backups").resolve()
    s.model_profiles_dir = Path(g("model_profiles_dir") or base / "model_profiles").resolve()
    s.llama_presets_file = Path(g("llama_presets_file") or Path.home() / "models" / "coding_server_presets.ini").expanduser()

    for name in (
        "access_token_minutes", "refresh_token_days", "max_concurrent_jobs", "max_queued_jobs",
        "run_timeout", "build_timeout", "memory_limit_mb", "min_free_memory_mb",
        "output_limit_bytes", "max_file_size_bytes", "terminal_idle_timeout",
        "max_terminal_sessions", "http_timeout", "backup_retention", "rate_limit_login_per_minute",
        "rate_limit_api_per_minute",
        "agent_max_concurrent", "agent_max_steps", "agent_model_timeout", "agent_task_timeout",
        "install_timeout",
    ):
        val = g(name)
        if val:
            setattr(s, name, int(val))
    for name in ("sandbox_network", "install_network", "terminal_network", "http_allow_private", "model_profiles_git"):
        setattr(s, name, _bool(g(name), getattr(s, name)))
    for name in ("sandbox", "admin_username", "admin_password", "ai_base_url", "ai_model", "ai_api_key", "cors_origins"):
        val = g(name)
        if val is not None:
            setattr(s, name, val)

    s.ensure_dirs()
    s.secret_key = g("secret_key") or _secret_from_file(s.metadata_dir / "secret.key")
    return s


@lru_cache
def get_settings() -> Settings:
    return build_settings()
