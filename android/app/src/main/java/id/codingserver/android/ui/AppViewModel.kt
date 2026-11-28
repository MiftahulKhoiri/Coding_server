package id.codingserver.android.ui

import id.codingserver.android.ui.theme.AppTheme
import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import id.codingserver.android.CodingServerApp
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.ApiException
import id.codingserver.android.data.api.FileEntry
import id.codingserver.android.data.api.InstallRequest
import id.codingserver.android.data.api.Job
import id.codingserver.android.data.api.JobEvent
import id.codingserver.android.data.api.JobStream
import id.codingserver.android.data.api.Project
import id.codingserver.android.data.api.RunRequest
import id.codingserver.android.data.api.UserOut
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.data.settings.EditorPrefs
import id.codingserver.android.data.settings.ServerProfile
import kotlinx.coroutines.Job as CoJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

data class EditorTab(
    val projectId: String,
    val path: String,
    val sha256: String?,
    val dirty: Boolean = false,
    val language: String = "",
) {
    val id: String get() = "$projectId:$path"
    val name: String get() = path.substringAfterLast('/')
}

data class RunState(
    val job: Job,
    val combined: List<Pair<String, String>> = emptyList(),
    val status: String = job.status,
    val phase: String = "",
    val version: Int = 0,
)

enum class AuthState { NO_SERVER, LOGGED_OUT, LOGGED_IN }

/** State bersama seluruh aplikasi: server aktif, sesi login, proyek, tab editor, job berjalan. */
class AppViewModel(application: Application) : AndroidViewModel(application) {
    private val app = application as CodingServerApp
    val serverStore = app.servers

    val servers: StateFlow<List<ServerProfile>> = serverStore.servers.stateIn(viewModelScope, SharingStarted.Eagerly, emptyList())
    val editorPrefs: StateFlow<EditorPrefs> = serverStore.editorPrefs.stateIn(viewModelScope, SharingStarted.Eagerly, EditorPrefs())
    val appTheme: StateFlow<AppTheme> = serverStore.appTheme.stateIn(viewModelScope, SharingStarted.Eagerly, AppTheme())
    val terminalPrefs: StateFlow<id.codingserver.android.data.settings.TerminalPrefs> =
        serverStore.terminalPrefs.stateIn(viewModelScope, SharingStarted.Eagerly, id.codingserver.android.data.settings.TerminalPrefs())
    fun setTerminalPrefs(p: id.codingserver.android.data.settings.TerminalPrefs) { viewModelScope.launch { serverStore.setTerminalPrefs(p) } }

    private val _client = MutableStateFlow<ApiClient?>(null)
    val client: StateFlow<ApiClient?> = _client.asStateFlow()

    private val _auth = MutableStateFlow(AuthState.NO_SERVER)
    val auth: StateFlow<AuthState> = _auth.asStateFlow()

    private val _user = MutableStateFlow<UserOut?>(null)
    val user: StateFlow<UserOut?> = _user.asStateFlow()

    /** null = belum diketahui, true = online, false = offline. */
    private val _online = MutableStateFlow<Boolean?>(null)
    val online: StateFlow<Boolean?> = _online.asStateFlow()

    private val _project = MutableStateFlow<Project?>(null)
    val project: StateFlow<Project?> = _project.asStateFlow()

    private val _tabs = MutableStateFlow<List<EditorTab>>(emptyList())
    val tabs: StateFlow<List<EditorTab>> = _tabs.asStateFlow()
    private val _activeTab = MutableStateFlow<String?>(null)
    val activeTab: StateFlow<String?> = _activeTab.asStateFlow()

    private val _run = MutableStateFlow<RunState?>(null)
    val run: StateFlow<RunState?> = _run.asStateFlow()
    private var stream: JobStream? = null
    private var streamJob: CoJob? = null

    private val _messages = MutableSharedFlow<String>(extraBufferCapacity = 16)
    val messages: SharedFlow<String> = _messages

    private var healthLoop: CoJob? = null

    /** Chat AI (state bertahan saat pindah layar). */
    val aiChat = id.codingserver.android.ui.ai.AiChatController(viewModelScope) { _client.value }

    init {
        // Cek APK terbaru otomatis: saat aplikasi dibuka lalu tiap 6 jam selama berjalan.
        viewModelScope.launch {
            delay(4_000)
            while (isActive) {
                id.codingserver.android.data.update.UpdateChecker.check(getApplication())
                delay(6 * 60 * 60 * 1000L)
            }
        }
        viewModelScope.launch {
            val active = serverStore.current()
            if (active != null) activate(active, restoreProject = true) else _auth.value = AuthState.NO_SERVER
        }
    }

    fun toast(msg: String) { _messages.tryEmit(msg) }

    /** false selama ganti server/login: perubahan tab saat itu (dikosongkan) tidak boleh menimpa tab tersimpan. */
    @Volatile private var tabsReady = false

    init {
        // Simpan daftar tab editor yang terbuka (per server) agar dipulihkan saat aplikasi dibuka lagi.
        viewModelScope.launch {
            kotlinx.coroutines.flow.combine(_tabs, _activeTab) { t, a -> t.map { it.id } to a }
                .distinctUntilChanged()
                .collect { (ids, a) ->
                    val sid = _client.value?.server?.id ?: return@collect
                    if (tabsReady && _auth.value == AuthState.LOGGED_IN) serverStore.setOpenTabs(sid, ids, a)
                }
        }
    }

    // ---------- AI Agent (notifikasi & pemantau latar belakang) ----------
    /** Task agent yang diminta dibuka dari notifikasi; dikonsumsi oleh layar Agent Tasks. */
    private val _agentTarget = MutableStateFlow<String?>(null)
    val agentTarget: StateFlow<String?> = _agentTarget.asStateFlow()

    fun openAgentTask(taskId: String) { _agentTarget.value = taskId }
    fun consumeAgentTarget() { _agentTarget.value = null }

    /** Layar yang diminta dibuka dari notifikasi (mis. "settings" untuk pembaruan, "ai_bench" untuk Uji Model). */
    private val _openRoute = MutableStateFlow<String?>(null)
    val openRoute: StateFlow<String?> = _openRoute.asStateFlow()
    fun requestRoute(route: String) { _openRoute.value = route }
    fun consumeRoute() { _openRoute.value = null }

    // ---------- Model AI (pusat pengelolaan model) ----------
    /** Bagian Model AI yang sedang dibuka (kunci AiModelTab); bertahan saat pindah ke AI Chat lalu kembali. */
    private val _aiModelTab = MutableStateFlow("ringkasan")
    val aiModelTab: StateFlow<String> = _aiModelTab.asStateFlow()
    fun selectAiModelTab(key: String) { _aiModelTab.value = key }

    /** Sub-bagian Konfigurasi AI: "profil" (Profil Model) atau "parameter" (Parameter Chat). */
    private val _aiConfigSection = MutableStateFlow("profil")
    val aiConfigSection: StateFlow<String> = _aiConfigSection.asStateFlow()
    fun selectAiConfigSection(key: String) { _aiConfigSection.value = key }

    /** Nyalakan pemantau latar belakang bila masih ada task agent / Uji Model yang berjalan di server. */
    private fun resumeAgentMonitor(c: ApiClient) {
        viewModelScope.launch {
            if (runningWork(c).isNotEmpty()) id.codingserver.android.agent.AgentMonitorService.start(getApplication())
        }
    }

    /** Daftar proses yang masih berjalan (untuk dialog keluar). Kosong = aman ditutup. */
    suspend fun runningWork(c: ApiClient? = _client.value): List<String> {
        val out = mutableListOf<String>()
        if (c != null) {
            apiCall { c.api.agentTasks() }.onSuccess { list ->
                val active = list.tasks.filter { it.status in id.codingserver.android.agent.AgentMonitorService.ACTIVE }
                if (active.isNotEmpty()) out += "🤖 ${active.size} task AI Agent (${active.first().title.take(40)})"
            }
            apiCall { c.api.benchOverview() }.onSuccess { b ->
                b.runs.filter { it.status == "PENDING" || it.status == "RUNNING" }.forEach {
                    out += "🧪 Uji model ${it.model} (${it.done_cases}/${it.total_cases})"
                }
            }
        }
        _run.value?.let { r -> if (r.status in setOf("QUEUED", "RUNNING", "PENDING", "BUILDING")) out += "▶ Program sedang dijalankan" }
        return out
    }

    // ---------- server & auth ----------
    suspend fun activate(server: ServerProfile, restoreProject: Boolean = false) {
        tabsReady = false
        serverStore.setActive(server.id)
        val c = ApiClient(server, app.tokens) {
            _auth.value = AuthState.LOGGED_OUT
            _user.value = null
            toast("Sesi berakhir, silakan login lagi")
        }
        _client.value = c
        aiChat.newConversation()
        _tabs.value = emptyList()
        _activeTab.value = null
        _project.value = null
        _user.value = null
        startHealthLoop(c)
        if (c.accessToken() == null) {
            _auth.value = AuthState.LOGGED_OUT
            return
        }
        _auth.value = AuthState.LOGGED_IN
        apiCall { c.api.me() }
            .onSuccess { _user.value = it }
            .onFailure {
                val e = it as ApiException
                if (e.status == 401) _auth.value = AuthState.LOGGED_OUT
            }
        if (_auth.value == AuthState.LOGGED_IN) resumeAgentMonitor(c)
        if (restoreProject) {
            serverStore.lastProject.first()?.let { pid -> apiCall { c.api.project(pid) }.onSuccess { p -> _project.value = p } }
        }
        if (_auth.value == AuthState.LOGGED_IN) restoreTabs(server.id)
    }

    /** Pulihkan tab editor terakhir server ini (isi dimuat ulang dari server saat tab dibuka). */
    private suspend fun restoreTabs(serverId: String) {
        val (ids, active) = serverStore.openTabs(serverId)
        val restored = ids.mapNotNull { id ->
            val i = id.indexOf(':')
            if (i <= 0) null else EditorTab(id.substring(0, i), id.substring(i + 1), null)
        }
        if (restored.isNotEmpty() && _tabs.value.isEmpty()) {
            _tabs.value = restored
            _activeTab.value = active?.takeIf { a -> restored.any { it.id == a } } ?: restored.last().id
        }
        tabsReady = true
    }

    private fun startHealthLoop(c: ApiClient) {
        healthLoop?.cancel()
        _online.value = null
        healthLoop = viewModelScope.launch {
            while (isActive) {
                _online.value = apiCall { c.health() }.isSuccess
                delay(if (_online.value == true) 15_000 else 5_000)
            }
        }
    }

    suspend fun login(username: String, password: String): Result<UserOut> {
        val c = _client.value ?: return Result.failure(ApiException("no_server", "Pilih server dulu"))
        return apiCall { c.login(username, password) }.map { res ->
            _user.value = res.user
            _auth.value = AuthState.LOGGED_IN
            _online.value = true
            serverStore.upsert(c.server.copy(username = username))
            resumeAgentMonitor(c)
            restoreTabs(c.server.id)
            res.user
        }
    }

    fun logout() {
        val c = _client.value ?: return
        id.codingserver.android.agent.AgentMonitorService.stop(getApplication())
        viewModelScope.launch {
            tabsReady = false
            c.logout()
            _user.value = null
            _tabs.value = emptyList()
            _auth.value = AuthState.LOGGED_OUT
        }
    }

    fun disconnect() {
        id.codingserver.android.agent.AgentMonitorService.stop(getApplication())
        viewModelScope.launch {
            healthLoop?.cancel()
            serverStore.setActive(null)
            _client.value = null
            _online.value = null
            _auth.value = AuthState.NO_SERVER
        }
    }

    // ---------- proyek ----------
    fun openProject(p: Project) {
        _project.value = p
        viewModelScope.launch { serverStore.setLastProject(p.id) }
    }

    fun closeProject() {
        _project.value = null
        viewModelScope.launch { serverStore.setLastProject(null) }
    }

    // ---------- tab editor ----------
    fun addOrFocusTab(tab: EditorTab) {
        _tabs.update { list -> if (list.any { it.id == tab.id }) list else list + tab }
        _activeTab.value = tab.id
    }

    fun setActiveTab(id: String?) { _activeTab.value = id }

    fun updateTab(id: String, f: (EditorTab) -> EditorTab) {
        _tabs.update { list -> list.map { if (it.id == id) f(it) else it } }
    }

    fun closeTab(id: String) {
        _tabs.update { list -> list.filterNot { it.id == id } }
        if (_activeTab.value == id) _activeTab.value = _tabs.value.lastOrNull()?.id
    }

    fun renameTabs(projectId: String, oldPath: String, newPath: String) {
        _tabs.update { list ->
            list.map { t ->
                if (t.projectId == projectId && (t.path == oldPath || t.path.startsWith("$oldPath/")))
                    t.copy(path = newPath + t.path.removePrefix(oldPath)) else t
            }
        }
    }

    // ---------- eksekusi ----------
    suspend fun execute(entry: FileEntry, build: Boolean, args: List<String> = emptyList(), stdin: String? = null,
                        interactive: Boolean = false, projectId: String? = null): Result<Job> {
        val c = _client.value ?: return Result.failure(ApiException("no_server", "Tidak terhubung"))
        val pid = projectId ?: _project.value?.id ?: return Result.failure(ApiException("no_project", "Buka proyek dulu"))
        val req = RunRequest(project_id = pid, path = entry.path, args = args, stdin = stdin, interactive = interactive)
        return apiCall { if (build) c.api.build(req) else c.api.run(req) }.onSuccess { attach(it) }
    }

    /** Instal dependensi proyek (pip → .venv, npm, go, composer) di server; output tampil di layar Output. */
    suspend fun installDeps(projectId: String? = null, packages: List<String> = emptyList()): Result<Job> {
        val c = _client.value ?: return Result.failure(ApiException("no_server", "Tidak terhubung"))
        val pid = projectId ?: _project.value?.id ?: return Result.failure(ApiException("no_project", "Buka proyek dulu"))
        return apiCall { c.api.install(InstallRequest(project_id = pid, packages = packages)) }.onSuccess { attach(it) }
    }

    /** Perbarui data akun yang sedang login (setelah ubah profil). */
    fun setUser(u: UserOut) { _user.value = u }

    fun attach(job: Job) {
        val c = _client.value ?: return
        streamJob?.cancel()
        _run.value = RunState(job)
        val s = JobStream(c)
        stream = s
        streamJob = viewModelScope.launch {
            c.ensureFreshToken()
            s.events(job.process_id).collect { ev ->
                _run.update { st ->
                    st ?: return@update st
                    when (ev) {
                        is JobEvent.Output -> st.copy(combined = st.combined + (ev.stream to ev.text), version = st.version + 1)
                        is JobEvent.Status -> st.copy(status = ev.status, version = st.version + 1)
                        is JobEvent.Phase -> st.copy(phase = ev.phase, version = st.version + 1)
                        is JobEvent.End -> st.copy(job = ev.job, status = ev.job.status, version = st.version + 1)
                        is JobEvent.Error -> st.copy(combined = st.combined + ("stderr" to "\n[stream: ${ev.message}]\n"),
                                                     version = st.version + 1)
                    }
                }
            }
            // Ambil hasil final lengkap (stdout/stderr tersimpan) setelah stream selesai.
            apiCall { c.api.job(job.process_id) }.onSuccess { full ->
                _run.update { st -> st?.copy(job = full, status = full.status, version = st.version + 1) }
            }
        }
    }

    fun sendStdin(text: String, eof: Boolean = false) { stream?.sendStdin(text, eof) }

    fun stopRun() {
        val c = _client.value ?: return
        val pid = _run.value?.job?.process_id ?: return
        viewModelScope.launch {
            apiCall { c.api.stop(pid) }.onFailure { toast((it as ApiException).message) }
        }
    }

    fun setEditorPrefs(p: EditorPrefs) { viewModelScope.launch { serverStore.setEditorPrefs(p) } }
    fun setAppTheme(t: AppTheme) { viewModelScope.launch { serverStore.setAppTheme(t) } }

    /** Konfigurasi klien LSP untuk editor WebView (dipanggil dari thread WebView). */
    fun lspConfigJson(): String {
        val c = _client.value ?: return ""
        val p = _project.value ?: return ""
        val o = kotlinx.serialization.json.buildJsonObject {
            put("wsBase", kotlinx.serialization.json.JsonPrimitive(c.wsUrl("").substringBefore("?")))
            put("token", kotlinx.serialization.json.JsonPrimitive(c.accessToken() ?: ""))
            put("projectId", kotlinx.serialization.json.JsonPrimitive(p.id))
            put("enabled", kotlinx.serialization.json.JsonPrimitive(editorPrefs.value.lsp))
        }
        return o.toString()
    }
}
