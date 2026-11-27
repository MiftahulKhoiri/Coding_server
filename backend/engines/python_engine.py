from backend.engines.base_engine import BaseEngine, EngineContext, Step

# Dijalankan di sandbox. Duplikat def/class tingkat atas hampir selalu bug (mis. route Flask ganda →
# "View function mapping is overwriting an existing endpoint"), padahal lolos py_compile.
# Format "file:baris:" supaya error bisa diklik di layar Output.
CHECK_SCRIPT = r"""
import ast, py_compile, sys
src, pyc = sys.argv[1], sys.argv[2]
py_compile.compile(src, cfile=pyc, doraise=True)
tree = ast.parse(open(src, encoding='utf-8').read(), src)
seen, bad = {}, 0
for n in tree.body:
    if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        continue
    decos = [ast.unparse(d) for d in getattr(n, 'decorator_list', [])]
    if any('overload' in d or d.endswith('.setter') or d.endswith('.deleter') for d in decos):
        continue
    if n.name in seen:
        print(f"{src}:{n.lineno}: error: '{n.name}' didefinisikan ulang (pertama di baris {seen[n.name]}); "
              f"definisi lama tertimpa", file=sys.stderr)
        bad += 1
    else:
        seen[n.name] = n.lineno
if bad:
    sys.exit(1)
print('Sintaks OK')
"""


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
        # Pemeriksaan sintaks + fungsi/kelas tingkat atas yang didefinisikan dua kali (tanpa menjalankan kode).
        # Bytecode ditaruh di folder build agar proyek tetap bersih.
        return [self.step("build", [exe, "-c", CHECK_SCRIPT, str(ctx.file), str(ctx.build_dir / "check.pyc")], ctx)]

    def run_steps(self, ctx: EngineContext) -> list[Step]:
        exe = self.interpreter(ctx)
        return [self.step("run", [exe, "-u", str(ctx.file), *ctx.args], ctx,
                          env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"})]
