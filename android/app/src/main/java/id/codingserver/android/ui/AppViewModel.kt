package id.codingserver.android.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import id.codingserver.android.CodingServerApp
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.ApiException
import id.codingserver.android.data.api.FileEntry
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
        viewModelScope.launch {
            val active = serverStore.current()
            if (active != null) activate(active, restoreProject = true) else _auth.value = AuthState.NO_SERVER
        }
    }

    fun toast(msg: String) { _messages.tryEmit(msg) }

    // ---------- server & auth ----------
    suspend fun activate(server: ServerProfile, restoreProject: Boolean = false) {
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
        if (restoreProject) {
            serverStore.lastProject.first()?.let { pid -> apiCall { c.api.project(pid) }.onSuccess { p -> _project.value = p } }
        }
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
            res.user
        }
    }

    fun logout() {
        val c = _client.value ?: return
        viewModelScope.launch {
            c.logout()
            _user.value = null
            _tabs.value = emptyList()
            _auth.value = AuthState.LOGGED_OUT
        }
    }

    fun disconnect() {
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
}
