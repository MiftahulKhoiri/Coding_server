"""Backup & restore.

Isi backup: proyek, database pengguna, metadata (snapshot SQLite yang konsisten), riwayat
file, dan konfigurasi. Cache compiler & file sementara tidak ikut.

Alur aman: tulis ke ``.partial`` -> verifikasi (baca ulang + cocokkan SHA-256 manifest)
-> rename final -> baru hapus backup lama sesuai retensi. Backup valid terakhir tidak
pernah ditimpa/dihapus sebelum backup baru terbukti valid.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path

from backend.config import VERSION, Settings
from backend.core.exceptions import AppError, NotFound
from backend.core.logging import get_logger

log = get_logger("backup")
EXCLUDE_DIRS = {"node_modules", "__pycache__", ".pytest_cache", ".gradle", "bin", "obj"}
EXCLUDE_SUFFIX = (".tmp", ".pyc", ".o")


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class BackupService:
    def __init__(self, settings: Settings):
        self.s = settings
        self._lock = asyncio.Lock()

    def _sources(self) -> list[tuple[Path, str]]:
        s = self.s
        out = [(s.projects_dir, "workspace/projects"), (s.database_dir, "workspace/database"),
               (s.history_dir, "workspace/history"), (s.data_dir, "workspace/data")]
        cfg = s.base_dir / "deployment" / "configuration"
        if cfg.is_dir():
            out.append((cfg, "deployment/configuration"))
        return out

    def _iter_files(self, root: Path):
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
            for fn in filenames:
                if fn.endswith(EXCLUDE_SUFFIX):
                    continue
                p = Path(dirpath) / fn
                if p.is_symlink() or not p.is_file():
                    continue
                yield p

    SECRET_FILES = ("secret.key", "initial_admin_password.txt")

    def _metadata_extras(self):
        """File metadata selain database: sandi admin utama dan folder avatars/ (foto profil)."""
        pw = self.s.metadata_dir / "initial_admin_password.txt"
        if pw.is_file() and not pw.is_symlink():
            yield pw
        av = self.s.metadata_dir / "avatars"
        if av.is_dir() and not av.is_symlink():
            for f in self._iter_files(av):
                if f.suffix == ".img":  # lewati sisa .tmp dari unggahan yang terputus
                    yield f

    def create_sync(self, label: str = "manual") -> dict:
        s = self.s
        s.backups_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(s.backups_dir, 0o700)
        ts = time.strftime("%Y%m%d-%H%M%S")
        name = f"coding_server-{ts}-{label}.tar.gz"
        final = s.backups_dir / name
        partial = s.backups_dir / (name + ".partial")
        manifest: dict[str, str] = {}
        with tempfile.TemporaryDirectory(dir=s.backups_dir) as tmp:
            # Snapshot konsisten database metadata (aman walau server sedang berjalan).
            meta_snap = Path(tmp) / "coding_server.db"
            src = sqlite3.connect(f"file:{s.metadata_dir / 'coding_server.db'}?mode=ro", uri=True)
            dst = sqlite3.connect(meta_snap)
            src.backup(dst)
            src.close()
            dst.close()
            with tarfile.open(partial, "w:gz", compresslevel=6) as tar:
                tar.add(meta_snap, arcname="workspace/metadata/coding_server.db")
                manifest["workspace/metadata/coding_server.db"] = _sha256_file(meta_snap)
                key = s.metadata_dir / "secret.key"
                if key.is_file():
                    tar.add(key, arcname="workspace/metadata/secret.key")
                    manifest["workspace/metadata/secret.key"] = _sha256_file(key)
                # Sumber sandi admin utama (akun pemulihan) & foto profil pengguna.
                for f in self._metadata_extras():
                    arcname = f"workspace/metadata/{f.relative_to(s.metadata_dir).as_posix()}"
                    manifest[arcname] = _sha256_file(f)
                    tar.add(f, arcname=arcname, recursive=False)
                for root, arc in self._sources():
                    if not root.is_dir():
                        continue
                    for f in self._iter_files(root):
                        arcname = f"{arc}/{f.relative_to(root).as_posix()}"
                        manifest[arcname] = _sha256_file(f)
                        tar.add(f, arcname=arcname, recursive=False)
                meta = {"version": VERSION, "created_at": time.time(), "label": label, "files": manifest}
                data = json.dumps(meta, indent=1).encode()
                ti = tarfile.TarInfo("MANIFEST.json")
                ti.size = len(data)
                ti.mtime = int(time.time())
                tar.addfile(ti, io.BytesIO(data))
        try:
            self.verify_path(partial)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        os.replace(partial, final)
        os.chmod(final, 0o600)
        (s.backups_dir / (name + ".sha256")).write_text(f"{_sha256_file(final)}  {name}\n")
        self._apply_retention()
        log.info("Backup dibuat: %s (%d file)", name, len(manifest))
        return self._describe(final)

    async def create(self, label: str = "manual") -> dict:
        async with self._lock:
            return await asyncio.to_thread(self.create_sync, label)

    def _apply_retention(self) -> None:
        backups = sorted(self.s.backups_dir.glob("coding_server-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[max(1, self.s.backup_retention):]:
            old.unlink(missing_ok=True)
            Path(str(old) + ".sha256").unlink(missing_ok=True)

    def _describe(self, p: Path) -> dict:
        return {"name": p.name, "size": p.stat().st_size, "created_at": p.stat().st_mtime}

    def list(self) -> list[dict]:
        return [self._describe(p) for p in sorted(self.s.backups_dir.glob("coding_server-*.tar.gz"),
                                                    key=lambda p: p.stat().st_mtime, reverse=True)]

    def path_of(self, name: str) -> Path:
        if "/" in name or not name.startswith("coding_server-") or not name.endswith(".tar.gz"):
            raise AppError("Nama backup tidak valid", code="bad_name")
        p = self.s.backups_dir / name
        if not p.is_file():
            raise NotFound("Backup tidak ditemukan")
        return p

    @staticmethod
    def verify_path(p: Path) -> dict:
        with tarfile.open(p, "r:gz") as tar:
            mf = tar.extractfile("MANIFEST.json")
            if mf is None:
                raise AppError("MANIFEST.json tidak ada", code="backup_invalid")
            meta = json.loads(mf.read())
            checked = 0
            for m in tar.getmembers():
                if m.name == "MANIFEST.json":
                    continue
                if not m.isfile() or m.name.startswith("/") or ".." in Path(m.name).parts:
                    raise AppError(f"Entri tidak aman di backup: {m.name}", code="backup_invalid")
                f = tar.extractfile(m)
                h = hashlib.sha256()
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
                if meta["files"].get(m.name) != h.hexdigest():
                    raise AppError(f"Checksum tidak cocok: {m.name}", code="backup_invalid")
                checked += 1
            if checked != len(meta["files"]):
                raise AppError("Jumlah file tidak sesuai manifest", code="backup_invalid")
        return {"valid": True, "files": checked, "version": meta.get("version"), "created_at": meta.get("created_at")}

    def verify(self, name: str) -> dict:
        return self.verify_path(self.path_of(name))

    def restore_sync(self, name: str, include_metadata: bool = False) -> dict:
        """Pulihkan proyek, database, riwayat & data. Metadata (user/proyek) hanya bila
        include_metadata=True — sebaiknya dilakukan saat server berhenti (scripts/backup.py restore)."""
        p = self.path_of(name)
        self.verify_path(p)
        s = self.s
        stamp = time.strftime("%Y%m%d-%H%M%S")
        staging = s.workspace_dir / f".restore-{stamp}"
        staging.mkdir()
        try:
            with tarfile.open(p, "r:gz") as tar:
                tar.extractall(staging, filter="data")
            targets = {"workspace/projects": s.projects_dir, "workspace/database": s.database_dir,
                       "workspace/history": s.history_dir, "workspace/data": s.data_dir}
            if include_metadata:
                targets["workspace/metadata"] = s.metadata_dir
            old_root = s.backups_dir / f"pre-restore-{stamp}"
            restored = []
            for arc, dest in targets.items():
                src = staging / arc
                if not src.exists():
                    continue
                old_root.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    shutil.move(str(dest), str(old_root / dest.name))
                shutil.move(str(src), str(dest))
                restored.append(arc)
            for d in (s.projects_dir, s.database_dir, s.history_dir, s.data_dir, s.metadata_dir):
                d.mkdir(parents=True, exist_ok=True)
            if "workspace/metadata" in restored:
                # tar filter="data" bisa melonggarkan izin; file rahasia wajib 0600 lagi.
                for fn in self.SECRET_FILES:
                    f = s.metadata_dir / fn
                    if f.is_file():
                        os.chmod(f, 0o600)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        log.info("Restore dari %s: %s", name, restored)
        return {"restored": restored, "previous_data": str(old_root), "restart_required": include_metadata}

    async def restore(self, name: str, include_metadata: bool = False) -> dict:
        async with self._lock:
            return await asyncio.to_thread(self.restore_sync, name, include_metadata)

    async def scheduler(self, hour: int = 3) -> None:
        """Backup otomatis harian pada jam tertentu (waktu lokal server)."""
        while True:
            now = time.localtime()
            target = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, hour, 0, 0, 0, 0, -1))
            if target <= time.time():
                target += 86400
            await asyncio.sleep(target - time.time())
            try:
                await self.create("scheduled")
            except Exception as e:
                log.error("Backup terjadwal gagal: %s", e)
