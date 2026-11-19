from backend.engines.base_engine import BaseEngine, EngineContext, Step


class PythonEngine(BaseEngine):
    language_id = "python"
    name = "Python 3"
    extensions = (".py",)
    executables = ("python3", "python")
    address_space_limit = True

    def build_steps(self, ctx: EngineContext) -> list[Step]:
        exe = self.require()
        # Pemeriksaan sintaks; bytecode ditaruh di folder build agar proyek tetap bersih.
        return [self.step("build", [exe, "-c",
                                    "import py_compile,sys; py_compile.compile(sys.argv[1], cfile=sys.argv[2], doraise=True); print('Sintaks OK')",
                                    str(ctx.file), str(ctx.build_dir / "check.pyc")], ctx)]

    def run_steps(self, ctx: EngineContext) -> list[Step]:
        exe = self.require()
        return [self.step("run", [exe, "-u", str(ctx.file), *ctx.args], ctx,
                          env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"})]
