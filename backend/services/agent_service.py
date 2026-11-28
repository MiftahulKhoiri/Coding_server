"""AI Coding Agent: task persisten dengan loop Understand → Inspect → Plan → Execute → Test → Review → Report.

* Model (lokal llama-server atau online) memilih SATU tool per langkah dalam format JSON. Format ini
  sengaja tidak bergantung pada fitur "tool calling" penyedia agar model lokal kecil juga bisa.
* Semua aksi lewat ``agent_tools`` (izin = irisan hak pengguna & peran 'ai'); perubahan file menjadi
  proposal di Approval Center; eksekusi lewat ExecutionService (antrean, sandbox fail-closed).
* Task, rencana, log event, dan checkpoint percakapan disimpan di SQLite. Server restart → task
  yang sedang berjalan menjadi PAUSED (bukan hilang) dan bisa dilanjutkan dari checkpoint.
* Laporan akhir dibangun server dari data nyata (proposal, hasil eksekusi); ringkasan dari model
  ditandai sebagai teks buatan AI.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from pathlib import Path

from backend.config import Settings
from backend.core.exceptions import AppError, Conflict, Forbidden, NotFound
from backend.core.logging import get_logger
from backend.core.permissions import intersect_for_ai
from backend.database.db import Database
from backend.services import agent_tools
from backend.services.agent_tools import NeedsApproval, ToolContext, ToolError

log = get_logger("agent")

ACTIVE = {"PENDING", "PLANNING", "INSPECTING", "EXECUTING", "BUILDING", "TESTING", "REVIEWING", "FIXING"}
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
STATUSES = ACTIVE | TERMINAL | {"PAUSED", "WAITING_APPROVAL"}
CONTEXT_BUDGET = 48_000   # karakter percakapan maksimum (dipersempit otomatis sesuai konteks model)
CHARS_PER_TOKEN = 3       # perkiraan aman untuk kode/teks campuran (Qwen ±3,5–4 karakter per token)
_CTX_ERR = re.compile(r"exceeds? the (?:available )?context|context size|context length", re.I)
_CTX_SIZE = re.compile(r"context (?:size|length)\D{0,20}(\d{3,7})", re.I)
KEEP_RECENT = 6           # hasil tool terakhir yang tidak dipangkas
MAX_PARSE_FAILS = 3
FREE_PLAN_UPDATES = 8      # update_plan yang tidak dihitung sebagai langkah
ESCALATE_AFTER_PARSE = 2  # balasan salah format berturut-turut sebelum eskalasi ke model yang lebih kuat
ESC_STEPS = 3             # langkah yang dikerjakan model eskalasi sebelum kembali ke peran normal
MAX_REVIEWS = 2           # peninjauan sebelum finish (mencegah loop tinjau tanpa akhir)
ROLE_LABEL = {"planner": "Perencana", "executor": "Pelaksana", "reviewer": "Peninjau", "online": "Online"}
ESC_LEVEL = {"planner": 1, "online": 2}

REVIEW_PROMPT = """[peninjau] Agen mengusulkan task SELESAI. Kamu sekarang PENINJAU yang teliti.
Periksa riwayat di atas: apakah tugas benar-benar terpenuhi? Apakah perubahan sudah diterapkan (bukan
hanya diusulkan) dan sudah diverifikasi (build/test) bila memungkinkan? Adakah error yang tersisa atau
klaim yang tidak didukung hasil tool?
- Bila semuanya benar: panggil finish (perbaiki ringkasan/keterbatasan bila perlu).
- Bila belum: panggil tool untuk memeriksa atau memperbaiki (mis. read_file, run_tests, edit_file).
Balas dengan format JSON tool seperti biasa."""

SYSTEM_PROMPT = """Kamu adalah AI Coding Agent di CODING_SERVER (Raspberry Pi 5). Kamu bekerja pada SATU proyek
nyata dan hanya bisa bertindak lewat tool di bawah. Jangan pernah mengarang isi file: baca dulu.

Alur kerja: pahami tugas → inspeksi proyek (project_info, list_dir, search, read_file) → buat rencana
(update_plan) → ubah file seperlunya (edit_file untuk perubahan kecil, write_file untuk file baru) →
verifikasi (build_file / run_file / run_tests) → bila gagal, baca error, cari akar masalah, perbaiki,
ulangi verifikasi → perbarui status rencana → finish.

Aturan:
- Setiap balasan berisi TEPAT SATU objek JSON dalam blok ```json:
  {{"thought": "alasan singkat", "tool": "nama_tool", "args": {{...}}}}
- Hanya SATU tool per balasan; jangan menulis beberapa blok JSON sekaligus.
- Untuk write_file/edit_file, JANGAN taruh isi file di dalam JSON. Tulis isi file di blok kode TERPISAH
  tepat setelah blok json (JSON hanya berisi path & reason). Untuk edit_file pakai format:
<<<<<<< SEARCH
teks lama persis (sertakan baris di sekitarnya agar unik, mis. nama fungsinya)
=======
teks baru
>>>>>>> REPLACE
- Perubahan file menjadi proposal; bisa saja menunggu persetujuan pengguna. Jangan menyingkat isi
  file dengan "...".
- Buat perubahan sekecil mungkin, jangan ubah hal yang tidak diminta, jangan hapus file kecuali diminta.
- Jangan mengaku tes lulus tanpa menjalankannya. Bila tidak bisa diverifikasi, katakan di finish.
- Program yang dijalankan (run_file/run_tests) TIDAK punya internet. Untuk memasang paket/library
  JANGAN menulis skrip installer (pip/npm/subprocess); tulis dulu daftar dependensinya
  (requirements.txt / package.json / go.mod / composer.json) lalu panggil install_deps. Paket Python
  dipasang ke .venv proyek dan otomatis dipakai oleh run_file & run_tests.
- Setiap selesai mengubah file kode (.py, .js, .c, …), jalankan build_file untuk file itu dan perbaiki
  error yang muncul SEBELUM lanjut. Untuk menambah kode ke file yang sudah ada, baca dulu isinya:
  jangan menambahkan fungsi/route yang sudah ada (duplikat).

Tool yang tersedia untukmu:
{tools}
"""


def _now() -> float:
    return time.time()


def tools_text(ai_perms: set[str]) -> str:
    def sig(t) -> str:
        return ", ".join(k + ("" if a.required else "?") + ": " + a.type for k, a in t.args.items())

    return "\n".join(f"- {t.name}({sig(t)}): {t.description}" for t in agent_tools.available(ai_perms))


def system_prompt(ai_perms: set[str]) -> str:
    return SYSTEM_PROMPT.format(tools=tools_text(ai_perms))


_STR_KEYS = ("thought", "path", "content", "search", "replace", "query", "id", "summary", "limitations",
             "remaining", "reason", "stdin")
_END_OF_VALUE = re.compile(r'"\s*(?:,\s*"[A-Za-z_]+"\s*:|})')
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f"}


def _lenient_string(text: str, key: str) -> tuple[str, int] | None:
    """Nilai string untuk key, toleran terhadap baris baru mentah & tanda kutip tak ter-escape di dalamnya.
    Nilai dianggap berakhir pada tanda kutip yang diikuti ', "key":' atau '}'."""
    m = re.search(r'"' + key + r'"\s*:\s*"', text)
    if not m:
        return None
    i, n = m.end(), len(text)
    out: list[str] = []
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            nx = text[i + 1]
            if nx == "u" and re.match(r"[0-9a-fA-F]{4}", text[i + 2:i + 6]):
                out.append(chr(int(text[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append(_ESCAPES.get(nx, "\\" + nx))
            i += 2
            continue
        if ch == '"' and _END_OF_VALUE.match(text, i):
            return "".join(out), i + 1
        out.append(ch)
        i += 1
    return None


# Akhir nilai "content" yang ditulis model kecil dengan gaya Python, mis. ...\n''', reason="...")
# atau ..."}} ; penutup string boleh ''' / """ / ".
_Q = r"""(?:'''|\"\"\"|")"""
_CONTENT_START = re.compile(r'"content"\s*:\s*' + _Q)
_CONTENT_END = re.compile(_Q + r'\s*,\s*"?reason"?\s*[:=]|' + _Q + r"\s*}\s*}?\s*\)?\s*(?:```)?\s*$")


def _decode_escapes(raw: str) -> str:
    out, i = [], 0
    while i < len(raw):
        if raw[i] == "\\" and i + 1 < len(raw):
            nx = raw[i + 1]
            if nx == "u" and re.match(r"[0-9a-fA-F]{4}", raw[i + 2:i + 6]):
                out.append(chr(int(raw[i + 2:i + 6], 16)))
                i += 6
                continue
            out.append(_ESCAPES.get(nx, "\\" + nx))
            i += 2
            continue
        out.append(raw[i])
        i += 1
    return "".join(out)


def _recover_content(text: str) -> tuple[str, int] | None:
    """Selamatkan isi file dari args.content yang bukan JSON valid (jangan dibuang diam-diam).

    Batas akhir = kemunculan TERAKHIR penutup string sebelum `reason` / akhir objek, karena isi file
    sendiri boleh memuat ''' atau tanda kutip. Escape JSON (backslash-n, backslash-kutip) di-decode
    bila isinya memakai escape, bukan baris baru asli."""
    m = _CONTENT_START.search(text)
    if not m:
        return None
    ends = list(_CONTENT_END.finditer(text, m.end()))
    if not ends:
        return None
    cut = ends[-1]
    raw = text[m.end():cut.start()]
    if raw.count("\\n") > raw.count("\n"):
        raw = _decode_escapes(raw)
    if not raw.strip():
        return None
    return raw, cut.end()


def _lenient_call(text: str) -> tuple[dict, int] | None:
    m = re.search(r'"tool"\s*:\s*"([A-Za-z_]+)"', text)
    if not m:
        return None
    obj: dict = {"tool": m.group(1), "args": {}}
    end = m.end()
    for key in _STR_KEYS:
        got = _lenient_string(text, key)
        if got is None and key == "content" and obj["tool"] == "write_file":
            got = _recover_content(text)
        if got is not None:
            (obj if key == "thought" else obj["args"])[key] = got[0]
            end = max(end, got[1])
    if obj["tool"] == "write_file" and "reason" not in obj["args"]:
        r = re.search(r'reason"?\s*[:=]\s*"([^"\n]{0,300})"', text)
        if r:
            obj["args"]["reason"] = r.group(1)
    close = text.find("}", end)
    return obj, (close + 1 if close >= 0 else end)


def extract_call(text: str) -> tuple[dict, str | None]:
    """Ambil objek JSON pertama (utamakan blok ```json) + blok kode pertama SETELAH JSON."""
    candidates: list[tuple[int, int]] = []
    for m in re.finditer(r"```(?:json|JSON)\s*\n(.*?)```", text, re.S):
        candidates.append((m.start(1), m.end()))
    dec = json.JSONDecoder()
    obj, end = None, None
    for start, fence_end in candidates:
        try:
            o, _ = dec.raw_decode(text[start:].lstrip())
            if isinstance(o, dict):
                obj, end = o, fence_end
                break
        except json.JSONDecodeError:
            continue
    if obj is None:
        for m in re.finditer(r"\{", text):
            try:
                o, n = dec.raw_decode(text[m.start():])
            except json.JSONDecodeError:
                continue
            if isinstance(o, dict) and "tool" in o:
                obj, end = o, m.start() + n
                break
    if obj is None:
        # JSON rusak (biasanya isi file di dalam string tanpa escape yang benar): coba baca secara toleran
        lenient = _lenient_call(text)
        if lenient is not None:
            obj, end = lenient
    if obj is None or not isinstance(obj.get("tool"), str):
        raise ValueError("Balasan tidak berisi objek JSON dengan field \"tool\"")
    code = None
    m = re.search(r"```[^\n`]*\n(.*?)```", text[end:], re.S)
    if m:
        code = m.group(1)
    return obj, code


class AgentService:
    def __init__(self, settings: Settings, db: Database, services_ref):
        self.s = settings
        self.db = db
        self._svc_ref = services_ref  # callable -> Services (hindari import melingkar)
        self._sem = asyncio.Semaphore(max(1, settings.agent_max_concurrent))
        self._tasks: dict[str, asyncio.Task] = {}
        self._pause: set[str] = set()
        self._pause_now: set[str] = set()  # jeda segera: panggilan model yang sedang berjalan dihentikan
        # Proses model yang sedang berjalan per task (di memori, tidak disimpan): tahap, token, teks terakhir.
        self._live: dict[str, dict] = {}

    def recover(self) -> None:
        """Pemulihan saat server mulai (lifespan): task yang sedang berjalan saat server mati menjadi PAUSED,
        tidak dihapus diam-diam. Tidak di konstruktor agar sekadar mengimpor aplikasi tidak menjeda task aktif."""
        self.db.execute(
            "UPDATE agent_tasks SET status='PAUSED', current_op='Server dimulai ulang; lanjutkan untuk meneruskan "
            "dari checkpoint', updated_at=? WHERE status IN (%s)" % ",".join("?" * len(ACTIVE)),
            (_now(), *sorted(ACTIVE)),
        )

    @property
    def svc(self):
        return self._svc_ref()

    # ---------- penyimpanan ----------
    def _row(self, task_id: str) -> dict:
        row = self.db.one("SELECT * FROM agent_tasks WHERE id=?", (task_id,))
        if not row:
            raise NotFound("Task agen tidak ditemukan")
        return row

    def _owned(self, task_id: str, user: dict) -> dict:
        row = self._row(task_id)
        if row["user_id"] != user["id"] and "admin" not in user["perms"]:
            raise NotFound("Task agen tidak ditemukan")
        return row

    def _update(self, task_id: str, **f) -> None:
        f["updated_at"] = _now()
        cols = ", ".join(f"{k}=?" for k in f)
        self.db.execute(f"UPDATE agent_tasks SET {cols} WHERE id=?", (*f.values(), task_id))

    def _event(self, task_id: str, kind: str, data: dict) -> None:
        self.db.execute("INSERT INTO agent_events(task_id, ts, kind, data) VALUES(?,?,?,?)",
                        (task_id, _now(), kind, json.dumps(data, ensure_ascii=False, default=str)[:60_000]))

    def public(self, row: dict, detail: bool = False) -> dict:
        out = {k: row.get(k) for k in ("id", "user_id", "project_id", "title", "description", "status", "stage",
                                       "progress", "current_op", "connection_id", "model", "error", "max_steps",
                                       "steps_used", "created_at", "started_at", "updated_at", "finished_at",
                                       "last_activity")}
        out["auto_apply"] = bool(row.get("auto_apply"))
        end = row.get("finished_at") or (_now() if row.get("status") not in TERMINAL else row.get("updated_at"))
        out["duration"] = round(end - row["started_at"], 1) if row.get("started_at") and end else None
        pend = self.db.one("SELECT COUNT(*) AS n FROM ai_proposals WHERE task_id=? AND status='pending'", (row["id"],))
        out["pending_proposals"] = pend["n"] if pend else 0
        live = self._live.get(row["id"])
        out["live"] = (dict(live, elapsed=round(time.time() - live["started"], 1))
                       if live and row.get("status") not in TERMINAL else None)
        if detail:
            out["plan"] = json.loads(row.get("plan") or "[]")
            out["report"] = json.loads(row["report"]) if row.get("report") else None
        return out

    # ---------- API ----------
    def tools_for(self, user: dict) -> list[dict]:
        perms = intersect_for_ai(user["perms"])
        return [t.schema() | {"allowed": t.perm in perms} for t in agent_tools.TOOLS.values()]

    def _auto_apply_text(self, row: dict) -> str:
        if not row["auto_apply"]:
            return "tidak (semua editan menunggu persetujuan)"
        if self.svc.ai.agent_models().get("approval_mode") == "penuh":
            return "ya, penuh (semua editan langsung diterapkan)"
        return "ya (risiko HIGH tetap butuh persetujuan)"

    def create(self, user: dict, project_id: str, description: str, title: str | None = None,
               auto_apply: bool | None = False, max_steps: int | None = None) -> dict:
        perms = intersect_for_ai(user["perms"])
        if "read" not in perms:
            raise Forbidden("Agen AI tidak punya hak baca untuk pengguna ini")
        if auto_apply is None:  # ikuti mode izin agent global
            auto_apply = (self.svc.ai.agent_models().get("approval_mode") != "manual"
                          and "write" in user["perms"])
        if auto_apply and "write" not in user["perms"]:
            raise Forbidden("Auto-apply butuh hak tulis")
        description = description.strip()
        if not description:
            raise AppError("Deskripsi tugas wajib diisi", code="empty_task")
        self.svc.projects.get(project_id, user)
        if self.svc.ai.state["status"] == "loading":
            raise AppError(f"Model masih dimuat: {self.svc.ai.state['message']}", code="ai_loading", status_code=503)
        self._target("executor")  # gagal cepat (503) bila belum ada model sama sekali
        if max_steps is None:  # bawaan dari pengaturan Model AI → AI Agent
            max_steps = int(self.svc.ai.agent_models().get("max_steps") or 30)
        tid = uuid.uuid4().hex[:12]
        now = _now()
        self.db.execute(
            "INSERT INTO agent_tasks(id, user_id, project_id, title, description, status, stage, auto_apply, "
            "max_steps, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (tid, user["id"], project_id, (title or description.splitlines()[0])[:120], description[:20_000],
             "PENDING", "PENDING", int(auto_apply), max(3, min(int(max_steps), self.s.agent_max_steps)), now, now),
        )
        self._event(tid, "status", {"status": "PENDING", "message": "Task dibuat"})
        self.db.audit("agent_task_create", user=user, target=tid, detail={"project_id": project_id})
        self._start(tid, user)
        return self.public(self._row(tid), detail=True)

    def list(self, user: dict, project_id: str | None = None, status: str | None = None, limit: int = 100) -> list[dict]:
        sql, args = "SELECT * FROM agent_tasks WHERE 1=1", []
        if "admin" not in user["perms"]:
            sql += " AND user_id=?"; args.append(user["id"])
        if project_id:
            sql += " AND project_id=?"; args.append(project_id)
        if status:
            sql += " AND status=?"; args.append(status.upper())
        rows = self.db.all(sql + " ORDER BY updated_at DESC LIMIT ?", (*args, min(limit, 500)))
        return [self.public(r) for r in rows]

    def get(self, user: dict, task_id: str) -> dict:
        return self.public(self._owned(task_id, user), detail=True)

    def events(self, user: dict, task_id: str, after: int = 0, limit: int = 200) -> list[dict]:
        self._owned(task_id, user)
        rows = self.db.all("SELECT id, ts, kind, data FROM agent_events WHERE task_id=? AND id>? ORDER BY id LIMIT ?",
                           (task_id, after, min(limit, 1000)))
        for r in rows:
            r["data"] = json.loads(r["data"])
        return rows

    async def cancel(self, user: dict, task_id: str) -> dict:
        row = self._owned(task_id, user)
        if row["status"] in TERMINAL:
            return self.public(row, detail=True)
        t = self._tasks.get(task_id)
        if t and not t.done():
            t.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(t), 10)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
        row = self._row(task_id)
        if row["status"] not in TERMINAL:
            self._update(task_id, status="CANCELLED", current_op="Dibatalkan pengguna", finished_at=_now())
            self._event(task_id, "status", {"status": "CANCELLED", "message": "Dibatalkan pengguna"})
        self.db.audit("agent_task_cancel", user=user, target=task_id)
        return self.get(user, task_id)

    def pause(self, user: dict, task_id: str) -> dict:
        row = self._owned(task_id, user)
        if row["status"] not in ACTIVE:
            raise Conflict(f"Task berstatus {row['status']}, tidak bisa dijeda")
        self._pause.add(task_id)
        t = self._tasks.get(task_id)
        if task_id in self._live and t and not t.done():
            # Sedang menunggu model (bisa >10 menit di Pi): hentikan sekarang. Aman — checkpoint sudah tersimpan
            # sesudah langkah terakhir yang selesai; langkah yang belum dijawab model diulang saat dilanjutkan.
            self._pause_now.add(task_id)
            t.cancel()
            self._update(task_id, current_op="Menjeda… (menghentikan model)")
        else:  # sedang menjalankan tool (tulis file, build/test): tunggu selesai supaya tidak setengah jalan
            self._update(task_id, current_op="Akan dijeda setelah langkah ini selesai")
        return self.get(user, task_id)

    async def pause_all(self, reason: str) -> list[str]:
        """Jeda SEGERA semua task yang sedang berjalan (dipakai saat model dilepas paksa dari RAM).

        Sama seperti tombol Jeda saat menunggu model: status PAUSED dari checkpoint terakhir, langkah yang belum
        selesai diulang saat dilanjutkan. Bila sedang menjalankan build/test/instal, proses itu ikut dihentikan."""
        paused = []
        for task_id, t in list(self._tasks.items()):
            if t.done():
                continue
            self._pause.add(task_id)
            self._pause_now.add(task_id)
            t.cancel()
            paused.append(task_id)
        for task_id in paused:
            t = self._tasks.get(task_id)
            if t:
                try:
                    await asyncio.wait_for(asyncio.shield(t), 15)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass
            self._event(task_id, "status", {"status": "PAUSED", "message": reason})
            self._update(task_id, current_op=reason)
        return paused

    def resume(self, user: dict, task_id: str) -> dict:
        row = self._owned(task_id, user)
        if row["status"] in ACTIVE and task_id in self._tasks and not self._tasks[task_id].done():
            self._pause.discard(task_id)
            return self.get(user, task_id)
        if row["status"] not in ("PAUSED", "WAITING_APPROVAL", "FAILED", "CANCELLED"):
            raise Conflict(f"Task berstatus {row['status']}, tidak bisa dilanjutkan")
        if row["status"] == "WAITING_APPROVAL" and self.public(row)["pending_proposals"]:
            raise Conflict("Masih ada proposal yang menunggu keputusan di Approval Center", code="approval_pending")
        if row["status"] in ("FAILED", "CANCELLED"):  # retry dari checkpoint terakhir
            self._update(task_id, error="", finished_at=None,
                         max_steps=min(row["max_steps"] + 10, self.s.agent_max_steps + 20))
        self._update(task_id, status="PENDING", current_op="Menunggu giliran")
        self._event(task_id, "status", {"status": "PENDING", "message": "Dilanjutkan"})
        self._start(task_id, self._owner(row))
        return self.get(user, task_id)

    def delete(self, user: dict, task_id: str) -> None:
        row = self._owned(task_id, user)
        if row["status"] in ACTIVE:
            raise Conflict("Batalkan task dulu sebelum dihapus")
        with self.db.tx() as c:
            c.execute("DELETE FROM agent_events WHERE task_id=?", (task_id,))
            c.execute("DELETE FROM agent_tasks WHERE id=?", (task_id,))

    def on_proposal_decided(self, task_id: str | None) -> None:
        """Dipanggil setelah pengguna memutuskan proposal: lanjutkan otomatis bila tak ada lagi yang pending."""
        if not task_id:
            return
        row = self.db.one("SELECT * FROM agent_tasks WHERE id=?", (task_id,))
        if row and row["status"] == "WAITING_APPROVAL" and not self.public(row)["pending_proposals"]:
            self._update(task_id, status="PENDING", current_op="Persetujuan selesai, melanjutkan")
            self._event(task_id, "status", {"status": "PENDING", "message": "Semua proposal sudah diputuskan"})
            self._start(task_id, self._owner(row))

    def _owner(self, row: dict) -> dict:
        """Hak pemilik dibaca ulang dari DB (bukan dari token lama): izin yang dicabut langsung berlaku."""
        u = self.db.one("SELECT * FROM users WHERE id=?", (row["user_id"],))
        if not u or not u["is_active"]:
            raise Forbidden("Pemilik task tidak aktif")
        pub = self.svc.auth.public(u)
        pub["perms"] = set(pub["permissions"])
        return pub

    def _start(self, task_id: str, user: dict) -> None:
        self._pause.discard(task_id)
        if not _loop_running():
            raise AppError("Event loop tidak berjalan", code="internal", status_code=500)
        t = asyncio.get_running_loop().create_task(self._run(task_id, user))
        self._tasks[task_id] = t
        t.add_done_callback(lambda _t: self._tasks.pop(task_id, None) if self._tasks.get(task_id) is _t else None)

    async def shutdown(self) -> None:
        for t in list(self._tasks.values()):
            t.cancel()

    # ---------- loop agen ----------
    def _messages(self, row: dict, ai_perms: set[str]) -> list[dict]:
        if row.get("checkpoint"):
            try:
                msgs = json.loads(row["checkpoint"])["messages"]
                if msgs and msgs[0].get("role") == "system":
                    # Aturan & daftar tool terbaru juga berlaku untuk task yang dilanjutkan dari checkpoint.
                    msgs[0] = {"role": "system", "content": system_prompt(ai_perms)}
                return msgs
            except (ValueError, KeyError):
                pass
        proj = self.svc.projects.get(row["project_id"], self._owner(row))
        user_msg = (f"Proyek: {proj['name']} (bahasa utama: {proj.get('language') or '-'})\n"
                    f"Auto-apply: {self._auto_apply_text(row)}\n"
                    f"Batas langkah: {row['max_steps']}\n\nTUGAS:\n{row['description']}")
        return [{"role": "system", "content": system_prompt(ai_perms)},
                {"role": "user", "content": user_msg}]

    @staticmethod
    def _compact(messages: list[dict], budget: int = CONTEXT_BUDGET) -> list[dict]:
        """Pangkas riwayat lama agar muat konteks model; file asli tetap sumber kebenaran (bisa dibaca ulang).

        Urutan: (1) hasil tool lama, (2) balasan model lama yang panjang (mis. isi file yang sudah ditulis),
        (3) buang langkah tertua. System prompt, tugas, dan 2 pesan terakhir selalu dipertahankan."""
        total = sum(len(m["content"]) for m in messages)
        if total <= budget:
            return messages
        out = [dict(m) for m in messages]
        recent_from = max(2, len(out) - 2 * KEEP_RECENT)

        def shrink(i: int, keep: int, note: str) -> None:
            nonlocal total
            old = out[i]["content"]
            if len(old) <= keep + len(note) + 20:
                return
            out[i]["content"] = old[:keep] + note
            total -= len(old) - len(out[i]["content"])

        for i in range(2, recent_from):
            if total <= budget:
                break
            if out[i]["role"] == "user" and out[i]["content"].startswith("[hasil tool"):
                shrink(i, 300, "\n…[dipangkas; baca ulang file bila perlu]")
        for i in range(2, len(out) - 2):
            if total <= budget:
                break
            if out[i]["role"] == "assistant":
                shrink(i, 400, "\n…[balasan lama dipangkas]")
        for i in range(2, len(out) - 2):  # hasil tool terbaru pun dipangkas bila masih belum muat
            if total <= budget:
                break
            if out[i]["role"] == "user" and out[i]["content"].startswith("[hasil tool"):
                shrink(i, 1500, "\n…[dipangkas]")
        # Masih terlalu panjang: buang langkah tertua (setelah system + tugas).
        while total > budget and len(out) > 4:
            removed = out.pop(2)
            total -= len(removed["content"])
        # Upaya terakhir: pesan terbaru sendiri terlalu besar (mis. hasil tool 12 ribu karakter) →
        # sisakan awal & akhirnya saja supaya permintaan tetap muat konteks model.
        for i in range(len(out) - 1, 1, -1):
            if total <= budget:
                break
            old = out[i]["content"]
            fixed = total - len(old)
            room = max(600, budget - fixed)
            if len(old) > room:
                head, tail = room * 2 // 3, room // 3 - 40
                out[i]["content"] = old[:head] + "\n…[dipangkas agar muat konteks]…\n" + old[-max(tail, 0):]
                total = fixed + len(out[i]["content"])
        return out

    _ctx_tokens: dict[str, int] = {}  # model -> ukuran konteks (token) yang diketahui dari error server

    def any_active(self) -> bool:
        ph = ",".join("?" * len(ACTIVE))
        return self.db.one(f"SELECT 1 AS x FROM agent_tasks WHERE status IN ({ph}) LIMIT 1", tuple(ACTIVE)) is not None

    def forget_context(self) -> None:
        """Konteks model diubah pengguna: lupakan ukuran yang dipelajari dari error server."""
        AgentService._ctx_tokens.clear()

    def _budget(self, model: str, max_tokens: int) -> int:
        """Anggaran karakter riwayat untuk model, dari ukuran konteks yang diketahui/dikonfigurasi."""
        n_ctx = self._ctx_tokens.get(model)
        if not n_ctx:
            try:  # dari pengaturan Konteks model (file preset llama-server)
                n_ctx = self.svc.llama_ctx.ctx_for(model)
            except Exception:
                n_ctx = None
        if not n_ctx:
            return CONTEXT_BUDGET
        # Sisakan ruang untuk jawaban (maks sepertiga konteks) agar model masih bisa menulis isi file.
        room = max(1024, n_ctx - min(max_tokens, n_ctx // 3) - 256)
        return min(CONTEXT_BUDGET, room * CHARS_PER_TOKEN)

    def _save_checkpoint(self, task_id: str, messages: list[dict], extra: dict) -> None:
        self._update(task_id, checkpoint=json.dumps({"messages": messages, **extra}, ensure_ascii=False))

    def _progress(self, task: dict, steps_used: int, max_steps: int) -> float:
        plan = task.get("_plan") or []
        if plan:
            done = sum(1 for s in plan if s["status"] in ("done", "skipped"))
            return round(done / len(plan), 3)
        return round(min(0.9, steps_used / max(1, max_steps)), 3)

    # ---------- pemilihan model (peran & eskalasi) ----------
    def _target(self, role: str) -> tuple[str, str]:
        """(connection_id, model) untuk peran; peran kosong turun ke peran lain lalu ke model aktif."""
        ai = self.svc.ai
        order = {"planner": ("planner", "executor"), "executor": ("executor",),
                 "reviewer": ("reviewer", "planner", "executor"), "online": ("online",)}[role]
        for r in order:
            t = ai.role_target(r)
            if t:
                return t
        t = ai.default_target()
        if not t:
            raise AppError("Belum ada model AI. Buka menu AI Pengaturan: terapkan model atau atur peran model agent.",
                           code="ai_not_configured", status_code=503)
        return t

    @staticmethod
    def _pick_role(task: dict) -> str:
        if task.get("_esc_left", 0) > 0 and task.get("_esc_role"):
            return task["_esc_role"]
        if task.get("_review_pending"):
            return "reviewer"
        if not task["_plan"]:
            return "planner"
        return "executor"

    def _escalate(self, task_id: str, task: dict, reason: str, current: tuple[str, str]) -> bool:
        """Naikkan ke model yang lebih kuat: Perencana, lalu model Online (hanya bila diizinkan)."""
        conf = self.svc.ai.agent_models()
        chain: list[tuple[str, tuple[str, str]]] = []
        try:
            chain.append(("planner", self._target("planner")))
        except AppError:
            pass
        if conf.get("allow_online") and conf.get("online"):
            chain.append(("online", (conf["online"]["connection_id"], conf["online"]["model"])))
        cur_level = ESC_LEVEL.get(task.get("_esc_role") or "", 0) if task.get("_esc_left", 0) > 0 else 0
        for role, tgt in chain:
            if ESC_LEVEL[role] > cur_level and tgt != current:
                task["_esc_role"], task["_esc_left"] = role, ESC_STEPS
                self._event(task_id, "escalation", {"to_role": role, "to_model": tgt[1], "from_model": current[1],
                                                    "reason": reason})
                log.info("Task %s eskalasi ke %s (%s): %s", task_id, role, tgt[1], reason)
                return True
        return False

    async def _ask_model(self, task_id: str, messages: list[dict], target: tuple[str, str],
                         role: str = "executor") -> tuple[str, str, dict]:
        ai = self.svc.ai
        cid, model = target
        live = {"phase": "loading", "role": role, "model": model, "started": time.time(), "tokens": 0,
                "reasoning_tokens": 0, "first_token_s": None, "tps": None, "text": "",
                "approx_prompt_tokens": sum(len(str(m.get("content") or "")) for m in messages) // 4}
        self._live[task_id] = live
        try:
            return await self._ask_model_live(task_id, messages, target, role, live)
        finally:
            if self._live.get(task_id) is live:
                self._live.pop(task_id, None)

    async def _ask_model_live(self, task_id: str, messages: list[dict], target: tuple[str, str], role: str,
                              live: dict) -> tuple[str, str, dict]:
        ai = self.svc.ai
        cid, model = target
        row, prov = await ai.acquire(cid, model, on_status=lambda m: self._update(task_id, current_op=m,
                                                                                 last_activity=_now()))
        conf = ai.settings()
        parts: list[str] = []
        thinking = {"tokens": 0}
        started = time.time()
        # Profil model: Perencana/Peninjau/Online memakai preset "kualitas", Pelaksana preset "cepat".
        opts = ai.profiles.request_options(row, model, "cepat" if role == "executor" else "kualitas")
        if opts:
            temp, max_tok, extra = opts["temperature"], opts["max_tokens"], opts["extra"]
            messages = ai.profiles.with_prompt_extra(messages, opts["prompt_extra"])
        else:  # profil dimatikan: perilaku lama
            temp, max_tok, extra = min(float(conf.get("temperature") or 0.2), 0.4), max(int(conf.get("max_tokens") or 2048), 2048), None

        messages = self._compact(messages, self._budget(model, int(max_tok or 2048)))
        live["approx_prompt_tokens"] = sum(len(str(m.get("content") or "")) for m in messages) // 4
        live.update(phase="prompt", started=time.time())

        async def collect() -> None:
            async for kind, text in prov.stream_chat(model, messages, temp, max_tok, extra):
                now = time.time()
                if live["first_token_s"] is None:
                    live["first_token_s"] = round(now - live["started"], 1)
                if kind == "delta":
                    parts.append(text)
                    if live["phase"] != "writing":  # pisahkan jawaban dari isi pikiran
                        live["text"] = ""
                    live["phase"] = "writing"
                    live["tokens"] += max(1, len(text) // 4)
                else:
                    thinking["tokens"] += max(1, len(text) // 4)
                    live["phase"] = "thinking"
                    live["reasoning_tokens"] = thinking["tokens"]
                live["text"] = (live["text"] + text)[-1500:]
                gen = now - live["started"] - (live["first_token_s"] or 0)
                if gen > 0.5:
                    live["tps"] = round((live["tokens"] + live["reasoning_tokens"]) / gen, 2)
                ai.touch(cid, model)

        ai.hold(cid, model)  # cegah model dibongkar selama dipakai
        try:
            try:
                await asyncio.wait_for(collect(), self.s.agent_model_timeout)
            except AppError as e:
                m = _CTX_ERR.search(e.message or "")
                if not m or parts:
                    raise
                # Konteks model terlampaui: catat ukurannya, pangkas riwayat lebih kuat, coba sekali lagi.
                sent = sum(len(str(x.get("content") or "")) for x in messages)
                size = _CTX_SIZE.search(e.message or "")
                known = int(size.group(1)) if size else max(2048, int(sent / CHARS_PER_TOKEN * 0.8))
                self._ctx_tokens[model] = min(self._ctx_tokens.get(model, known), known)
                budget = min(int(sent * 0.7), self._budget(model, int(max_tok or 2048)))
                messages = self._compact(messages, budget)
                live["approx_prompt_tokens"] = sum(len(str(x.get("content") or "")) for x in messages) // 4
                self._event(task_id, "context_trim", {"model": model, "n_ctx": self._ctx_tokens[model],
                                                      "chars_before": sent,
                                                      "chars_after": sum(len(x["content"]) for x in messages)})
                log.info("Task %s: konteks %s terlampaui (%s token), riwayat dipangkas %d -> %d karakter",
                         task_id, model, self._ctx_tokens[model], sent, budget)
                await asyncio.wait_for(collect(), self.s.agent_model_timeout)
        finally:
            ai.release(cid, model)
        secs = time.time() - started
        text = "".join(parts)
        st = dict(prov.last_stats)
        tokens = int(st.get("completion_tokens") or max(1, len(text) // 4))
        stats = {"seconds": round(secs, 1), "tokens": tokens,
                 "tps": round(float(st.get("gen_tps") or tokens / max(secs, 0.01)), 2),
                 "prompt_tokens": st.get("prompt_tokens"), "connection": row["name"], "location": row["location"],
                 "thinking_tokens": thinking["tokens"], "profile": "cepat" if role == "executor" else "kualitas",
                 "temperature": temp}
        return text, model, stats

    async def _ask_file_content(self, task_id: str, messages: list[dict], target: tuple[str, str], role: str,
                                path: str) -> str | None:
        """Lanjutan write_file: minta HANYA isi file. Tidak dihitung sebagai langkah task."""
        ask = (f"[lanjutan] JSON-mu memanggil write_file untuk {path} tetapi isinya belum ada. "
               f"Balas SEKARANG hanya dengan isi LENGKAP file {path} di dalam satu blok kode ```, tanpa JSON "
               f"dan tanpa penjelasan.")
        messages.append({"role": "user", "content": ask})
        self._update(task_id, current_op=f"Meminta isi {path} dari model", last_activity=_now())
        try:
            text, model, stats = await self._ask_model(task_id, self._compact(messages), target, role)
        except (AppError, asyncio.TimeoutError):
            messages.pop()
            return None
        messages.append({"role": "assistant", "content": text})
        content = None
        for m in re.finditer(r"```([^\n`]*)\n(.*?)```", text, re.S):
            body = m.group(2)
            if body.lstrip().startswith("{") and '"tool"' in body:  # model malah mengirim tool call lagi
                continue
            content = body
            break
        if content is None and "```" not in text and '"tool"' not in text and text.strip():
            content = text.strip("\n") + "\n"  # tanpa pagar kode: pakai teks apa adanya
        self._event(task_id, "continuation", {"path": path, "model": model, "ok": bool(content),
                                              "chars": len(content or ""), **{k: stats[k] for k in ("seconds", "tokens")}})
        return content if content and content.strip() else None

    async def _run(self, task_id: str, user: dict) -> None:
        async with self._sem:
            try:
                await asyncio.wait_for(self._loop(task_id, user), self.s.agent_task_timeout)
            except asyncio.TimeoutError:
                self._fail(task_id, f"Melebihi batas waktu task ({self.s.agent_task_timeout} detik)")
            except asyncio.CancelledError:
                if task_id in self._pause_now:  # jeda segera (bukan batal)
                    self._pause_now.discard(task_id)
                    self._pause.discard(task_id)
                    self._live.pop(task_id, None)
                    self._set_stage(task_id, "PAUSED", "Dijeda pengguna — langkah yang belum selesai diulang saat dilanjutkan")
                    return
                row = self.db.one("SELECT status FROM agent_tasks WHERE id=?", (task_id,))
                if row and row["status"] not in TERMINAL:
                    self._update(task_id, status="CANCELLED", current_op="Dibatalkan", finished_at=_now())
                    self._event(task_id, "status", {"status": "CANCELLED", "message": "Dibatalkan"})
                raise
            except AppError as e:
                log.warning("Task agen %s gagal: %s", task_id, e.message)
                self._fail(task_id, e.message)
            except Exception as e:  # jangan biarkan task menggantung tanpa status
                log.exception("Task agen %s error", task_id)
                self._fail(task_id, f"Kesalahan internal: {e}")

    def _fail(self, task_id: str, msg: str) -> None:
        self._update(task_id, status="FAILED", error=msg[:2000], current_op="", finished_at=_now())
        self._event(task_id, "error", {"message": msg})
        self._event(task_id, "status", {"status": "FAILED", "message": msg})

    def _set_stage(self, task_id: str, status: str, op: str) -> None:
        self._update(task_id, status=status, stage=status, current_op=op[:300], last_activity=_now())
        self._event(task_id, "status", {"status": status, "message": op[:300]})

    async def _loop(self, task_id: str, user: dict) -> None:
        row = self._row(task_id)
        svc = self.svc
        root = svc.projects.project_dir(row["project_id"])
        svc.projects.get(row["project_id"], user)  # akses proyek masih sah?
        ai_perms = intersect_for_ai(user["perms"])
        ck = json.loads(row["checkpoint"]) if row.get("checkpoint") else {}
        ast = ck.get("agent_state") or {}
        task = {"id": task_id, "project_id": row["project_id"], "auto_apply": bool(row["auto_apply"]),
                "_plan": json.loads(row.get("plan") or "[]"), "_runs": ck.get("runs", []),
                # status peran/eskalasi/peninjauan (ikut checkpoint agar bertahan saat dijeda/restart)
                "_esc_role": ast.get("esc_role"), "_esc_left": int(ast.get("esc_left") or 0),
                "_reviews": int(ast.get("reviews") or 0), "_review_pending": bool(ast.get("review_pending")),
                "_fail_runs": int(ast.get("fail_runs") or 0), "_free_plans": int(ast.get("free_plans") or 0)}
        messages = self._messages(row, ai_perms)
        steps_used = row["steps_used"]
        parse_fails = 0
        if not row.get("started_at"):
            self._update(task_id, started_at=_now())
        self._set_stage(task_id, "PLANNING" if not task["_plan"] else "EXECUTING", "Menghubungi model AI")
        pending_call = ck.get("pending_call")
        last_failed_run = False
        same_err = {"sig": None, "n": 0}  # error tool yang sama berturut-turut (model terjebak mengulang)
        fail_limit = max(1, int(svc.ai.agent_models().get("escalate_after_failures") or 2))

        def extra(pc: dict | None = None) -> dict:
            return {"runs": task["_runs"], "pending_call": pc, "agent_state": {
                "esc_role": task["_esc_role"], "esc_left": task["_esc_left"], "reviews": task["_reviews"],
                "review_pending": task["_review_pending"], "fail_runs": task["_fail_runs"],
                "free_plans": task["_free_plans"]}}

        while True:
            if task_id in self._pause:
                self._pause.discard(task_id)
                self._save_checkpoint(task_id, messages, extra(pending_call))
                self._set_stage(task_id, "PAUSED", "Dijeda pengguna")
                return
            if pending_call is None:
                if steps_used >= row["max_steps"]:
                    self._finish(task_id, task, steps_used, {"summary": None},
                                 incomplete=f"Batas {row['max_steps']} langkah tercapai sebelum agen memanggil finish")
                    return
                role = self._pick_role(task)
                target = self._target(role)
                # Sinyal untuk UI (animasi "Berpikir"): model mana yang sedang menyusun langkah berikutnya.
                self._update(task_id, current_op=f"{ROLE_LABEL[role]} ({target[1]}) sedang berpikir…",
                             last_activity=_now())
                self._event(task_id, "thinking", {"step": steps_used + 1, "role": role, "model": target[1]})
                try:
                    text, model, stats = await self._ask_model(task_id, self._compact(messages), target, role)
                except (AppError, asyncio.TimeoutError) as e:
                    msg = e.message if isinstance(e, AppError) else \
                        f"tidak menjawab dalam {self.s.agent_model_timeout} detik"
                    self._event(task_id, "error", {"message": f"Model {target[1]} gagal: {msg}"})
                    if self._escalate(task_id, task, f"Model {target[1]} gagal: {msg}", target):
                        self._save_checkpoint(task_id, messages, extra())
                        continue
                    self._save_checkpoint(task_id, messages, extra())
                    raise AppError(f"Model {target[1]} gagal: {msg}", code="ai_error")
                steps_used += 1
                self._update(task_id, steps_used=steps_used, model=model, connection_id=target[0])
                messages.append({"role": "assistant", "content": text})
                try:
                    call, code = extract_call(text)
                    parse_fails = 0
                except ValueError as e:
                    parse_fails += 1
                    self._event(task_id, "error", {"message": f"Balasan {model} tidak valid: {e}", "raw": text[:2000],
                                                   "role": role, "model": model})
                    messages.append({"role": "user", "content": "[hasil tool] FORMAT SALAH: balas dengan tepat satu "
                                     "blok ```json berisi {\"thought\", \"tool\", \"args\"}."})
                    if parse_fails >= ESCALATE_AFTER_PARSE and self._escalate(
                            task_id, task, f"{model} berulang kali salah format JSON tool", target):
                        parse_fails = 0
                        self._save_checkpoint(task_id, messages, extra())
                        continue
                    if parse_fails >= MAX_PARSE_FAILS:
                        self._save_checkpoint(task_id, messages, extra())
                        self._fail(task_id, "Model berulang kali tidak mengikuti format JSON tool. Coba model lain "
                                            "atau atur model Perencana/Online untuk eskalasi.")
                        return
                    continue
                if task["_esc_left"] > 0 and role == task["_esc_role"]:
                    task["_esc_left"] -= 1
                    if task["_esc_left"] == 0:
                        self._event(task_id, "escalation_end", {"role": task["_esc_role"], "model": model})
                        task["_esc_role"] = None
                pending_call = {"tool": call["tool"], "args": call.get("args") or {}, "code": code,
                                "thought": str(call.get("thought", ""))[:2000]}
                # write_file tanpa isi (model sering berhenti setelah JSON): minta isinya langsung, TANPA
                # menghabiskan langkah. Dulu ini memakan 1 langkah + 1 error untuk hampir setiap file.
                pargs = pending_call["args"]
                if (call["tool"] == "write_file" and code is None and isinstance(pargs, dict)
                        and pargs.get("content") is None and isinstance(pargs.get("path"), str)):
                    filled = await self._ask_file_content(task_id, messages, target, role, pargs["path"])
                    if filled is not None:
                        pending_call["code"] = filled
                self._event(task_id, "thought", {"text": pending_call["thought"], "role": role, "model": model, **stats})
                if role == "reviewer":
                    task["_review_pending"] = False
                    self._event(task_id, "review", {"model": model, "approved": call["tool"] == "finish"})
                elif (call["tool"] == "finish" and svc.ai.role_target("reviewer") is not None
                      and task["_reviews"] < MAX_REVIEWS):
                    # Tahan dulu: Peninjau memeriksa hasil sebelum task dinyatakan selesai.
                    task["_reviews"] += 1
                    task["_review_pending"] = True
                    messages.append({"role": "user", "content": REVIEW_PROMPT})
                    self._set_stage(task_id, "REVIEWING", "Peninjau memeriksa hasil sebelum task selesai")
                    self._save_checkpoint(task_id, messages, extra())
                    pending_call = None
                    continue

            name = pending_call["tool"]
            tool = agent_tools.TOOLS.get(name)
            stage = tool.stage if tool else "EXECUTING"
            if stage == "EXECUTING" and last_failed_run:
                stage = "FIXING"
            self._set_stage(task_id, stage, f"{name}: {json.dumps(pending_call['args'], ensure_ascii=False)[:200]}")
            self._event(task_id, "tool_call", {"tool": name, "args": pending_call["args"],
                                               "has_code_block": pending_call.get("code") is not None})
            ctx = ToolContext(svc=svc, user=user, task=task, root=root, ai_perms=ai_perms,
                              code_block=pending_call.get("code"))
            runs_before = len(task["_runs"])
            try:
                obs = await agent_tools.call(ctx, name, pending_call["args"])
                ok = True
            except NeedsApproval:
                self._save_checkpoint(task_id, messages, extra(pending_call))
                self._set_stage(task_id, "WAITING_APPROVAL",
                                "Menunggu persetujuan proposal sebelum menjalankan/menguji kode")
                self._event(task_id, "approval", {"pending": self.public(self._row(task_id))["pending_proposals"]})
                return
            except ToolError as e:
                obs, ok = f"ERROR: {e}", False
            pending_call = None
            sig = f"{name}|{obs[:200]}" if not ok else None
            same_err["n"] = (same_err["n"] + 1 if sig == same_err["sig"] else 1) if sig else 0
            same_err["sig"] = sig
            if same_err["n"] >= 2:
                obs += ("\nPERINGATAN: kesalahan yang SAMA terulang. Jangan kirim panggilan yang sama lagi; "
                        "ikuti contoh format di atas dengan tepat.")
                if task["_esc_left"] == 0:
                    cur = self._target(self._pick_role(task))
                    if self._escalate(task_id, task, f"Error yang sama terulang {same_err['n']}x ({name})", cur):
                        same_err["n"] = 0
            if len(task["_runs"]) > runs_before:
                r = task["_runs"][-1]
                last_failed_run = not (r["status"] == "COMPLETED" and r["exit_code"] == 0)
                task["_fail_runs"] = task["_fail_runs"] + 1 if last_failed_run else 0
                if task["_fail_runs"] >= fail_limit and task["_esc_left"] == 0:
                    cur = self._target(self._pick_role(task))
                    if self._escalate(task_id, task, f"Verifikasi gagal {task['_fail_runs']} kali berturut-turut", cur):
                        task["_fail_runs"] = 0
            self._event(task_id, "observation", {"tool": name, "ok": ok, "text": obs[:8000]})
            if name == "update_plan" and ok:
                self._update(task_id, plan=json.dumps(task["_plan"], ensure_ascii=False))
                self._event(task_id, "plan", {"steps": task["_plan"]})
                # Memperbarui rencana hanya pencatatan: tidak menghabiskan jatah langkah (maks FREE_PLAN_UPDATES
                # kali per task supaya tidak bisa jadi loop tanpa akhir).
                if task["_free_plans"] < FREE_PLAN_UPDATES and steps_used > 0:
                    task["_free_plans"] += 1
                    steps_used -= 1
                    self._update(task_id, steps_used=steps_used)
            self._update(task_id, progress=self._progress(task, steps_used, row["max_steps"]))
            messages.append({"role": "user", "content": f"[hasil tool {name}]\n{obs}"})
            self._save_checkpoint(task_id, messages, extra())
            if name == "finish" and ok:
                self._finish(task_id, task, steps_used, task.get("_finish") or {})
                return

    def _finish(self, task_id: str, task: dict, steps_used: int, fin: dict, incomplete: str | None = None) -> None:
        props = self.db.all("SELECT id, path, action, status, risk, additions, deletions FROM ai_proposals "
                            "WHERE task_id=? ORDER BY id", (task_id,))
        runs = task.get("_runs") or []
        report = {
            "verified": {
                "proposals": props,
                "files_changed": sorted({p["path"] for p in props if p["status"] == "approved"}),
                "files_pending": sorted({p["path"] for p in props if p["status"] == "pending"}),
                "runs": runs,
                "tests_passed": sum(1 for r in runs if r["kind"] == "test" and r["status"] == "COMPLETED"
                                    and r["exit_code"] == 0),
                "tests_failed": sum(1 for r in runs if r["kind"] == "test" and not (r["status"] == "COMPLETED"
                                                                                   and r["exit_code"] == 0)),
                "steps_used": steps_used,
                "plan": task.get("_plan") or [],
            },
            "ai_generated": {k: fin.get(k) for k in ("summary", "limitations", "remaining")},
            "note": "Bagian 'verified' dihitung server dari data nyata; 'ai_generated' adalah klaim model.",
        }
        if incomplete:
            report["incomplete"] = incomplete
        status = "FAILED" if incomplete else "COMPLETED"
        self._update(task_id, status=status, stage=status, report=json.dumps(report, ensure_ascii=False, default=str),
                     progress=1.0 if not incomplete else self._progress(task, steps_used, 1), current_op="",
                     error=incomplete or "", finished_at=_now())
        self._event(task_id, "report", report)
        self._event(task_id, "status", {"status": status, "message": incomplete or "Task selesai"})


def _loop_running() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False
