"""Tool registry untuk AI Coding Agent.

Setiap tool punya skema argumen, validasi, izin (dicek terhadap irisan hak pengguna & peran
'ai'), batas waktu, dan logging lewat event task. Tool tidak pernah memberi model akses
langsung ke shell: perubahan file selalu menjadi proposal (Approval Center), eksekusi selalu
lewat ExecutionService (antrean + sandbox fail-closed), perintah uji disusun server.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from backend.core.exceptions import AppError
from backend.services.ai_edits import Edit
from backend.services.file_service import FileService, detect_language
from backend.services.test_detect import detect as detect_tests

MAX_OBS = 12_000  # karakter maksimum hasil tool yang dikirim ke model
_SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist", ".gradle", "target", "bin", "obj"}


class NeedsApproval(Exception):
    """Ada proposal yang belum diputuskan; task menunggu sebelum menjalankan/menguji kode."""


class ToolError(Exception):
    pass


@dataclass
class Arg:
    type: str  # string | integer | boolean | array | object
    required: bool = False
    description: str = ""


@dataclass
class Tool:
    name: str
    description: str
    perm: str
    stage: str
    args: dict[str, Arg] = field(default_factory=dict)
    timeout: float = 60.0
    handler: Callable[["ToolContext", dict], Awaitable[str]] | None = None

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description, "permission": self.perm,
                "args": {k: {"type": a.type, "required": a.required, "description": a.description}
                         for k, a in self.args.items()}}

    def validate(self, args: Any) -> dict:
        if not isinstance(args, dict):
            raise ToolError("args harus objek JSON")
        unknown = set(args) - set(self.args)
        if unknown:
            raise ToolError(f"Argumen tidak dikenal: {', '.join(sorted(unknown))}")
        py = {"string": str, "integer": int, "boolean": bool, "array": list, "object": dict}
        out = {}
        for k, a in self.args.items():
            if k not in args or args[k] is None:
                if a.required:
                    raise ToolError(f"Argumen wajib '{k}' tidak ada")
                continue
            v = args[k]
            if a.type == "integer" and isinstance(v, str) and v.strip().lstrip("-").isdigit():
                v = int(v)
            if not isinstance(v, py[a.type]) or (a.type == "integer" and isinstance(v, bool)):
                raise ToolError(f"Argumen '{k}' harus {a.type}")
            out[k] = v
        return out


@dataclass
class ToolContext:
    svc: Any  # backend.dependencies.Services
    user: dict
    task: dict
    root: Path
    ai_perms: set[str]
    code_block: str | None = None  # blok kode setelah JSON (isi file untuk write/edit)

    @property
    def project_id(self) -> str:
        return self.task["project_id"]


def clip(text: str, limit: int = MAX_OBS) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit * 2 // 3]
    tail = text[-limit // 3:]
    return f"{head}\n…[dipotong {len(text) - limit} karakter]…\n{tail}"


# ---------------- inspeksi ----------------
async def _project_info(ctx: ToolContext, _: dict) -> str:
    langs: Counter[str] = Counter()
    files = 0
    markers = []
    for p in ctx.root.rglob("*"):
        rel = p.relative_to(ctx.root)
        if any(part in _SKIP for part in rel.parts) or p.is_symlink() or not p.is_file():
            continue
        files += 1
        lang = detect_language(p.name)
        if lang and lang not in ("plaintext", "text"):
            langs[lang] += 1
        if p.name in ("CMakeLists.txt", "Makefile", "package.json", "go.mod", "pyproject.toml", "requirements.txt",
                      "setup.py", "build.gradle", "build.gradle.kts", "pom.xml", "Cargo.toml", "composer.json"):
            markers.append(str(rel))
        if files > 20000:
            break
    tests = detect_tests(ctx.root, ctx.svc.settings.cache_dir / "lang")
    lines = [f"Jumlah file: {files}",
             "Bahasa: " + (", ".join(f"{k} ({v})" for k, v in langs.most_common(8)) or "-"),
             "File build/dependensi: " + (", ".join(markers[:20]) or "-"),
             "Perintah uji terdeteksi: " + (", ".join(f"{t.id} → {' '.join(t.argv[1:]) or t.argv[0]}"
                                                       for t in tests) or "tidak ada"),
             "Repo git: " + ("ya" if (ctx.root / ".git").is_dir() else "tidak")]
    return "\n".join(lines)


async def _list_dir(ctx: ToolContext, a: dict) -> str:
    depth = max(1, min(int(a.get("depth", 2)), 4))
    tree = ctx.svc.files.tree(ctx.root, a.get("path", ""), depth=depth, show_hidden=False)
    out: list[str] = []

    def walk(node: dict, indent: int) -> None:
        for ch in node.get("children") or []:
            if ch["name"] in _SKIP:
                continue
            suffix = "/" if ch["type"] == "folder" else f"  ({ch['size']} B)"
            out.append("  " * indent + ch["name"] + suffix)
            if len(out) > 400:
                return
            walk(ch, indent + 1)

    walk(tree, 0)
    return "\n".join(out) or "(folder kosong)"


async def _read_file(ctx: ToolContext, a: dict) -> str:
    f = ctx.svc.files.read(ctx.root, a["path"])
    if f.get("binary"):
        return f"{f['path']} adalah file biner ({f['size']} byte); tidak ditampilkan."
    lines = f["content"].splitlines()
    start = max(1, int(a.get("start_line", 1)))
    end = min(len(lines), int(a.get("end_line", start + 399)))
    body = "\n".join(f"{i:>5}| {lines[i - 1]}" for i in range(start, end + 1))
    more = f"\n[baris {start}-{end} dari {len(lines)}; minta start_line={end + 1} untuk lanjut]" if end < len(lines) else ""
    return clip(f"File {f['path']} ({len(lines)} baris, sha256 {f['sha256'][:12]}):\n{body}{more}")


async def _search(ctx: ToolContext, a: dict) -> str:
    res = ctx.svc.files.search(ctx.root, a["query"], content=a.get("content", True), path=a.get("path", ""), limit=60)
    if not res:
        return "Tidak ada hasil."
    rows = [f"{r['path']}:{r['line']}: {r['text']}" if "line" in r else r["path"] for r in res]
    return clip("\n".join(rows))


# ---------------- rencana ----------------
async def _update_plan(ctx: ToolContext, a: dict) -> str:
    steps = []
    for i, s in enumerate(a["steps"][:30], 1):
        if not isinstance(s, dict) or not str(s.get("description", "")).strip():
            raise ToolError("Setiap langkah butuh 'description'")
        status = str(s.get("status", "pending")).lower()
        if status not in ("pending", "in_progress", "done", "skipped", "failed"):
            status = "pending"
        files = s.get("files") or []
        steps.append({"id": str(s.get("id") or i)[:20], "description": str(s["description"])[:400],
                      "files": [str(x)[:300] for x in files][:20] if isinstance(files, list) else [],
                      "depends_on": [str(x)[:20] for x in (s.get("depends_on") or [])][:10]
                      if isinstance(s.get("depends_on"), list) else [],
                      "risk": str(s.get("risk", "MEDIUM")).upper()[:6],
                      "verification": str(s.get("verification", ""))[:300], "status": status})
    ctx.task["_plan"] = steps
    done = sum(1 for s in steps if s["status"] in ("done", "skipped"))
    return f"Rencana disimpan: {len(steps)} langkah ({done} selesai)."


# ---------------- perubahan file (selalu lewat proposal) ----------------
def _after_proposal(ctx: ToolContext, row: dict) -> str:
    svc = ctx.svc
    if row["status"] == "failed":
        raise ToolError(f"Editan tidak bisa dibuat: {row['error']}")
    msg = f"Proposal #{row['id']} untuk {row['path']} (+{row['additions']}/-{row['deletions']}, risiko {row['risk']})"
    full = svc.ai.agent_models().get("approval_mode") == "penuh"
    if ctx.task.get("auto_apply") and (row["risk"] != "HIGH" or (full and row["action"] == "write")):
        try:
            # Mode izin "penuh": risiko TINGGI juga diterapkan (tetap tercatat & bisa dibatalkan di Approval Center).
            svc.ai.decide(ctx.user, ctx.project_id, ctx.root, row["id"], True, confirm_high_risk=full)
            return msg + " DITERAPKAN otomatis (bisa dibatalkan di Approval Center)."
        except AppError as e:
            svc.db.execute("UPDATE ai_proposals SET status='failed', error=? WHERE id=?", (e.message, row["id"]))
            raise ToolError(f"Gagal menerapkan: {e.message}")
    return msg + " dibuat dan MENUNGGU persetujuan pengguna; file belum berubah sampai disetujui."


async def _write_file(ctx: ToolContext, a: dict) -> str:
    content = a.get("content")
    if content is None:
        content = ctx.code_block
    if content is None:
        raise ToolError("Isi file tidak ada: isi args.content atau tulis blok kode tepat setelah JSON")
    row = ctx.svc.ai.propose_edit(ctx.user, ctx.project_id, ctx.root, Edit(a["path"], "full", content=content),
                                  reason=a.get("reason", "")[:300] or "agent", task_id=ctx.task["id"])
    return _after_proposal(ctx, row)


async def _edit_file(ctx: ToolContext, a: dict) -> str:
    blocks: list[tuple[str, str]] = []
    if "search" in a:
        blocks.append((a["search"], a.get("replace", "")))
    elif ctx.code_block:
        from backend.services.ai_edits import parse_edits

        parsed = parse_edits(f"```edit file={a['path']}\n{ctx.code_block}```")
        for e in parsed:
            blocks.extend(e.blocks)
    if not blocks:
        raise ToolError("Butuh args.search & args.replace, atau blok SEARCH/REPLACE setelah JSON")
    row = ctx.svc.ai.propose_edit(ctx.user, ctx.project_id, ctx.root, Edit(a["path"], "replace", blocks=blocks),
                                  reason=a.get("reason", "")[:300] or "agent", task_id=ctx.task["id"])
    return _after_proposal(ctx, row)


async def _delete_file(ctx: ToolContext, a: dict) -> str:
    row = ctx.svc.ai.propose(ctx.user, ctx.project_id, a["path"], "delete", None, a.get("reason", "agent"),
                             root=ctx.root, task_id=ctx.task["id"])
    return f"Proposal hapus #{row['id']} untuk {row['path']} dibuat (risiko HIGH); menunggu persetujuan eksplisit."


# ---------------- eksekusi ----------------
def _pending(ctx: ToolContext) -> list[dict]:
    return ctx.svc.ai.proposals(ctx.project_id, "pending", None, ctx.task["id"])


def _job_summary(job) -> str:
    out = job.stdout[-6000:]
    err = job.stderr[-4000:]
    return clip(f"Status: {job.status}, exit code: {job.exit_code}, durasi: {job.duration}s"
                + (f", error: {job.error}" if job.error else "")
                + (f"\n--- stdout (akhir) ---\n{out}" if out.strip() else "")
                + (f"\n--- stderr (akhir) ---\n{err}" if err.strip() else ""))


async def _run_or_build(ctx: ToolContext, a: dict, action: str) -> str:
    if _pending(ctx):
        raise NeedsApproval()
    svc = ctx.svc
    job = await svc.execution.submit(user=ctx.user, project_id=ctx.project_id, project_dir=ctx.root,
                                     file_rel=a["path"], action=action,
                                     args=[str(x) for x in a.get("args", [])][:32] if action == "run" else None,
                                     stdin=a.get("stdin") if action == "run" else None)
    ctx.task["_last_job"] = job.id
    await svc.execution.wait(job, timeout=svc.settings.build_timeout + svc.settings.run_timeout * 2 + 30)
    ctx.task.setdefault("_runs", []).append({"kind": action, "target": a["path"], "status": job.status,
                                             "exit_code": job.exit_code, "process_id": job.id})
    return _job_summary(job)


async def _run_file(ctx: ToolContext, a: dict) -> str:
    return await _run_or_build(ctx, a, "run")


async def _build_file(ctx: ToolContext, a: dict) -> str:
    return await _run_or_build(ctx, a, "build")


async def _list_tests(ctx: ToolContext, _: dict) -> str:
    tests = detect_tests(ctx.root, ctx.svc.settings.cache_dir / "lang")
    if not tests:
        return "Tidak ada perintah uji yang terdeteksi (pytest/unittest, go test, npm test, make test)."
    return "\n".join(f"- id={t.id}: {' '.join(t.argv)}" + (f"  ({t.note})" if t.note else "") for t in tests)


async def _run_tests(ctx: ToolContext, a: dict) -> str:
    if _pending(ctx):
        raise NeedsApproval()
    tests = detect_tests(ctx.root, ctx.svc.settings.cache_dir / "lang")
    if not tests:
        raise ToolError("Tidak ada perintah uji terdeteksi untuk proyek ini")
    want = a.get("id")
    t = next((x for x in tests if x.id == want), None) if want else tests[0]
    if t is None:
        raise ToolError(f"id uji '{want}' tidak dikenal. Pilihan: {', '.join(x.id for x in tests)}")
    svc = ctx.svc
    job = await svc.execution.submit_command(user=ctx.user, project_id=ctx.project_id, project_dir=ctx.root,
                                             argv=t.argv, action="test", label=t.framework, env=t.env)
    ctx.task["_last_job"] = job.id
    await svc.execution.wait(job, timeout=svc.settings.build_timeout + 30)
    ctx.task.setdefault("_runs", []).append({"kind": "test", "target": t.id, "status": job.status,
                                             "exit_code": job.exit_code, "process_id": job.id})
    return f"Perintah: {' '.join(t.argv)}\n" + _job_summary(job)


# ---------------- git (baca saja) ----------------
async def _git_status(ctx: ToolContext, _: dict) -> str:
    if not (ctx.root / ".git").is_dir():
        return "Proyek bukan repo git."
    st = await ctx.svc.git.status(ctx.root, ctx.user)
    files = "\n".join(f"{f['index']}{f['worktree']} {f['path']}" for f in st["files"][:200])
    return f"Branch: {st['branch']}\n" + (files or "(bersih)")


async def _git_diff(ctx: ToolContext, a: dict) -> str:
    if not (ctx.root / ".git").is_dir():
        return "Proyek bukan repo git."
    r = await ctx.svc.git.diff(ctx.root, ctx.user, path=a.get("path"))
    return clip(r.get("stdout") or "(tidak ada perubahan)")


async def _finish(ctx: ToolContext, a: dict) -> str:
    ctx.task["_finish"] = {k: a.get(k) for k in ("summary", "limitations", "remaining")}
    return "Selesai."


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("project_info", "Ringkasan proyek: bahasa, file build, perintah uji, repo git.", "read", "INSPECTING",
         handler=_project_info),
    Tool("list_dir", "Daftar isi folder (rekursif sampai depth).", "read", "INSPECTING",
         {"path": Arg("string", description="path relatif, kosong = akar"), "depth": Arg("integer")}, handler=_list_dir),
    Tool("read_file", "Baca file dengan nomor baris (maks 400 baris per panggilan).", "read", "INSPECTING",
         {"path": Arg("string", True), "start_line": Arg("integer"), "end_line": Arg("integer")}, handler=_read_file),
    Tool("search", "Cari teks di isi file (content=true) atau nama file (content=false).", "read", "INSPECTING",
         {"query": Arg("string", True), "content": Arg("boolean"), "path": Arg("string")}, handler=_search),
    Tool("update_plan", "Simpan/perbarui rencana kerja: steps=[{id, description, files, depends_on, risk, "
         "verification, status}] dengan status pending|in_progress|done|skipped|failed.", "read", "PLANNING",
         {"steps": Arg("array", True)}, handler=_update_plan),
    Tool("write_file", "Buat/ganti file utuh. Isi di args.content ATAU blok kode tepat setelah JSON.", "write",
         "EXECUTING", {"path": Arg("string", True), "content": Arg("string"), "reason": Arg("string")},
         handler=_write_file),
    Tool("edit_file", "Ubah sebagian file: args.search (teks lama persis) & args.replace, ATAU blok "
         "SEARCH/REPLACE setelah JSON.", "write", "EXECUTING",
         {"path": Arg("string", True), "search": Arg("string"), "replace": Arg("string"), "reason": Arg("string")},
         handler=_edit_file),
    Tool("delete_file", "Usulkan penghapusan file (selalu butuh persetujuan eksplisit).", "delete", "EXECUTING",
         {"path": Arg("string", True), "reason": Arg("string")}, handler=_delete_file),
    Tool("build_file", "Kompilasi/cek sintaks satu file sumber di sandbox.", "build", "BUILDING",
         {"path": Arg("string", True)}, timeout=900, handler=_build_file),
    Tool("run_file", "Jalankan satu file program di sandbox dan lihat output.", "execute", "TESTING",
         {"path": Arg("string", True), "args": Arg("array"), "stdin": Arg("string")}, timeout=900, handler=_run_file),
    Tool("list_tests", "Daftar perintah uji yang terdeteksi.", "read", "INSPECTING", handler=_list_tests),
    Tool("run_tests", "Jalankan perintah uji terdeteksi (id dari list_tests; default yang pertama).", "execute",
         "TESTING", {"id": Arg("string")}, timeout=900, handler=_run_tests),
    Tool("git_status", "Status git proyek.", "read", "REVIEWING", handler=_git_status),
    Tool("git_diff", "Diff git (perubahan yang sudah diterapkan).", "read", "REVIEWING",
         {"path": Arg("string")}, handler=_git_diff),
    Tool("finish", "Akhiri task dengan ringkasan, keterbatasan, dan sisa pekerjaan.", "read", "REVIEWING",
         {"summary": Arg("string", True), "limitations": Arg("string"), "remaining": Arg("string")}, handler=_finish),
]}


def available(ai_perms: set[str]) -> list[Tool]:
    return [t for t in TOOLS.values() if t.perm in ai_perms]


async def call(ctx: ToolContext, name: str, args: Any) -> str:
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"Tool '{name}' tidak ada. Tool tersedia: {', '.join(t.name for t in available(ctx.ai_perms))}")
    if tool.perm not in ctx.ai_perms:
        raise ToolError(f"Tool '{name}' butuh izin '{tool.perm}' yang tidak dimiliki agen untuk pengguna ini")
    clean = tool.validate(args)
    try:
        return await asyncio.wait_for(tool.handler(ctx, clean), tool.timeout)
    except asyncio.TimeoutError:
        raise ToolError(f"Tool '{name}' melebihi batas waktu {int(tool.timeout)} detik")
    except AppError as e:
        raise ToolError(e.message)
    except ValueError as e:
        raise ToolError(str(e))
