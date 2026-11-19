from backend.engines.base_engine import BaseEngine, EngineContext, Step


class PhpEngine(BaseEngine):
    language_id = "php"
    name = "PHP CLI"
    extensions = (".php",)
    executables = ("php",)
    address_space_limit = True

    def build_steps(self, ctx: EngineContext) -> list[Step]:
        return [self.step("build", [self.require(), "-l", str(ctx.file)], ctx)]

    def run_steps(self, ctx: EngineContext) -> list[Step]:
        return [self.step("run", [self.require(), "-d", f"memory_limit={ctx.memory_mb}M", str(ctx.file), *ctx.args], ctx)]
