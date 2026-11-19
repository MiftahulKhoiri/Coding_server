from backend.engines.base_engine import BaseEngine, EngineContext, Step, find_executable, java_main_class


class JavaEngine(BaseEngine):
    language_id = "java"
    name = "Java (JDK)"
    extensions = (".java",)
    executables = ("javac",)

    def build_steps(self, ctx: EngineContext) -> list[Step]:
        exe = self.require()
        classes = ctx.build_dir / "classes"
        return [self.step("build", [exe, "-encoding", "UTF-8", "-J-Xmx384m", "-d", str(classes), str(ctx.file)], ctx)]

    def run_steps(self, ctx: EngineContext) -> list[Step]:
        java = find_executable("java")
        if not java:
            self.require()
        main = java_main_class(ctx.file.read_text(encoding="utf-8", errors="replace"), ctx.file.stem)
        heap = max(64, ctx.memory_mb - 192)
        return self.build_steps(ctx) + [
            self.step("run", [java, f"-Xmx{heap}m", "-XX:+UseSerialGC", "-cp", str(ctx.build_dir / "classes"), main, *ctx.args], ctx)
        ]
