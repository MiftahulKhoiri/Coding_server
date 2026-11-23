"""C/C++ multi-file: otomatis, beberapa main(), Makefile (dengan/tanpa target run), CMake. Dijalankan nyata di sandbox."""
import pytest

from backend.engines.base_engine import find_executable
from backend.engines.registry import get_registry
from backend.tests.conftest import wait_job

pytestmark = pytest.mark.skipif(get_registry().get("cpp").get_status()["status"] != "AVAILABLE", reason="g++ tidak ada")

HDR = "#pragma once\nint add(int a, int b);\n"
LIB = '#include "mathx.h"\nint add(int a, int b) { return a + b; }\n'
MAIN = '#include <iostream>\n#include "mathx.h"\nint main(int argc, char** argv) {\n  std::cout << "jumlah " << add(40, 2) << " argc " << argc << std::endl;\n}\n'


def put(client, auth, project, path, content):
    r = client.put("/api/v1/files/write", json={"project_id": project, "path": path, "content": content}, headers=auth)
    assert r.status_code == 200, r.text


def run(client, auth, project, path, action="run", args=None):
    r = client.post(f"/api/v1/execution/{action}", json={"project_id": project, "path": path, "args": args or []}, headers=auth)
    assert r.status_code in (202, 400), r.text
    if r.status_code == 400:
        return r.json()["error"]
    return wait_job(client, auth, r.json()["process_id"])


def test_auto_multifile_and_subfolders(client, auth, project):
    put(client, auth, project, "app/mathx.h", HDR)
    put(client, auth, project, "app/lib/mathx.cpp", LIB)  # subfolder ikut dikompilasi
    put(client, auth, project, "app/main.cpp", MAIN)
    job = run(client, auth, project, "app/main.cpp")
    assert job["status"] == "COMPLETED", job
    assert "jumlah 42" in job["stdout"]
    # menjalankan dari file non-main memakai satu-satunya main()
    job = run(client, auth, project, "app/lib/mathx.cpp")
    assert job["status"] == "COMPLETED" and "jumlah 42" in job["stdout"], job


def test_exercise_folder_with_many_mains(client, auth, project):
    put(client, auth, project, "latihan/a.cpp", '#include <cstdio>\nint main(){ puts("program A"); }\n')
    put(client, auth, project, "latihan/b.cpp", '#include <cstdio>\n// int main() di komentar tidak dihitung\nint main(){ puts("program B"); }\n')
    put(client, auth, project, "latihan/util.cpp", "int helper(){ return 1; }\n")
    job = run(client, auth, project, "latihan/b.cpp")
    assert job["status"] == "COMPLETED" and "program B" in job["stdout"] and "program A" not in job["stdout"], job
    err = run(client, auth, project, "latihan/util.cpp")
    assert err["code"] == "multiple_mains" and "a.cpp" in err["message"]


@pytest.mark.skipif(not find_executable("make"), reason="make tidak ada")
def test_makefile_with_and_without_run_target(client, auth, project):
    mk = ("CXX ?= g++\nall: hello\nhello: main.o mathx.o\n\t$(CXX) -o hello main.o mathx.o\n"
          "%.o: %.cpp\n\t$(CXX) -c $< -o $@\n")
    put(client, auth, project, "mk/mathx.h", HDR)
    put(client, auth, project, "mk/mathx.cpp", LIB)
    put(client, auth, project, "mk/main.cpp", MAIN)
    put(client, auth, project, "mk/Makefile", mk)
    job = run(client, auth, project, "mk/main.cpp", args=["x", "y"])
    assert job["status"] == "COMPLETED", job
    assert "jumlah 42 argc 3" in job["stdout"], job          # binary terbaru dijalankan dengan argumen
    put(client, auth, project, "mk/Makefile", mk + "run: hello\n\t./hello $(ARGS)\n")
    job = run(client, auth, project, "mk/main.cpp", args=["a"])
    assert job["status"] == "COMPLETED" and "jumlah 42 argc 2" in job["stdout"], job
    # error kompilasi lewat make -> FAILED dengan pesan compiler
    put(client, auth, project, "mk/mathx.cpp", "int add(int a, int b) { return a + }\n")
    job = run(client, auth, project, "mk/main.cpp", action="build")
    assert job["status"] == "FAILED" and "error" in job["stderr"].lower(), job


@pytest.mark.skipif(not find_executable("cmake"), reason="cmake tidak ada")
def test_cmake_project(client, auth, project):
    put(client, auth, project, "cm/CMakeLists.txt",
        "cmake_minimum_required(VERSION 3.13)\nproject(demo CXX)\nadd_library(mathx src/mathx.cpp)\n"
        "target_include_directories(mathx PUBLIC include)\nadd_executable(demo src/main.cpp)\ntarget_link_libraries(demo mathx)\n")
    put(client, auth, project, "cm/include/mathx.h", HDR)
    put(client, auth, project, "cm/src/mathx.cpp", LIB)
    put(client, auth, project, "cm/src/main.cpp", MAIN)
    job = run(client, auth, project, "cm/src/main.cpp", args=["1"])
    assert job["status"] == "COMPLETED", job
    assert "jumlah 42 argc 2" in job["stdout"], job
    assert "cmake" in job["command"][0][0] or any("cmake" in a for a in job["command"][0]), job["command"]
    # build kedua (inkremental) tetap berhasil
    job = run(client, auth, project, "cm/src/main.cpp")
    assert job["status"] == "COMPLETED", job
