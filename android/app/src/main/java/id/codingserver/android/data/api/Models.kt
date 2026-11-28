package id.codingserver.android.data.api

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable data class ErrorBody(val code: String = "", val message: String = "", val details: JsonElement? = null)
@Serializable data class ErrorResponse(val error: ErrorBody)
@Serializable data class OkResponse(val ok: Boolean = true, val message: String = "")

// ---------- auth ----------
@Serializable data class LoginRequest(val username: String, val password: String)
@Serializable data class RefreshRequest(val refresh_token: String)
@Serializable data class LogoutRequest(val refresh_token: String? = null)
@Serializable data class UserOut(
    val id: Int, val username: String, val role: String, val is_active: Boolean = true,
    val permissions: List<String> = emptyList(), val created_at: Double = 0.0,
    val display_name: String = "", val email: String = "", val bio: String = "",
    /** Admin utama: tidak bisa dihapus/diubah; sandinya hanya diatur dari server (akun pemulihan). */
    val is_root: Boolean = false, val updated_at: Double = 0.0, val last_login_at: Double? = null,
    /** Tidak null = punya foto profil (GET auth/users/{id}/avatar); nilainya berubah tiap foto diganti. */
    val avatar_version: Double? = null,
) {
    val shownName: String get() = display_name.ifBlank { username }
}
@Serializable data class ProfileUpdate(val display_name: String? = null, val email: String? = null, val bio: String? = null)
@Serializable data class PasswordChange(val old_password: String, val new_password: String)
@Serializable data class UserCreate(
    val username: String, val password: String, val role: String = "developer",
    val display_name: String = "", val email: String = "",
)
@Serializable data class UserUpdate(
    val role: String? = null, val is_active: Boolean? = null, val password: String? = null,
    val display_name: String? = null, val email: String? = null,
)
@Serializable data class UserDeleted(val ok: Boolean = true, val message: String = "", val username: String = "",
                                     val projects_moved: Int = 0)
@Serializable data class TokenResponse(
    val access_token: String, val refresh_token: String, val token_type: String = "bearer",
    val expires_at: Long, val refresh_expires_at: Long, val user: UserOut,
)

// ---------- system ----------
@Serializable data class Health(
    val status: String, val version: String = "", val time: Double = 0.0, val database: Boolean = true,
    val sandbox: Boolean = false, val name: String = "",
)
@Serializable data class SystemInfo(
    val hostname: String = "", val board: String? = null, val os: String? = null, val kernel: String = "",
    val architecture: String = "", val cpu_count: Int = 0, val python: String = "", val server_version: String = "",
    val uptime_seconds: Long = 0, val server_uptime_seconds: Long = 0, val workspace: String = "",
)
@Serializable data class CpuInfo(val percent: Double = 0.0, val per_cpu: List<Double> = emptyList(),
                                 val load_avg: List<Double> = emptyList(), val freq_mhz: Double? = null)
@Serializable data class MemInfo(val total: Long = 0, val available: Long = 0, val used: Long = 0, val percent: Double = 0.0,
                                 val swap_total: Long = 0, val swap_used: Long = 0)
@Serializable data class DiskInfo(val path: String = "", val total: Long = 0, val used: Long = 0, val free: Long = 0,
                                  val percent: Double = 0.0)
@Serializable data class NetIf(val `interface`: String, val up: Boolean = false, val ipv4: List<String> = emptyList())
@Serializable data class NetInfo(val interfaces: List<NetIf> = emptyList(), val bytes_sent: Long = 0, val bytes_recv: Long = 0)
@Serializable data class QueueStats(val max_concurrent: Int = 0, val running: Int = 0, val waiting: Int = 0)
@Serializable data class Resources(
    val cpu: CpuInfo = CpuInfo(), val memory: MemInfo = MemInfo(), val disk: DiskInfo = DiskInfo(),
    val temperature_c: Double? = null, val uptime_seconds: Long = 0, val network: NetInfo = NetInfo(),
    val jobs: QueueStats? = null,
)
@Serializable data class EngineStatus(
    val engine_id: String, val language: String, val extensions: List<String> = emptyList(), val build: Boolean = true,
    val run: Boolean = true, val status: String, val version: String? = null, val executable: String? = null,
)
@Serializable data class Engines(val engines: List<EngineStatus>)
@Serializable data class RecentFile(val project_id: String, val path: String, val opened_at: Double = 0.0)
@Serializable data class Dashboard(
    val info: SystemInfo = SystemInfo(), val resources: Resources = Resources(), val projects_count: Int = 0,
    val recent_projects: List<Project> = emptyList(), val recent_files: List<RecentFile> = emptyList(),
    val active_executions: List<Job> = emptyList(), val jobs: QueueStats = QueueStats(), val terminal_sessions: Int = 0,
)
@Serializable data class ProcInfo(val pid: Int, val name: String? = null, val user: String? = null,
                                  val cpu_percent: Double? = null, val rss_mb: Double = 0.0, val cmd: String = "")
@Serializable data class Processes(val processes: List<ProcInfo> = emptyList(), val jobs: List<Job> = emptyList(), val terminals: Int = 0)

// ---------- projects & files ----------
@Serializable data class Project(
    val id: String, val name: String, val description: String = "", val language: String = "", val owner_id: Int = 0,
    val created_at: Double = 0.0, val updated_at: Double = 0.0, val path_exists: Boolean = true,
)
@Serializable data class ProjectCreate(val name: String, val description: String = "", val language: String = "", val template: Boolean = true)
@Serializable data class ProjectUpdate(val name: String? = null, val description: String? = null, val language: String? = null)
@Serializable data class Templates(val languages: List<String>)

@Serializable data class FormatRequest(val project_id: String, val path: String, val content: String, val tab_size: Int = 4)
@Serializable data class FormatResult(val content: String, val changed: Boolean = false, val formatter: String = "")

@Serializable data class ProjectFiles(val files: List<String> = emptyList(), val truncated: Boolean = false)

@Serializable data class FileEntry(
    val name: String, val path: String, val type: String, val size: Long = 0, val modified: Double = 0.0,
    val extension: String = "", val language: String = "", val mime: String? = null,
    val children: List<FileEntry>? = null, val truncated: Boolean? = null,
    // hasil pencarian isi file
    val line: Int? = null, val text: String? = null,
) {
    val isFolder: Boolean get() = type == "folder"
}
@Serializable data class FileContent(
    val name: String, val path: String, val type: String = "file", val size: Long = 0, val modified: Double = 0.0,
    val extension: String = "", val language: String = "", val binary: Boolean = false, val content: String? = null,
    val encoding: String? = null, val sha256: String = "",
)
@Serializable data class FileWritten(
    val name: String, val path: String, val type: String = "file", val size: Long = 0, val modified: Double = 0.0,
    val sha256: String? = null,
)
@Serializable data class FileCreate(val project_id: String, val path: String, val type: String = "file", val content: String = "")
@Serializable data class FileWrite(val project_id: String, val path: String, val content: String, val expected_sha256: String? = null)
@Serializable data class FileRename(val project_id: String, val path: String, val new_name: String)
@Serializable data class FileMove(val project_id: String, val path: String, val destination: String, val overwrite: Boolean = false)
@Serializable data class FavoriteRequest(val project_id: String, val path: String)
@Serializable data class FileList(val files: List<RecentFile> = emptyList())
@Serializable data class HistoryEntry(
    val id: Int, val path: String, val action: String, val sha256: String? = null, val size: Long? = null,
    val actor_type: String = "user", val note: String = "", val created_at: Double = 0.0,
)
@Serializable data class HistoryList(val history: List<HistoryEntry> = emptyList())
@Serializable data class RestoreRequest(val project_id: String, val history_id: Int)

// ---------- execution ----------
@Serializable data class RunRequest(
    val project_id: String, val path: String, val language: String? = null, val args: List<String> = emptyList(),
    val stdin: String? = null, val interactive: Boolean = false, val timeout: Int? = null,
)
@Serializable data class Job(
    val process_id: String, val project_id: String = "", val user_id: Int = 0, val action: String = "run",
    val language: String = "", val file: String = "", val status: String = "QUEUED", val exit_code: Int? = null,
    val command: List<List<String>> = emptyList(), val error: String = "", val created_at: Double = 0.0,
    val start_time: Double? = null, val end_time: Double? = null, val duration: Double? = null,
    val truncated: Boolean = false, val preview_path: String? = null, val stdout: String? = null, val stderr: String? = null,
) {
    val finished: Boolean get() = status in setOf("COMPLETED", "FAILED", "TIMEOUT", "CANCELLED")
}
@Serializable data class JobList(val executions: List<Job> = emptyList(), val queue: QueueStats = QueueStats())
@Serializable data class StdinRequest(val data: String = "", val eof: Boolean = false)
@Serializable data class Artifact(val path: String, val size: Long = 0, val modified: Double = 0.0, val location: String = "")
@Serializable data class Artifacts(val artifacts: List<Artifact> = emptyList())
@Serializable data class PreviewToken(val url: String, val expires_at: Long = 0)

// ---------- terminal ----------
@Serializable data class TerminalCreate(val project_id: String, val cwd: String = "", val cols: Int = 80, val rows: Int = 24)
@Serializable data class TerminalSession(
    val session_id: String, val owner_id: Int = 0, val project_id: String = "", val working_directory: String = "",
    val created_at: Double = 0.0, val last_activity: Double = 0.0, val status: String = "", val exit_code: Int? = null,
    val history: List<String> = emptyList(),
)

// ---------- database ----------
@Serializable data class DbItem(val name: String, val size: Long = 0, val modified: Double = 0.0)
@Serializable data class DbList(val databases: List<DbItem> = emptyList())
@Serializable data class DbCreate(val name: String, val project_id: String? = null)
@Serializable data class DbQuery(
    val database: String, val project_id: String? = null, val sql: String, val mode: String = "read",
    val confirm: Boolean = false,
)
@Serializable data class StmtResult(
    val statement: String = "", val columns: List<String>? = null, val rows: List<List<JsonElement>>? = null,
    val truncated: Boolean = false, val rowcount: Int? = null,
)
@Serializable data class DbQueryResult(val results: List<StmtResult> = emptyList(), val duration_ms: Double = 0.0, val mode: String = "")
@Serializable data class DbColumn(val cid: Int = 0, val name: String, val type: String = "", val notnull: Boolean = false, val pk: Boolean = false)
@Serializable data class DbObject(val type: String, val name: String, val table: String = "", val sql: String? = null,
                                  val columns: List<DbColumn>? = null, val row_count: Long? = null)
@Serializable data class DbSchema(val objects: List<DbObject> = emptyList())
@Serializable data class DbRef(val database: String, val project_id: String? = null)

// ---------- git ----------
@Serializable data class GitProject(val project_id: String)
@Serializable data class GitFile(val index: String = " ", val worktree: String = " ", val path: String)
@Serializable data class GitStatus(val branch: String = "", val files: List<GitFile> = emptyList(), val clean: Boolean = true)
@Serializable data class GitResult(val exit_code: Int? = null, val stdout: String = "", val stderr: String = "", val ok: Boolean = false)
@Serializable data class GitCommit(val project_id: String, val message: String, val add_all: Boolean = true)
@Serializable data class Commit(val hash: String, val author: String = "", val email: String = "", val date: String = "", val message: String = "")
@Serializable data class GitLog(val commits: List<Commit> = emptyList())
@Serializable data class GitBranches(val current: String? = null, val branches: List<String> = emptyList())
@Serializable data class GitBranch(val project_id: String, val name: String, val checkout: Boolean = true)
@Serializable data class GitCheckout(val project_id: String, val ref: String)
@Serializable data class GitRemoteOp(val project_id: String, val remote: String = "origin", val branch: String? = null)
@Serializable data class GitRemoteSet(val project_id: String, val name: String = "origin", val url: String)
@Serializable data class GitClone(val url: String, val name: String? = null, val branch: String? = null)
@Serializable data class GitCloneResult(val project: Project, val ok: Boolean = false, val stdout: String = "", val stderr: String = "")
@Serializable data class GitCredential(val host: String = "github.com", val username: String, val token: String)
@Serializable data class GitCredInfo(val host: String, val username: String, val created_at: Double = 0.0)
@Serializable data class GitCreds(val credentials: List<GitCredInfo> = emptyList())

// ---------- http ----------
@Serializable data class HttpRequestIn(
    val method: String = "GET", val url: String, val headers: Map<String, String> = emptyMap(),
    val params: Map<String, String> = emptyMap(), val body: String? = null, val body_type: String = "none",
    val form: Map<String, String>? = null, val follow_redirects: Boolean = true,
)
@Serializable data class HttpResponseOut(
    val status_code: Int, val reason: String = "", val http_version: String = "", val url: String = "",
    val headers: Map<String, String> = emptyMap(), val body: String = "", val size: Long = 0, val truncated: Boolean = false,
    val time_ms: Double = 0.0,
)
@Serializable data class HttpSaved(
    val id: Int? = null, val name: String, val collection: String = "default", val method: String = "GET", val url: String,
    val headers: Map<String, String> = emptyMap(), val params: Map<String, String> = emptyMap(), val body: String? = null,
    val body_type: String = "none",
)
@Serializable data class HttpCollection(val name: String, val requests: List<HttpSaved> = emptyList())
@Serializable data class HttpCollections(val collections: List<HttpCollection> = emptyList())

// ---------- backup ----------
@Serializable data class BackupInfo(val name: String, val size: Long = 0, val created_at: Double = 0.0)
@Serializable data class BackupList(val backups: List<BackupInfo> = emptyList(), val retention: Int = 0)
@Serializable data class BackupCreate(val label: String = "manual")

// ---------- AI ----------
@Serializable data class AIConnection(
    val id: String, val name: String, val kind: String, val location: String, val base_url: String,
    val has_key: Boolean = false, val created_at: Double = 0.0,
)
@Serializable data class AIConnections(val connections: List<AIConnection> = emptyList())
@Serializable data class AIPreset(
    val key: String, val name: String, val kind: String, val location: String, val base_url: String,
    val needs_key: Boolean = false, val note: String = "",
)
@Serializable data class AIPresets(val presets: List<AIPreset> = emptyList())
@Serializable data class AIConnectionIn(
    val name: String, val kind: String, val location: String, val base_url: String, val api_key: String? = null,
)
@Serializable data class AIModel(val id: String, val status: String? = null, val context_length: Long? = null)
@Serializable data class AIModels(val models: List<AIModel> = emptyList())
/** Konteks model llama-server: ctx = yang sedang dipakai; configured = dari pengaturan; override = khusus model. */
@Serializable data class ContextModel(val id: String, val status: String? = null, val ctx: Int? = null,
                                      val configured: Int? = null, val override: Int? = null)
@Serializable data class ContextStatus(
    val connection_id: String, val preset_file: String = "", val default_ctx: Int? = null,
    val models: List<ContextModel> = emptyList(), val problems: List<String> = emptyList(), val ready: Boolean = false,
    val fix_command: String = "",
)
/** models: nama -> token; 0 = kembali ikut bawaan. */
@Serializable data class ContextIn(val connection_id: String, val default_ctx: Int? = null,
                                   val models: Map<String, Int>? = null)
@Serializable data class AIApply(val connection_id: String, val model: String, val wait: Boolean = false)
@Serializable data class AISettings(
    val system_prompt: String = "", val temperature: Double = 0.7, val max_tokens: Int = 2048,
    val idle_unload_minutes: Int = 15, val history_messages: Int = 20,
)
// ---------- Peran model agent & Uji Model ----------
@Serializable data class AgentModelTarget(val connection_id: String, val model: String)
@Serializable data class AgentRoleModel(
    val connection_id: String, val model: String, val connection_name: String = "", val location: String = "local",
)
@Serializable data class AgentModels(
    val planner: AgentRoleModel? = null, val executor: AgentRoleModel? = null, val reviewer: AgentRoleModel? = null,
    val online: AgentRoleModel? = null, val allow_online: Boolean = false, val escalate_after_failures: Int = 2,
    val max_loaded_models: Int = 2, val default: AgentModelTarget? = null,
    /** Batas langkah bawaan task baru, dan batas atas yang diizinkan server. */
    val max_steps: Int = 30, val max_steps_limit: Int = 100,
    /** Izin agent menerapkan editan file: manual | otomatis | penuh (bawaan task baru). */
    val approval_mode: String = "manual",
)
/** Hasil "Lepas semua model": model yang dibongkar, dilewati (sedang dipakai), dan error per koneksi. */
@Serializable data class UnloadAllResult(
    val unloaded: List<String> = emptyList(), val skipped: List<String> = emptyList(), val errors: List<String> = emptyList(),
    /** Hanya pada force=true: task agent yang dijeda & Uji Model yang dihentikan. */
    val paused_tasks: List<String> = emptyList(), val cancelled_bench: List<String> = emptyList(),
)
@Serializable data class BenchSummary(
    val score: Double = 0.0, val passed: Int = 0, val total: Int = 0, val format_ok: Int = 0,
    val avg_tps: Double? = null, val avg_seconds: Double = 0.0, val total_seconds: Double = 0.0, val tokens: Int = 0,
    val verdict: String = "", val thinking_tokens: Int = 0, val empty_answers: Int = 0, val variant: String? = null,
)
@Serializable data class BenchCaseResult(
    val id: String, val title: String = "", val category: String = "", val format_ok: Boolean = false,
    val score: Double = 0.0, val note: String = "", val tool: String? = null, val seconds: Double = 0.0,
    val tokens: Int = 0, val tps: Double? = null, val prompt_tokens: Int? = null, val output: String = "",
    val thinking_tokens: Int = 0, val empty: Boolean = false,
)
@Serializable data class BenchRun(
    val id: String, val connection_id: String = "", val model: String = "", val connection_name: String = "",
    val location: String = "local", val status: String = "PENDING", val current: String = "", val error: String = "",
    val created_at: Double = 0.0, val started_at: Double? = null, val finished_at: Double? = null,
    val done_cases: Int = 0, val total_cases: Int = 0, val summary: BenchSummary? = null,
    val results: List<BenchCaseResult> = emptyList(),
    val live: BenchLive? = null, val log: List<BenchLogEntry> = emptyList(),
    val mode: String = "cepat", val variants: List<BenchVariant> = emptyList(),
    val profile_decision: ProfileDecision? = null,
)
@Serializable data class BenchVariant(
    val key: String = "", val label: String = "", val params: ModelPreset = ModelPreset(), val describe: String? = null,
    val summary: BenchSummary? = null, val results: List<BenchCaseResult> = emptyList(),
)
@Serializable data class ProfileDecision(
    val saved: Boolean = false, val status: String = "", val saran: List<String> = emptyList(),
    val pilihan: Map<String, String> = emptyMap(),
)

// ---------- Profil model ----------
@Serializable data class ModelPreset(
    val temperature: Double? = null, val top_p: Double? = null, val top_k: Int? = null, val min_p: Double? = null,
    val presence_penalty: Double? = null, val repeat_penalty: Double? = null, val thinking: Boolean? = null,
    val max_tokens: Int = 2048,
)
@Serializable data class ModelPresets(val kualitas: ModelPreset = ModelPreset(), val cepat: ModelPreset = ModelPreset())
@Serializable data class CalibVariant(
    val key: String = "", val label: String = "", val score: Double? = null, val avg_seconds: Double? = null,
    val format_ok: Int? = null, val total: Int? = null, val passed: Int? = null, val avg_tps: Double? = null,
    val thinking_tokens: Int? = null,
)
@Serializable data class Calibration(
    val tanggal: Double = 0.0, val run_id: String? = null, val pilihan: Map<String, String> = emptyMap(),
    val varian: List<CalibVariant> = emptyList(), val saran: List<String> = emptyList(),
)
@Serializable data class ProfileSync(val status: String = "", val message: String = "", val at: Double = 0.0)
@Serializable data class ModelProfile(
    val model: String, val family: String = "", val thinking_supported: Boolean? = null, val source: String = "bawaan",
    val status: String = "ok", val active: Boolean = true, val kegunaan: List<String> = emptyList(),
    val catatan: String = "", val prompt_tambahan: String = "", val preset: ModelPresets = ModelPresets(),
    val kalibrasi: Calibration? = null, val updated_at: Double? = null, val sync: ProfileSync? = null,
    val file: String = "",
)
@Serializable data class ProfilePurpose(val key: String, val label: String)
@Serializable data class ModelProfiles(
    val profiles: List<ModelProfile> = emptyList(), val purposes: List<ProfilePurpose> = emptyList(),
    val dir: String = "", val git: Boolean = true,
)
@Serializable data class ModelProfileUpdate(
    val active: Boolean? = null, val kegunaan: List<String>? = null, val catatan: String? = null,
    val prompt_tambahan: String? = null, val kualitas: ModelPreset? = null, val cepat: ModelPreset? = null,
)
@Serializable data class ModelProfileImport(val profile: kotlinx.serialization.json.JsonObject)
/** Keadaan langsung uji yang sedang berjalan. phase: loading|prompt|thinking|writing|checking */
@Serializable data class BenchLive(
    val phase: String = "", val case: String? = null, val elapsed: Double = 0.0, val tokens: Int = 0,
    val reasoning_tokens: Int = 0, val first_token_s: Double? = null, val tps: Double? = null, val text: String = "",
    val approx_prompt_tokens: Int? = null,
    /** Hanya untuk AI Agent: peran & model yang sedang bekerja. */
    val role: String? = null, val model: String? = null,
)
@Serializable data class BenchLogEntry(val ts: Double = 0.0, val kind: String = "", val text: String = "")
@Serializable data class BenchCase(val id: String, val title: String = "", val category: String = "", val description: String = "")
@Serializable data class BenchPick(val connection_id: String, val model: String, val score: Double = 0.0, val avg_tps: Double? = null)
@Serializable data class BenchRecommendation(val planner: BenchPick? = null, val executor: BenchPick? = null, val reviewer: BenchPick? = null)
@Serializable data class BenchOverview(
    val runs: List<BenchRun> = emptyList(), val leaderboard: List<BenchRun> = emptyList(),
    val recommendation: BenchRecommendation = BenchRecommendation(), val cases: List<BenchCase> = emptyList(),
)
@Serializable data class BenchStart(val targets: List<AgentModelTarget>, val mode: String = "cepat")
@Serializable data class BenchRuns(val runs: List<BenchRun> = emptyList())

@Serializable data class AISelected(val connection_id: String? = null, val model: String? = null)
@Serializable data class AIStatus(
    val status: String = "idle", val connection_id: String? = null, val model: String? = null, val message: String = "",
    val loaded_by_us: Boolean = false, val target: String? = null, val configured: Boolean = false,
    val connection: AIConnection? = null, val settings: AISettings = AISettings(), val selected: AISelected = AISelected(),
    val ai_permissions: List<String> = emptyList(),
)
@Serializable data class AIConversationSummary(
    val id: Int, val title: String = "", val model: String? = null, val updated_at: Double = 0.0, val messages: Int = 0,
)
@Serializable data class AIConversations(val conversations: List<AIConversationSummary> = emptyList())
@Serializable data class AIMessage(
    val id: Int = 0, val role: String, val content: String, val reasoning: String = "", val model: String = "",
    val created_at: Double = 0.0,
)
@Serializable data class AIConversationDetail(val id: Int, val title: String = "", val messages: List<AIMessage> = emptyList())
@Serializable data class AIConversationIn(val title: String = "Percakapan baru")
@Serializable data class AIChat(val messages: List<Map<String, String>>, val project_id: String? = null, val files: List<String> = emptyList())
/** Usulan perubahan file dari AI (tanpa isi penuh; cukup diff). status: pending|approved|rejected|reverted|failed */
@Serializable data class AIProposalItem(
    val id: Int, val path: String, val action: String = "write", val status: String = "pending",
    val diff: String? = "", val additions: Int = 0, val deletions: Int = 0, val error: String? = "",
    val new_file: Boolean = false, val message_id: Int? = null, val conversation_id: Int? = null,
    /** LOW | MEDIUM | HIGH — HIGH tidak pernah diterapkan otomatis & butuh konfirmasi. */
    val risk: String = "MEDIUM", val risk_reasons: List<String> = emptyList(), val task_id: String? = null,
)
@Serializable data class AIProposalList(val proposals: List<AIProposalItem> = emptyList())
@Serializable data class AIDecisionIn(val project_id: String, val approve: Boolean = true,
                                      val confirm_high_risk: Boolean = false)
@Serializable data class AIDecisionResult(val id: Int, val status: String, val proposal: AIProposalItem? = null)
@Serializable data class AIReply(val content: String = "", val reasoning: String = "", val model: String? = null)

// ---------- AI Coding Agent ----------
@Serializable data class AgentPlanStep(
    val id: String = "", val description: String = "", val files: List<String> = emptyList(),
    val risk: String = "MEDIUM", val verification: String = "", val status: String = "pending",
)
@Serializable data class AgentRun(
    val kind: String = "", val target: String = "", val status: String = "", val exit_code: Int? = null,
    val process_id: String? = null,
)
@Serializable data class AgentVerified(
    val files_changed: List<String> = emptyList(), val files_pending: List<String> = emptyList(),
    val runs: List<AgentRun> = emptyList(), val tests_passed: Int = 0, val tests_failed: Int = 0, val steps_used: Int = 0,
)
@Serializable data class AgentAiText(val summary: String? = null, val limitations: String? = null, val remaining: String? = null)
@Serializable data class AgentReport(
    val verified: AgentVerified = AgentVerified(), val ai_generated: AgentAiText = AgentAiText(),
    val incomplete: String? = null,
)
/** status: PENDING|PLANNING|INSPECTING|EXECUTING|WAITING_APPROVAL|BUILDING|TESTING|REVIEWING|FIXING|COMPLETED|FAILED|CANCELLED|PAUSED */
@Serializable data class AgentTask(
    val id: String, val project_id: String = "", val title: String = "", val description: String = "",
    val status: String = "PENDING", val stage: String = "", val progress: Double = 0.0, val current_op: String = "",
    val model: String? = null, val error: String = "", val max_steps: Int = 0, val steps_used: Int = 0,
    val created_at: Double = 0.0, val started_at: Double? = null, val updated_at: Double = 0.0,
    val finished_at: Double? = null, val duration: Double? = null, val auto_apply: Boolean = false,
    val pending_proposals: Int = 0, val plan: List<AgentPlanStep> = emptyList(), val report: AgentReport? = null,
    /** Proses model yang sedang berjalan (tahap, token, teks langsung); null bila model tidak sedang bekerja. */
    val live: BenchLive? = null,
)
@Serializable data class AgentTaskList(val tasks: List<AgentTask> = emptyList())
@Serializable data class AgentTaskCreate(
    val project_id: String, val description: String, val title: String? = null,
    val auto_apply: Boolean = false,
    /** null = pakai "Batas langkah per task" di Model AI → AI Agent. */
    val max_steps: Int? = null,
)
@Serializable data class AgentEvent(val id: Int, val ts: Double = 0.0, val kind: String = "",
                                    val data: kotlinx.serialization.json.JsonObject = kotlinx.serialization.json.JsonObject(emptyMap()))
@Serializable data class AgentEvents(val events: List<AgentEvent> = emptyList())

// ---------- instal dependensi ----------
@Serializable data class InstallRequest(val project_id: String, val kind: String? = null, val packages: List<String> = emptyList())
@Serializable data class InstallPlanItem(val kind: String = "", val label: String = "", val manifest: String = "",
                                         val note: String = "", val commands: List<String> = emptyList(),
                                         val error: String? = null)
@Serializable data class InstallPlan(val kinds: List<String> = emptyList(), val plans: List<InstallPlanItem> = emptyList(),
                                     val venv: String? = null, val network: Boolean = true)
