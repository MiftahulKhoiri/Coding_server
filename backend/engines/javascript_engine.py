from backend.engines.base_engine import BaseEngine, EngineContext, Step


class JavaScriptEngine(BaseEngine):
    language_id = "javascript"
    name = "JavaScript (Node.js)"
    extensions = (".js", ".mjs", ".cjs")
    executables = ("node", "nodejs")

    def build_steps(self, ctx: EngineContext) -> list[Step]:
        return [self.step("build", [self.require(), "--check", str(ctx.file)], ctx)]

    def run_steps(self, ctx: EngineContext) -> list[Step]:
        heap = max(64, ctx.memory_mb - 128)
        return [self.step("run", [self.require(), f"--max-old-space-size={heap}", str(ctx.file), *ctx.args], ctx)]
