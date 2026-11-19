import sys
from pathlib import Path

from backend.engines.base_engine import BaseEngine, EngineContext, Step

RUNNER = Path(__file__).with_name("sql_runner.py")


class SqlEngine(BaseEngine):
    """Menjalankan file .sql ke database SQLite proyek (default: <nama_file>.db di folder yang sama)."""

    language_id = "sql"
    name = "SQL (SQLite)"
    extensions = (".sql",)
    executables = ()
    address_space_limit = True

    def executable(self) -> str | None:
        return sys.executable

    def get_version(self) -> str | None:
        import sqlite3

        return f"SQLite {sqlite3.sqlite_version}"

    def _db(self, ctx: EngineContext) -> list[str]:
        args = list(ctx.args)
        db = ctx.file.with_suffix(".db")
        if len(args) >= 2 and args[0] == "--db":
            db = (ctx.file.parent / args[1]).resolve()
            db.relative_to(ctx.project_dir)  # tolak path di luar proyek
        return [str(db)]

    def build_steps(self, ctx: EngineContext) -> list[Step]:
        return [self.step("build", [sys.executable, "-I", str(RUNNER), "--check", str(ctx.file), *self._db(ctx)], ctx)]

    def run_steps(self, ctx: EngineContext) -> list[Step]:
        return [self.step("run", [sys.executable, "-I", str(RUNNER), str(ctx.file), *self._db(ctx)], ctx)]
