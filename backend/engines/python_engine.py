from backend.engines.base_engine import BaseEngine, EngineContext, Step


class PythonEngine(BaseEngine):
    language_id = "python"
    name = "Python 3"
    extensions = (".py",)
    executables = ("python3", "python")
    address_space_limit = True

    def interpreter(self, ctx: EngineContext) -> str:
        """Pakai virtualenv proyek (.venv/ atau venv/, hasil install_deps) bila ada; bila tidak, Python sistem."""
        from backend.services.deps_install import project_python

        venv = project_python(ctx.project_dir)
        if venv is not None:
            self.require()  # pastikan Python sistem (target symlink venv) memang ada
            return str(venv)
        return self.require()

    def build_steps(self, ctx: EngineContext) -> list[Step]:
        exe = self.interpreter(ctx)
        # Pemeriksaan sintaks; bytecode ditaruh di folder build agar proyek tetap bersih.
        return [self.step("build", [exe, "-c",
                                    "import py_compile,sys; py_compile.compile(sys.argv[1], cfile=sys.argv[2], doraise=True); print('Sintaks OK')",
                                    str(ctx.file), str(ctx.build_dir / "check.pyc")], ctx)]

    def run_steps(self, ctx: EngineContext) -> list[Step]:
        exe = self.interpreter(ctx)
        return [self.step("run", [exe, "-u", str(ctx.file), *ctx.args], ctx,
                          env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"})]
