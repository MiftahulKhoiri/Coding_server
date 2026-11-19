"""Manajemen proyek: setiap proyek adalah folder di workspace/projects/<id>."""
from __future__ import annotations

import re
import secrets
import shutil
import time
from pathlib import Path

from backend.config import Settings
from backend.core.exceptions import Conflict, Forbidden, NotFound
from backend.database.db import Database

TEMPLATES: dict[str, tuple[str, str]] = {
    "python": ("main.py", 'def main():\n    print("Halo dari CODING_SERVER (Python)!")\n\n\nif __name__ == "__main__":\n    main()\n'),
    "javascript": ("main.js", 'console.log("Halo dari CODING_SERVER (Node.js)!");\n'),
    "php": ("main.php", '<?php\necho "Halo dari CODING_SERVER (PHP)!\\n";\n'),
    "go": ("main.go", 'package main\n\nimport "fmt"\n\nfunc main() {\n\tfmt.Println("Halo dari CODING_SERVER (Go)!")\n}\n'),
    "c": ("main.c", '#include <stdio.h>\n\nint main(void) {\n    printf("Halo dari CODING_SERVER (C)!\\n");\n    return 0;\n}\n'),
    "cpp": ("main.cpp", '#include <iostream>\n\nint main() {\n    std::cout << "Halo dari CODING_SERVER (C++)!" << std::endl;\n    return 0;\n}\n'),
    "java": ("Main.java", 'public class Main {\n    public static void main(String[] args) {\n        System.out.println("Halo dari CODING_SERVER (Java)!");\n    }\n}\n'),
    "csharp": ("Program.cs", 'Console.WriteLine("Halo dari CODING_SERVER (C#)!");\n'),
    "sql": ("query.sql", "CREATE TABLE IF NOT EXISTS catatan (id INTEGER PRIMARY KEY, isi TEXT);\nINSERT INTO catatan(isi) VALUES ('Halo dari CODING_SERVER (SQLite)!');\nSELECT * FROM catatan;\n"),
    "web": ("index.html", '<!DOCTYPE html>\n<html lang="id">\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=device-width, initial-scale=1">\n  <title>Halo</title>\n  <link rel="stylesheet" href="style.css">\n</head>\n<body>\n  <h1>Halo dari CODING_SERVER!</h1>\n  <script src="script.js"></script>\n</body>\n</html>\n'),
    "shell": ("main.sh", '#!/usr/bin/env bash\necho "Halo dari CODING_SERVER (Bash)!"\n'),
}
EXTRA_WEB = {"style.css": "body { font-family: sans-serif; padding: 2rem; }\n", "script.js": 'console.log("siap");\n'}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    s = _SLUG_RE.sub("-", name.lower()).strip("-")
    return (s or "proyek")[:40]


class ProjectService:
    def __init__(self, settings: Settings, db: Database):
        self.s = settings
        self.db = db

    def project_dir(self, project_id: str) -> Path:
        return self.s.projects_dir / project_id

    def get(self, project_id: str, user: dict) -> dict:
        p = self.db.one("SELECT * FROM projects WHERE id=?", (project_id,))
        if not p:
            raise NotFound("Proyek tidak ditemukan")
        if p["owner_id"] != user["id"] and "admin" not in user["perms"]:
            raise Forbidden("Bukan proyek milikmu")
        return p

    def list(self, user: dict) -> list[dict]:
        if "admin" in user["perms"]:
            rows = self.db.all("SELECT * FROM projects ORDER BY updated_at DESC")
        else:
            rows = self.db.all("SELECT * FROM projects WHERE owner_id=? ORDER BY updated_at DESC", (user["id"],))
        return [self._decorate(r) for r in rows]

    def _decorate(self, p: dict) -> dict:
        d = self.project_dir(p["id"])
        p = dict(p)
        p["path_exists"] = d.is_dir()
        return p

    def create(self, user: dict, name: str, description: str = "", language: str = "", template: bool = True) -> dict:
        name = name.strip()
        if not name:
            raise Conflict("Nama proyek wajib diisi")
        pid = f"{slugify(name)}-{secrets.token_hex(3)}"
        d = self.project_dir(pid)
        d.mkdir(parents=True, exist_ok=False)
        if template and language in TEMPLATES:
            fname, content = TEMPLATES[language]
            (d / fname).write_text(content, encoding="utf-8")
            if language == "web":
                for f, c in EXTRA_WEB.items():
                    (d / f).write_text(c, encoding="utf-8")
            if language == "go":
                (d / "go.mod").write_text(f"module {slugify(name).replace('-', '_')}\n\ngo 1.21\n", encoding="utf-8")
        now = time.time()
        self.db.execute(
            "INSERT INTO projects(id, name, description, language, owner_id, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
            (pid, name, description, language, user["id"], now, now),
        )
        return self._decorate(self.db.one("SELECT * FROM projects WHERE id=?", (pid,)))

    def update(self, project_id: str, user: dict, name: str | None, description: str | None, language: str | None) -> dict:
        p = self.get(project_id, user)
        self.db.execute(
            "UPDATE projects SET name=?, description=?, language=?, updated_at=? WHERE id=?",
            (name or p["name"], p["description"] if description is None else description,
             p["language"] if language is None else language, time.time(), project_id),
        )
        return self._decorate(self.db.one("SELECT * FROM projects WHERE id=?", (project_id,)))

    def touch(self, project_id: str) -> None:
        self.db.execute("UPDATE projects SET updated_at=? WHERE id=?", (time.time(), project_id))

    def delete(self, project_id: str, user: dict) -> None:
        self.get(project_id, user)
        d = self.project_dir(project_id)
        if d.is_dir() and not d.is_symlink():
            shutil.rmtree(d)
        builds = self.s.cache_dir / "builds" / project_id
        if builds.is_dir():
            shutil.rmtree(builds, ignore_errors=True)
        with self.db.tx() as c:
            c.execute("DELETE FROM projects WHERE id=?", (project_id,))
            c.execute("DELETE FROM favorites WHERE project_id=?", (project_id,))
            c.execute("DELETE FROM recent_files WHERE project_id=?", (project_id,))
