"""Skema request/response (kontrak OpenAPI antara backend dan Android)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class OkResponse(BaseModel):
    ok: bool = True
    message: str = ""


# ---------- auth ----------
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    permissions: list[str]
    created_at: float
    display_name: str = ""
    email: str = ""
    bio: str = ""
    is_root: bool = False  # admin utama: tidak bisa dihapus/diubah, sandi diatur dari server
    updated_at: float = 0.0
    last_login_at: float | None = None
    avatar_version: float | None = None  # ada foto profil bila tidak null → GET /auth/users/{id}/avatar
    email_verified: bool = False  # email berasal dari akun GitHub/Google tertaut


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: int
    refresh_expires_at: int
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    role: Literal["admin", "developer", "runner", "viewer", "ai"] = "developer"
    display_name: str = Field(default="", max_length=80)
    email: str = Field(default="", max_length=120)


class UserUpdate(BaseModel):
    role: Literal["admin", "developer", "runner", "viewer", "ai"] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)
    display_name: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=120)


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=500)


class UserDeleted(BaseModel):
    ok: bool = True
    message: str = ""
    username: str
    projects_moved: int = 0


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)


# ---------- projects ----------
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    language: str = ""
    template: bool = True


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    description: str | None = None
    language: str | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str
    language: str
    owner_id: int
    created_at: float
    updated_at: float
    path_exists: bool = True


# ---------- files ----------
class FileEntry(BaseModel):
    name: str
    path: str
    type: str
    size: int
    modified: float
    extension: str = ""
    language: str = ""
    mime: str | None = None
    children: list["FileEntry"] | None = None
    truncated: bool | None = None


class FileContent(FileEntry):
    binary: bool
    content: str | None
    encoding: str | None = None
    sha256: str


class FileCreate(BaseModel):
    project_id: str
    path: str
    type: Literal["file", "folder"] = "file"
    content: str = ""


class OAuthConfigIn(BaseModel):
    github_client_id: str | None = Field(default=None, max_length=200)
    google_client_id: str | None = Field(default=None, max_length=300)
    google_client_secret: str | None = Field(default=None, max_length=300)


class LinkStart(BaseModel):
    allow_push: bool = False  # GitHub: izinkan push (scope repo), token disimpan sebagai kredensial Git


class GrepRequest(BaseModel):
    project_id: str
    query: str = Field(min_length=1, max_length=500)
    regex: bool = False
    case_sensitive: bool = False
    whole_word: bool = False


class ReplaceRequest(GrepRequest):
    replacement: str = Field(default="", max_length=10_000)
    paths: list[str] | None = None  # None = semua file teks proyek


class FormatRequest(BaseModel):
    project_id: str
    path: str
    content: str = Field(max_length=2_000_000)
    tab_size: int = Field(default=4, ge=1, le=8)


class FileWrite(BaseModel):
    project_id: str
    path: str
    content: str
    expected_sha256: str | None = None


class FileRename(BaseModel):
    project_id: str
    path: str
    new_name: str


class FileMove(BaseModel):
    project_id: str
    path: str
    destination: str
    overwrite: bool = False


class FavoriteRequest(BaseModel):
    project_id: str
    path: str


class RestoreRequest(BaseModel):
    project_id: str
    history_id: int


# ---------- execution ----------
class RunRequest(BaseModel):
    project_id: str
    path: str
    language: str | None = None
    args: list[str] = Field(default_factory=list, max_length=64)
    stdin: str | None = Field(default=None, max_length=1_000_000)
    interactive: bool = False
    timeout: int | None = Field(default=None, ge=1, le=3600)


class InstallRequest(BaseModel):
    project_id: str
    kind: Literal["python", "node", "go", "php"] | None = None
    packages: list[str] = Field(default_factory=list, max_length=20)


class JobOut(BaseModel):
    process_id: str
    project_id: str
    user_id: int
    action: str
    language: str
    file: str
    status: Literal["QUEUED", "STARTING", "RUNNING", "COMPLETED", "FAILED", "TIMEOUT", "CANCELLED"]
    exit_code: int | None = None
    command: list[list[str]] = Field(default_factory=list)
    error: str = ""
    created_at: float
    start_time: float | None = None
    end_time: float | None = None
    duration: float | None = None
    truncated: bool = False
    preview_path: str | None = None
    stdout: str | None = None
    stderr: str | None = None


class StdinRequest(BaseModel):
    data: str = ""
    eof: bool = False


# ---------- terminal ----------
class TerminalCreate(BaseModel):
    project_id: str
    cwd: str = ""
    cols: int = Field(default=80, ge=10, le=500)
    rows: int = Field(default=24, ge=2, le=300)


class TerminalOut(BaseModel):
    session_id: str
    owner_id: int
    project_id: str
    working_directory: str
    created_at: float
    last_activity: float
    status: str
    exit_code: int | None = None
    history: list[str] = Field(default_factory=list)


# ---------- database ----------
class DbCreate(BaseModel):
    name: str
    project_id: str | None = None


class DbQuery(BaseModel):
    database: str
    project_id: str | None = None
    sql: str = Field(min_length=1, max_length=1_000_000)
    params: list[Any] | dict[str, Any] | None = None
    mode: Literal["read", "write"] = "read"
    confirm: bool = False


class DbImport(BaseModel):
    database: str
    project_id: str | None = None
    table: str
    csv: str
    create_table: bool = True


class DbRef(BaseModel):
    database: str
    project_id: str | None = None


# ---------- git ----------
class GitProject(BaseModel):
    project_id: str


class GitAdd(GitProject):
    paths: list[str] = Field(default_factory=lambda: ["."])


class GitCommit(GitProject):
    message: str = Field(min_length=1, max_length=5000)
    add_all: bool = False


class GitRemoteOp(GitProject):
    remote: str = "origin"
    branch: str | None = None


class GitBranch(GitProject):
    name: str
    checkout: bool = True


class GitCheckout(GitProject):
    ref: str


class GitRemoteSet(GitProject):
    name: str = "origin"
    url: str


class GitClone(BaseModel):
    url: str
    name: str | None = None
    branch: str | None = None


class GitCredential(BaseModel):
    host: str = "github.com"
    username: str
    token: str = Field(min_length=1)


# ---------- http ----------
class HttpRequestIn(BaseModel):
    method: str = "GET"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    body_type: Literal["none", "json", "form", "raw"] = "none"
    form: dict[str, str] | None = None
    timeout: float | None = Field(default=None, gt=0, le=120)
    follow_redirects: bool = True


class HttpSaved(BaseModel):
    name: str
    collection: str = "default"
    method: str = "GET"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)
    params: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    body_type: Literal["none", "json", "form", "raw"] = "none"


# ---------- backup ----------
class BackupCreate(BaseModel):
    label: str = Field(default="manual", pattern=r"^[A-Za-z0-9_-]{1,32}$")


class BackupRestore(BaseModel):
    name: str
    include_metadata: bool = False
    confirm: bool = False


# ---------- AI ----------
class AIChat(BaseModel):
    messages: list[dict[str, str]]
    project_id: str | None = None
    files: list[str] = Field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None


class AIConnectionIn(BaseModel):
    name: str = Field(default="", max_length=80)
    kind: Literal["llama_router", "openai", "anthropic", "gemini"]
    location: Literal["local", "online"]
    base_url: str = Field(min_length=8, max_length=300)
    api_key: str | None = Field(default=None, max_length=500)


class AIApply(BaseModel):
    connection_id: str
    model: str = Field(min_length=1, max_length=300)
    wait: bool = False


class AISettingsIn(BaseModel):
    system_prompt: str | None = Field(default=None, max_length=20000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=16, le=65536)
    idle_unload_minutes: int | None = Field(default=None, ge=0, le=1440)
    history_messages: int | None = Field(default=None, ge=0, le=200)


class AgentModelTarget(BaseModel):
    connection_id: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=300)


class AgentModelsIn(BaseModel):
    """Peran model agent. Kirim null untuk mengosongkan peran (kembali ke model aktif)."""
    planner: AgentModelTarget | None = None
    executor: AgentModelTarget | None = None
    reviewer: AgentModelTarget | None = None
    online: AgentModelTarget | None = None
    allow_online: bool | None = None
    escalate_after_failures: int | None = Field(default=None, ge=1, le=10)
    max_loaded_models: int | None = Field(default=None, ge=1, le=4)
    max_steps: int | None = Field(default=None, ge=3, le=500)  # dibatasi lagi oleh CS_AGENT_MAX_STEPS
    approval_mode: Literal["manual", "otomatis", "penuh"] | None = None


class ContextIn(BaseModel):
    """Ukuran konteks llama-server. default_ctx null = tidak diubah; models: {nama: angka | null (ikut bawaan)}."""
    connection_id: str
    default_ctx: int | None = Field(default=None, ge=2048, le=131072)
    models: dict[str, int | None] | None = None


class ModelBenchIn(BaseModel):
    targets: list[AgentModelTarget] = Field(min_length=1, max_length=10)
    mode: Literal["cepat", "kalibrasi"] = "cepat"


class ModelPresetIn(BaseModel):
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    top_k: int | None = Field(default=None, ge=0, le=500)
    min_p: float | None = Field(default=None, ge=0, le=1)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    repeat_penalty: float | None = Field(default=None, ge=0.5, le=2)
    thinking: bool | None = None
    max_tokens: int = Field(default=2048, ge=64, le=32768)


class ModelProfileIn(BaseModel):
    """Ubah profil secara manual. Kolom yang tidak dikirim tidak diubah."""
    active: bool | None = None
    kegunaan: list[str] | None = None
    catatan: str | None = Field(default=None, max_length=2000)
    prompt_tambahan: str | None = Field(default=None, max_length=4000)
    kualitas: ModelPresetIn | None = None
    cepat: ModelPresetIn | None = None


class ModelProfileImport(BaseModel):
    profile: dict


class AIConversationIn(BaseModel):
    title: str = Field(default="Percakapan baru", max_length=120)


class AIProposal(BaseModel):
    project_id: str
    path: str
    action: Literal["write", "delete"] = "write"
    content: str | None = None
    reason: str = ""


class AIDecision(BaseModel):
    project_id: str
    approve: bool = True
    confirm_high_risk: bool = False


class AgentTaskCreate(BaseModel):
    project_id: str
    description: str = Field(min_length=1, max_length=20_000)
    title: str | None = Field(default=None, max_length=120)
    auto_apply: bool | None = None  # None = ikuti mode izin agent (Model AI → AI Agent)
    max_steps: int | None = Field(default=None, ge=3, le=500)  # None = pakai pengaturan (Model AI → AI Agent)
