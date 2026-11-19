from backend.engines.base_engine import BaseEngine, EngineContext, Step


class WebEngine(BaseEngine):
    """HTML/CSS tidak dieksekusi di server; 'run' menghasilkan URL pratinjau untuk WebView/browser."""

    language_id = "web"
    name = "HTML/CSS (Browser)"
    extensions = (".html", ".htm", ".css")
    executables = ()
    can_build = False

    def executable(self) -> str | None:
        return "browser"

    def get_version(self) -> str | None:
        return "Pratinjau statis lewat browser"

    def build_steps(self, ctx: EngineContext) -> list[Step]:
        return []

    def run_steps(self, ctx: EngineContext) -> list[Step]:
        return []
