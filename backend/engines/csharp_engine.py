from pathlib import Path

from backend.engines.base_engine import BaseEngine, EngineContext, Step

CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>{tfm}</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
    <AssemblyName>app</AssemblyName>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
    <BaseIntermediateOutputPath>{obj}/</BaseIntermediateOutputPath>
    <SatelliteResourceLanguages>en</SatelliteResourceLanguages>
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="{src}" />
  </ItemGroup>
</Project>
"""


class CSharpEngine(BaseEngine):
    language_id = "csharp"
    name = "C# (.NET)"
    extensions = (".cs",)
    executables = ("dotnet",)

    def _env(self, ctx: EngineContext) -> dict[str, str]:
        exe = self.executable() or ""
        return {
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_NOLOGO": "1",
            "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
            "DOTNET_CLI_HOME": str(ctx.cache_dir / "dotnet-home"),
            "NUGET_PACKAGES": str(ctx.cache_dir / "nuget"),
            "DOTNET_ROOT": str(Path(exe).resolve().parent) if exe else "",
            "DOTNET_GCHeapHardLimit": hex(max(64, ctx.memory_mb - 128) * 1024 * 1024),
        }

    def _tfm(self) -> str:
        ver = (self.get_status().get("version") or "8.0").split(".")
        return f"net{ver[0]}.0" if ver and ver[0].isdigit() else "net8.0"

    def build_steps(self, ctx: EngineContext) -> list[Step]:
        exe = self.require()
        proj_dir = ctx.build_dir / "proj"
        proj_dir.mkdir(parents=True, exist_ok=True)
        csproj = proj_dir / "app.csproj"
        csproj.write_text(CSPROJ.format(tfm=self._tfm(), obj=str(proj_dir / "obj"), src=str(ctx.file)), encoding="utf-8")
        env = self._env(ctx)
        return [self.step("build", [exe, "build", str(csproj), "-o", str(ctx.build_dir / "out"), "-nologo",
                                    "-v", "q", "-clp:NoSummary", "-p:UseSharedCompilation=false"], ctx, cwd=proj_dir, env=env)]

    def run_steps(self, ctx: EngineContext) -> list[Step]:
        exe = self.require()
        return self.build_steps(ctx) + [
            self.step("run", [exe, str(ctx.build_dir / "out" / "app.dll"), *ctx.args], ctx, env=self._env(ctx))
        ]
