"""Build Manager: daftar artefak hasil build per proyek dan pembersihan cache build."""
from __future__ import annotations

import shutil
from pathlib import Path

from backend.config import Settings


class BuildService:
    def __init__(self, settings: Settings):
        self.s = settings

    def build_root(self, project_id: str) -> Path:
        return self.s.cache_dir / "builds" / project_id

    def artifacts(self, project_id: str) -> list[dict]:
        root = self.build_root(project_id)
        out = []
        if root.is_dir():
            for p in sorted(root.rglob("*")):
                if p.is_file() and (p.name in ("app", "app.dll") or p.suffix in (".class", ".jar", ".exe")):
                    out.append({"path": str(p.relative_to(root)), "size": p.stat().st_size, "modified": p.stat().st_mtime,
                                "location": str(p)})
        return out

    def clean(self, project_id: str) -> dict:
        root = self.build_root(project_id)
        size = sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) if root.is_dir() else 0
        shutil.rmtree(root, ignore_errors=True)
        return {"freed_bytes": size}
