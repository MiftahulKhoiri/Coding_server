from backend.engines.c_engine import CEngine


class CppEngine(CEngine):
    language_id = "cpp"
    name = "C++ (G++)"
    extensions = (".cpp", ".cc", ".cxx")
    source_exts = (".cpp", ".cc", ".cxx", ".c++")
    executables = ("g++", "c++")
    compiler_flags = ("-std=c++17", "-O2", "-Wall", "-Wextra")
    link_flags = ("-pthread",)
