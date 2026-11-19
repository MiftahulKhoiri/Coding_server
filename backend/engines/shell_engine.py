from backend.engines.base_engine import BaseEngine, EngineContext, Step


class ShellEngine(BaseEngine):
    language_id = "shell"
    name = "Shell Script (Bash)"
    extensions = (".sh", ".bash")
    executables = ("bash",)

    def build_steps(self, ctx: EngineContext) -> list[Step]:
        return [self.step("build", [self.require(), "-n", str(ctx.file)], ctx)]

    def run_steps(self, ctx: EngineContext) -> list[Step]:
        return [self.step("run", [self.require(), str(ctx.file), *ctx.args], ctx)]
