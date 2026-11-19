"""Registry engine: memetakan bahasa/ekstensi ke engine."""
from __future__ import annotations

from pathlib import Path

from backend.engines.base_engine import BaseEngine
from backend.engines.c_engine import CEngine
from backend.engines.cpp_engine import CppEngine
from backend.engines.csharp_engine import CSharpEngine
from backend.engines.go_engine import GoEngine
from backend.engines.java_engine import JavaEngine
from backend.engines.javascript_engine import JavaScriptEngine
from backend.engines.php_engine import PhpEngine
from backend.engines.python_engine import PythonEngine
from backend.engines.shell_engine import ShellEngine
from backend.engines.sql_engine import SqlEngine
from backend.engines.web_engine import WebEngine


class EngineRegistry:
    def __init__(self) -> None:
        self._engines: dict[str, BaseEngine] = {}
        for cls in (PythonEngine, JavaScriptEngine, PhpEngine, GoEngine, CEngine, CppEngine,
                    JavaEngine, CSharpEngine, SqlEngine, WebEngine, ShellEngine):
            self.register(cls())

    def register(self, engine: BaseEngine) -> None:
        self._engines[engine.language_id] = engine

    def get(self, language_id: str) -> BaseEngine | None:
        return self._engines.get(language_id)

    def for_file(self, path: str | Path) -> BaseEngine | None:
        ext = Path(path).suffix.lower()
        for e in self._engines.values():
            if ext in e.extensions:
                return e
        return None

    def all(self) -> list[BaseEngine]:
        return list(self._engines.values())

    def statuses(self, refresh: bool = False) -> list[dict]:
        return [e.get_status(refresh=refresh) for e in self._engines.values()]


_registry: EngineRegistry | None = None


def get_registry() -> EngineRegistry:
    global _registry
    if _registry is None:
        _registry = EngineRegistry()
    return _registry
