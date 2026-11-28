package id.codingserver.android.ui.ai

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import id.codingserver.android.data.api.AIConnection
import id.codingserver.android.data.api.AIModel
import id.codingserver.android.data.api.AIPreset
import id.codingserver.android.data.api.AIStatus
import id.codingserver.android.data.api.AgentModels
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.UnloadAllResult
import id.codingserver.android.data.api.apiCall
import kotlinx.coroutines.delay

/** Bagian di dalam menu Model AI. [key] disimpan di AppViewModel agar bertahan saat berpindah layar. */
enum class AiModelTab(val key: String, val label: String) {
    OVERVIEW("ringkasan", "Ringkasan"),
    MODELS("model", "Model & Koneksi"),
    AGENT("agent", "AI Agent"),
    LAB("lab", "Laboratorium"),
    CONFIG("konfigurasi", "Konfigurasi");

    companion object {
        fun of(key: String?): AiModelTab = entries.firstOrNull { it.key == key } ?: OVERVIEW
    }
}

/** Model lokal yang sedang ada di RAM (dari daftar model koneksi lokal yang melaporkan status). */
data class LoadedModel(val connection: AIConnection, val model: String)

/** Hasil "Uji koneksi": daftar model berhasil diambil (jumlahnya) atau pesan error. */
data class ConnectionCheck(val ok: Boolean, val text: String)

/**
 * State bersama untuk semua bagian Model AI: status model aktif (dipantau berkala), daftar koneksi, preset
 * penyedia, konfigurasi peran agent, dan model lokal yang termuat. Semua data berasal dari API server.
 */
@Stable
class AiModelHubState(val c: ApiClient) {
    var status by mutableStateOf<AIStatus?>(null)
    var statusError by mutableStateOf<String?>(null)
    var conns by mutableStateOf<List<AIConnection>?>(null)
    var presets by mutableStateOf<List<AIPreset>>(emptyList())
    var connError by mutableStateOf<String?>(null)
    var agent by mutableStateOf<AgentModels?>(null)
    var agentError by mutableStateOf<String?>(null)

    /** null = belum dicek; kosong = tidak ada koneksi lokal yang melaporkan status muat. */
    var loaded by mutableStateOf<List<LoadedModel>?>(null)
    var loadedSupported by mutableStateOf(false)
    var loadedChecking by mutableStateOf(false)

    // Pilihan di bagian Model & Koneksi (dipertahankan saat berpindah tab).
    var location by mutableStateOf("local")
    var selConn by mutableStateOf<String?>(null)
    var selModel by mutableStateOf<String?>(null)
    var models by mutableStateOf<List<AIModel>?>(null)
    var modelsError by mutableStateOf<String?>(null)
    var loadingModels by mutableStateOf(false)
    private var selectionInit = false
    val checks = mutableStateMapOf<String, ConnectionCheck>()
    val checking = mutableStateMapOf<String, Boolean>()

    val connections: List<AIConnection> get() = conns.orEmpty()

    suspend fun loadConnections() {
        apiCall { c.api.aiConnections() }
            .onSuccess { conns = it.connections; connError = null; initSelection() }
            .onFailure { connError = it.message }
        apiCall { c.api.aiPresets() }.onSuccess { presets = it.presets }
    }

    suspend fun loadAgent() {
        apiCall { c.api.agentModels() }.onSuccess { agent = it; agentError = null }.onFailure { agentError = it.message }
    }

    /** Pantau status model aktif: cepat selama memuat, santai saat diam. Berhenti otomatis bersama layar. */
    suspend fun pollStatus() {
        while (true) {
            apiCall { c.api.aiStatus() }
                .onSuccess { status = it; statusError = null; initSelection() }
                .onFailure { statusError = it.message }
            delay(if (status?.status == "loading") 1500 else 6000)
        }
    }

    /** Pilihan awal mengikuti model chat tersimpan — dijalankan sekali setelah status & koneksi tersedia. */
    private fun initSelection() {
        if (selectionInit) return
        val st = status ?: return
        val list = conns ?: return
        selectionInit = true
        val cid = st.selected.connection_id ?: return
        list.firstOrNull { it.id == cid }?.let { location = it.location }
        selConn = cid
        selModel = st.selected.model
    }

    fun chooseLocation(loc: String) {
        if (loc == location) return
        location = loc; selConn = null; selModel = null; models = null; modelsError = null
    }

    fun chooseConnection(id: String) {
        if (selConn != id) selModel = null
        selConn = id
    }

    suspend fun fetchModels(cid: String) {
        loadingModels = true; models = null; modelsError = null
        apiCall { c.api.aiModels(cid) }
            .onSuccess { models = it.models; checks[cid] = ConnectionCheck(true, "Terhubung · ${it.models.size} model") }
            .onFailure { modelsError = it.message }
        loadingModels = false
    }

    /** Uji koneksi memakai endpoint daftar model yang sudah ada (tidak ada endpoint baru). */
    suspend fun testConnection(cn: AIConnection) {
        checking[cn.id] = true
        apiCall { c.api.aiModels(cn.id) }
            .onSuccess { checks[cn.id] = ConnectionCheck(true, "Terhubung · ${it.models.size} model tersedia") }
            .onFailure { checks[cn.id] = ConnectionCheck(false, it.message ?: "Tidak bisa terhubung") }
        checking.remove(cn.id)
    }

    var unloadingAll by mutableStateOf(false)

    /** Lepas semua model lokal dari RAM (endpoint /ai/unload-all); model yang sedang dipakai dilewati server. */
    suspend fun unloadAll(force: Boolean = false): Result<UnloadAllResult> {
        unloadingAll = true
        val r = apiCall { c.api.aiUnloadAll(force) }
        apiCall { c.api.aiStatus() }.onSuccess { status = it }
        unloadingAll = false
        refreshLoaded()
        return r
    }

    /** Hitung model lokal yang sedang di RAM dari status model tiap koneksi lokal (data asli llama-server). */
    suspend fun refreshLoaded() {
        if (loadedChecking) return
        loadedChecking = true
        val out = mutableListOf<LoadedModel>()
        var supported = false
        for (cn in connections.filter { it.location == "local" }) {
            apiCall { c.api.aiModels(cn.id) }.onSuccess { list ->
                if (list.models.any { it.status != null }) supported = true
                list.models.filter { it.status == "loaded" || it.status == "loading" }
                    .forEach { out += LoadedModel(cn, it.id + if (it.status == "loading") " (sedang dimuat)" else "") }
            }
        }
        loaded = out
        loadedSupported = supported
        loadedChecking = false
    }
}

@Composable
fun rememberAiModelHubState(c: ApiClient): AiModelHubState {
    val s = remember(c) { AiModelHubState(c) }
    LaunchedEffect(s) { s.loadConnections() }
    LaunchedEffect(s) { s.loadAgent() }
    LaunchedEffect(s) { s.pollStatus() }
    return s
}

fun kindLabel(k: String) = when (k) {
    "llama_router" -> "llama-server"
    "openai" -> "OpenAI-compatible"
    "anthropic" -> "Anthropic"
    "gemini" -> "Gemini"
    else -> k
}

fun modelStatusLabel(s: String) = when (s) {
    "loaded" -> "termuat"
    "loading" -> "sedang dimuat"
    "unloaded" -> "belum dimuat"
    "failed" -> "gagal dimuat"
    else -> s
}

fun locationLabel(loc: String) = if (loc == "local") "lokal" else "online"
