"""Git Manager. Perintah git dijalankan dengan daftar argumen tervalidasi, di dalam sandbox,
dengan hooks dimatikan. Token disimpan terenkripsi dan diberikan lewat GIT_ASKPASS (tidak
pernah masuk URL, argumen, maupun log)."""
from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from backend.config import Settings
from backend.core.exceptions import AppError
from backend.core.logging import redact
from backend.core.process_manager import RunningProcess, run_step
from backend.core.sandbox import Limits, SandboxSpec, make_preexec, require_sandbox, wrap
from backend.database.db import Database
from backend.engines.base_engine import find_executable
from backend.services.secret_store import SecretStore

ASKPASS = Path(__file__).resolve().parent.parent / "core" / "git_askpass.sh"
_REF_RE = re.compile(r"^(?!-)(?!.*\.\.)(?!.*//)[A-Za-z0-9._/\-]{1,200}(?<!\.lock)(?<!/)$")
_REMOTE_RE = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")
SAFE_CONFIG = [
    "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "-c", "protocol.ext.allow=never",
    "-c", "protocol.file.allow=user", "-c", "credential.helper=", "-c", "core.pager=cat",
    "-c", "advice.detachedHead=false", "-c", "init.defaultBranch=main", "-c", "safe.directory=*",
]


def check_ref(name: str) -> str:
    if not name or not _REF_RE.match(name):
        raise AppError(f"Nama branch/ref tidak valid: {name!r}", code="bad_ref")
    return name


def check_remote(name: str) -> str:
    if not _REMOTE_RE.match(name or "") or name.startswith("-"):
        raise AppError("Nama remote tidak valid", code="bad_remote")
    return name


def check_url(url: str) -> str:
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise AppError("Hanya URL https:// tanpa kredensial di dalamnya yang diizinkan", code="bad_url")
    return url


class GitService:
    def __init__(self, settings: Settings, db: Database):
        self.s = settings
        self.db = db
        self.secrets = SecretStore(settings.secret_key)

    # ---------- kredensial ----------
    def set_credential(self, user: dict, host: str, username: str, token: str) -> None:
        host = host.lower().strip()
        if not re.match(r"^[a-z0-9.\-]{1,253}(:\d+)?$", host):
            raise AppError("Host tidak valid", code="bad_host")
        self.db.execute(
            "INSERT OR REPLACE INTO git_credentials(user_id, host, username, secret, created_at) VALUES(?,?,?,?,?)",
            (user["id"], host, username, self.secrets.encrypt(token), time.time()),
        )

    def list_credentials(self, user: dict) -> list[dict]:
        return self.db.all("SELECT host, username, created_at FROM git_credentials WHERE user_id=?", (user["id"],))

    def delete_credential(self, user: dict, host: str) -> None:
        self.db.execute("DELETE FROM git_credentials WHERE user_id=? AND host=?", (user["id"], host.lower()))

    def _cred_env(self, user: dict, host: str | None) -> dict[str, str]:
        if not host:
            return {}
        row = self.db.one("SELECT username, secret FROM git_credentials WHERE user_id=? AND host=?", (user["id"], host.lower()))
        if not row:
            return {}
        token = self.secrets.decrypt(row["secret"])
        if token is None:
            return {}
        return {"GIT_ASKPASS": str(ASKPASS), "CS_GIT_USERNAME": row["username"], "CS_GIT_PASSWORD": token}

    # ---------- eksekusi ----------
    async def _git(self, repo: Path, args: list[str], *, user: dict, network: bool = False, host: str | None = None,
                   timeout: int = 120, writable: list[Path] | None = None) -> dict:
        require_sandbox(self.s)
        git = find_executable("git")
        if not git:
            raise AppError("git belum terpasang di server", code="engine_unavailable", status_code=503)
        # Commit memakai nama & email terverifikasi (akun tertaut) agar tercatat di profil GitHub pemiliknya.
        name = user.get("display_name") or user["username"]
        email = user.get("email") if user.get("email_verified") else f"{user['username']}@coding-server.local"
        env = {
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email,
            "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email,
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
        }
        env.update(self._cred_env(user, host))
        spec = SandboxSpec(cwd=repo, writable=writable or [repo], readonly=[ASKPASS], network=network, env=env)
        argv, full_env = wrap([git, *SAFE_CONFIG, *args], spec, enabled=self.s.sandbox_enabled)
        out: dict[str, list[str]] = {"stdout": [], "stderr": []}

        async def collect(stream: str, text: str) -> None:
            out[stream].append(text)

        res = await run_step(argv, cwd=str(repo), env=full_env, preexec=make_preexec(Limits(timeout=timeout, memory_mb=1024)),
                             timeout=timeout, memory_limit_mb=1024, on_output=collect, handle=RunningProcess())
        stdout = "".join(out["stdout"])
        stderr = redact("".join(out["stderr"]))
        if res.reason != "ok":
            raise AppError(f"git gagal: {res.message or res.reason}", code="git_error", details={"stderr": stderr[-4000:]})
        return {"exit_code": res.exit_code, "stdout": stdout, "stderr": stderr, "ok": res.exit_code == 0}

    @staticmethod
    def _ensure_repo(repo: Path) -> None:
        if not (repo / ".git").exists():
            raise AppError("Proyek belum menjadi repository Git (jalankan init/clone)", code="not_a_repo")

    async def _remote_host(self, repo: Path, remote: str, user: dict) -> str | None:
        r = await self._git(repo, ["remote", "get-url", remote], user=user)
        url = r["stdout"].strip()
        return urlparse(url).hostname if url.startswith("https://") else None

    async def init(self, repo: Path, user: dict) -> dict:
        return await self._git(repo, ["init"], user=user)

    async def status(self, repo: Path, user: dict) -> dict:
        self._ensure_repo(repo)
        r = await self._git(repo, ["status", "--porcelain=v1", "-b", "-uall"], user=user)
        lines = r["stdout"].splitlines()
        branch = lines[0][3:] if lines and lines[0].startswith("##") else ""
        files = [{"index": l[0], "worktree": l[1], "path": l[3:]} for l in lines[1:] if len(l) > 3]
        return {"branch": branch, "files": files, "clean": not files}

    async def add(self, repo: Path, user: dict, paths: list[str]) -> dict:
        self._ensure_repo(repo)
        from backend.services.file_service import FileService

        safe = [FileService.normalize(p) or "." for p in (paths or ["."])]
        return await self._git(repo, ["add", "--", *safe], user=user)

    async def commit(self, repo: Path, user: dict, message: str, add_all: bool = False) -> dict:
        self._ensure_repo(repo)
        if not message.strip():
            raise AppError("Pesan commit wajib diisi", code="empty_message")
        if add_all:
            await self._git(repo, ["add", "-A"], user=user)
        return await self._git(repo, ["commit", "-m", message], user=user)

    async def log(self, repo: Path, user: dict, limit: int = 50) -> list[dict]:
        self._ensure_repo(repo)
        r = await self._git(repo, ["log", f"-n{min(max(limit, 1), 500)}", "--date=iso-strict",
                                   "--pretty=format:%H%x1f%an%x1f%ae%x1f%ad%x1f%s"], user=user)
        out = []
        for line in r["stdout"].splitlines():
            parts = line.split("\x1f")
            if len(parts) == 5:
                out.append(dict(zip(["hash", "author", "email", "date", "message"], parts)))
        return out

    async def branches(self, repo: Path, user: dict) -> dict:
        self._ensure_repo(repo)
        r = await self._git(repo, ["branch", "-a", "--format=%(HEAD) %(refname:short)"], user=user)
        items = []
        current = None
        for line in r["stdout"].splitlines():
            head, name = line[:1], line[2:].strip()
            if not name:
                continue
            items.append(name)
            if head == "*":
                current = name
        if current is None:  # repo tanpa commit: branch belum muncul di daftar
            h = await self._git(repo, ["symbolic-ref", "--short", "HEAD"], user=user)
            current = h["stdout"].strip() or None
        return {"current": current, "branches": items}

    async def create_branch(self, repo: Path, user: dict, name: str, checkout: bool = True) -> dict:
        self._ensure_repo(repo)
        check_ref(name)
        return await self._git(repo, ["switch", "-c", name] if checkout else ["branch", name], user=user)

    async def checkout(self, repo: Path, user: dict, ref: str) -> dict:
        self._ensure_repo(repo)
        check_ref(ref)
        return await self._git(repo, ["checkout", ref, "--"], user=user)

    async def diff(self, repo: Path, user: dict, staged: bool = False, path: str | None = None) -> dict:
        self._ensure_repo(repo)
        args = ["diff", "--no-color", "--no-ext-diff"] + (["--cached"] if staged else [])
        if path:
            from backend.services.file_service import FileService

            args += ["--", FileService.normalize(path)]
        return await self._git(repo, args, user=user)

    async def head_file(self, repo: Path, user: dict, path: str) -> dict:
        """Isi file pada commit HEAD (untuk penanda baris berubah di editor). tracked=False bila bukan repo/file baru."""
        if not (repo / ".git").exists():
            return {"tracked": False, "repo": False, "content": None}
        from backend.services.file_service import FileService

        rel = FileService.normalize(path)
        r = await self._git(repo, ["show", f"HEAD:{rel}"], user=user, timeout=30)
        if not r["ok"]:
            return {"tracked": False, "repo": True, "content": None}
        return {"tracked": True, "repo": True, "content": r["stdout"]}

    async def set_remote(self, repo: Path, user: dict, name: str, url: str) -> dict:
        self._ensure_repo(repo)
        check_remote(name)
        check_url(url)
        r = await self._git(repo, ["remote"], user=user)
        verb = "set-url" if name in r["stdout"].split() else "add"
        return await self._git(repo, ["remote", verb, name, url], user=user)

    async def pull(self, repo: Path, user: dict, remote: str = "origin", branch: str | None = None) -> dict:
        self._ensure_repo(repo)
        check_remote(remote)
        args = ["pull", "--ff-only", remote] + ([check_ref(branch)] if branch else [])
        host = await self._remote_host(repo, remote, user)
        return await self._git(repo, args, user=user, network=True, host=host, timeout=300)

    async def push(self, repo: Path, user: dict, remote: str = "origin", branch: str | None = None, set_upstream: bool = True) -> dict:
        self._ensure_repo(repo)
        check_remote(remote)
        args = ["push"] + (["-u"] if set_upstream else []) + [remote] + ([check_ref(branch)] if branch else ["HEAD"])
        host = await self._remote_host(repo, remote, user)
        return await self._git(repo, args, user=user, network=True, host=host, timeout=300)

    async def clone(self, target: Path, user: dict, url: str, branch: str | None = None) -> dict:
        check_url(url)
        if target.exists() and any(target.iterdir()):
            raise AppError("Folder tujuan clone harus kosong", code="not_empty")
        target.mkdir(parents=True, exist_ok=True)
        args = ["clone", "--depth", "50"] + (["--branch", check_ref(branch)] if branch else []) + ["--", url, str(target)]
        return await self._git(target, args, user=user, network=True, host=urlparse(url).hostname, timeout=600,
                               writable=[target])
