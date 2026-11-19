"""Database Manager (SQLite): buat/buka DB, query baca/tulis terpisah, skema, CSV, backup.

Lokasi database:
  * tanpa project_id  -> workspace/database/<user_id>/<nama>.db (milik pengguna)
  * dengan project_id -> file .db/.sqlite di dalam folder proyek
Operasi destruktif (DROP/DELETE/ALTER/...) wajib mengirim ``confirm=true``.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
import time
from pathlib import Path

from backend.config import Settings
from backend.core.exceptions import AppError, Conflict, NotFound

_NAME_RE = re.compile(r"^[A-Za-z0-9_\-.]{1,64}$")
DB_EXT = (".db", ".sqlite", ".sqlite3")
MAX_ROWS = 1000

DESTRUCTIVE = {
    sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_DROP_INDEX, sqlite3.SQLITE_DROP_VIEW, sqlite3.SQLITE_DROP_TRIGGER,
    sqlite3.SQLITE_DROP_TEMP_TABLE, sqlite3.SQLITE_DROP_TEMP_INDEX, sqlite3.SQLITE_DROP_TEMP_VIEW,
    sqlite3.SQLITE_DROP_TEMP_TRIGGER, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_ALTER_TABLE,
    sqlite3.SQLITE_DROP_VTABLE, sqlite3.SQLITE_DETACH,
}
WRITE_OPS = DESTRUCTIVE | {
    sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_CREATE_INDEX,
    sqlite3.SQLITE_CREATE_VIEW, sqlite3.SQLITE_CREATE_TRIGGER, sqlite3.SQLITE_CREATE_TEMP_TABLE,
    sqlite3.SQLITE_CREATE_VTABLE,
}


def split_statements(sql: str) -> list[str]:
    """Pisahkan SQL menjadi pernyataan utuh (aman untuk ';' di dalam string/trigger)."""
    out, buf = [], ""
    for ch in sql:
        buf += ch
        if ch == ";" and sqlite3.complete_statement(buf):
            if buf.strip().strip(";").strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


class DatabaseService:
    def __init__(self, settings: Settings):
        self.s = settings

    def user_dir(self, user: dict) -> Path:
        d = self.s.database_dir / str(user["id"])
        d.mkdir(parents=True, exist_ok=True)
        return d

    def resolve(self, user: dict, name: str, project_dir: Path | None = None, must_exist: bool = True) -> Path:
        if project_dir is not None:
            from backend.services.file_service import FileService

            p = FileService.__new__(FileService).resolve(project_dir, name, allow_root=False)
        else:
            if not _NAME_RE.match(name or ""):
                raise AppError("Nama database hanya boleh huruf, angka, _ - .", code="bad_name")
            if not name.endswith(DB_EXT):
                name += ".db"
            p = self.user_dir(user) / name
        if must_exist and not p.is_file():
            raise NotFound("Database tidak ditemukan")
        return p

    def list(self, user: dict, project_dir: Path | None = None) -> list[dict]:
        base = project_dir if project_dir is not None else self.user_dir(user)
        out = []
        for p in sorted(base.rglob("*")):
            if p.suffix.lower() in DB_EXT and p.is_file() and ".git" not in p.parts:
                out.append({"name": str(p.relative_to(base)), "size": p.stat().st_size, "modified": p.stat().st_mtime})
        return out

    def create(self, user: dict, name: str, project_dir: Path | None = None) -> dict:
        p = self.resolve(user, name, project_dir, must_exist=False)
        if p.exists():
            raise Conflict("Database sudah ada")
        p.parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(p).close()
        return {"name": name if project_dir is not None else p.name, "size": p.stat().st_size}

    def _connect(self, p: Path, readonly: bool) -> sqlite3.Connection:
        if readonly:
            conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=10)
        else:
            conn = sqlite3.connect(p, timeout=10, isolation_level=None)
        # Cegah ATTACH ke file lain di luar sandbox & load_extension.
        conn.execute("PRAGMA trusted_schema=OFF")
        return conn

    def query(self, p: Path, sql: str, params: list | dict | None = None, mode: str = "read", confirm: bool = False) -> dict:
        stmts = split_statements(sql)
        if not stmts:
            raise AppError("SQL kosong", code="empty_sql")
        readonly = mode != "write"
        conn = self._connect(p, readonly)
        seen: set[int] = set()

        def authorizer(action, arg1, arg2, dbname, source):
            if action == sqlite3.SQLITE_ATTACH:
                return sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_FUNCTION and arg2 and arg2.lower() in ("load_extension", "readfile", "writefile"):
                return sqlite3.SQLITE_DENY
            seen.add(action)
            if readonly and action in WRITE_OPS:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        conn.set_authorizer(authorizer)
        results = []
        start = time.monotonic()
        try:
            if not readonly:
                conn.execute("BEGIN")
            for i, stmt in enumerate(stmts):
                cur = conn.execute(stmt, params if (params and len(stmts) == 1) else ())
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    rows = cur.fetchmany(MAX_ROWS + 1)
                    results.append({
                        "statement": stmt[:200], "columns": cols,
                        "rows": [list(r) for r in rows[:MAX_ROWS]], "truncated": len(rows) > MAX_ROWS,
                    })
                else:
                    results.append({"statement": stmt[:200], "rowcount": max(cur.rowcount, 0)})
            if not readonly:
                if seen & DESTRUCTIVE and not confirm:
                    conn.execute("ROLLBACK")
                    raise Conflict(
                        "Query berisi operasi destruktif (DROP/DELETE/ALTER). Kirim confirm=true untuk melanjutkan.",
                        code="confirmation_required",
                    )
                conn.execute("COMMIT")
        except sqlite3.DatabaseError as e:
            if not readonly and conn.in_transaction:
                conn.execute("ROLLBACK")
            msg = str(e)
            if readonly and "not authorized" in msg:
                msg = "Mode baca tidak mengizinkan perubahan data. Gunakan mode 'write'."
            raise AppError(f"Error SQL: {msg}", code="sql_error")
        finally:
            conn.close()
        return {"results": results, "duration_ms": round((time.monotonic() - start) * 1000, 2), "mode": mode}

    def schema(self, p: Path) -> dict:
        conn = self._connect(p, True)
        try:
            objs = conn.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            ).fetchall()
            tables = []
            for typ, name, tbl, sql in objs:
                entry = {"type": typ, "name": name, "table": tbl, "sql": sql}
                if typ in ("table", "view"):
                    cols = conn.execute(f'PRAGMA table_info("{name.replace(chr(34), "")}")').fetchall()
                    entry["columns"] = [
                        {"cid": c[0], "name": c[1], "type": c[2], "notnull": bool(c[3]), "default": c[4], "pk": bool(c[5])}
                        for c in cols
                    ]
                    if typ == "table":
                        entry["row_count"] = conn.execute(f'SELECT COUNT(*) FROM "{name.replace(chr(34), "")}"').fetchone()[0]
                tables.append(entry)
            return {"objects": tables}
        finally:
            conn.close()

    def export_csv(self, p: Path, table: str) -> str:
        conn = self._connect(p, True)
        try:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
            if table not in names:
                raise NotFound("Tabel tidak ditemukan")
            cur = conn.execute(f'SELECT * FROM "{table}"')
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([d[0] for d in cur.description])
            for row in cur:
                w.writerow(row)
            return buf.getvalue()
        finally:
            conn.close()

    def import_csv(self, p: Path, table: str, data: str, create: bool = True) -> dict:
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$", table):
            raise AppError("Nama tabel tidak valid", code="bad_name")
        rows = list(csv.reader(io.StringIO(data)))
        if not rows:
            raise AppError("CSV kosong", code="empty_csv")
        header, body = rows[0], rows[1:]
        for h in header:
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_ ]{0,63}$", h):
                raise AppError(f"Nama kolom tidak valid: {h!r}", code="bad_column")
        cols = ", ".join(f'"{h}"' for h in header)
        conn = self._connect(p, False)
        try:
            conn.execute("BEGIN")
            if create:
                conn.execute(f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(f"{chr(34)}{h}{chr(34)} TEXT" for h in header)})')
            conn.executemany(f'INSERT INTO "{table}" ({cols}) VALUES ({", ".join("?" for _ in header)})', body)
            conn.execute("COMMIT")
        except sqlite3.DatabaseError as e:
            conn.execute("ROLLBACK")
            raise AppError(f"Import gagal: {e}", code="sql_error")
        finally:
            conn.close()
        return {"table": table, "inserted": len(body)}

    def backup(self, p: Path) -> Path:
        dest_dir = self.s.backups_dir / "databases"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{p.stem}-{time.strftime('%Y%m%d-%H%M%S')}{p.suffix}"
        src = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        chk = sqlite3.connect(dest)
        try:
            if chk.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise AppError("Backup database gagal diverifikasi", code="backup_invalid")
        finally:
            chk.close()
        return dest
