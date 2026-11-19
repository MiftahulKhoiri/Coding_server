from pathlib import Path

from backend.engines.base_engine import BaseEngine, EngineContext, Step


class GoEngine(BaseEngine):
    language_id = "go"
    name = "Go"
    extensions = (".go",)
    executables = ("go",)
    version_args = ("version",)

    def _env(self, ctx: EngineContext) -> dict[str, str]:
        return {
            "GOCACHE": str(ctx.cache_dir / "go-build"),
            "GOPATH": str(ctx.cache_dir / "gopath"),
            "GOTOOLCHAIN": "local",
            "GOTELEMETRY": "off",
            "GOFLAGS": "-buildvcs=false",
            **({} if ctx.network else {"GOPROXY": "off"}),
        }

    def _module_root(self, ctx: EngineContext) -> Path | None:
        d = ctx.file.parent
        while True:
            if (d / "go.mod").is_file():
                return d
            if d == ctx.project_dir or d.parent == d:
                return None
            d = d.parent

    def build_steps(self, ctx: EngineContext) -> list[Step]:
        exe = self.require()
        out = str(ctx.build_dir / "app")
        root = self._module_root(ctx)
        if root:
            pkg = "./" + str(ctx.file.parent.relative_to(root)) if ctx.file.parent != root else "."
            return [self.step("build", [exe, "build", "-o", out, pkg], ctx, cwd=root, env=self._env(ctx))]
        return [self.step("build", [exe, "build", "-o", out, str(ctx.file)], ctx, env=self._env(ctx))]

    def run_steps(self, ctx: EngineContext) -> list[Step]:
        return self.build_steps(ctx) + [self.step("run", [str(ctx.build_dir / "app"), *ctx.args], ctx)]
