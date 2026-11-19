from backend.engines.base_engine import BaseEngine, EngineContext, Step


class CEngine(BaseEngine):
    language_id = "c"
    name = "C (GCC)"
    extensions = (".c",)
    executables = ("gcc", "cc")
    compiler_flags = ("-std=c17", "-O2", "-Wall", "-Wextra")
    link_flags = ("-lm",)
    address_space_limit = True

    def build_steps(self, ctx: EngineContext) -> list[Step]:
        exe = self.require()
        return [self.step("build", [exe, *self.compiler_flags, "-o", str(ctx.build_dir / "app"), str(ctx.file), *self.link_flags], ctx)]

    def run_steps(self, ctx: EngineContext) -> list[Step]:
        return self.build_steps(ctx) + [self.step("run", [str(ctx.build_dir / "app"), *ctx.args], ctx)]
