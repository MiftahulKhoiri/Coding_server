package id.codingserver.android.ui.ai

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.AIConnection
import id.codingserver.android.data.api.AIModel
import id.codingserver.android.data.api.AgentModels
import id.codingserver.android.data.api.AgentRoleModel
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.common.InfoButton
import id.codingserver.android.ui.theme.OkGreen
import id.codingserver.android.ui.theme.WarnAmber
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

private data class RoleInfo(val key: String, val icon: String, val title: String, val hint: String, val tasks: String)

private val PLANNER = RoleInfo("planner", "🧠", "Perencana (Planner)",
    "Juga target eskalasi pertama bila model lain gagal berulang. Pilih model paling pintar.",
    "Memahami instruksi, membaca konteks proyek, menyusun rencana & langkah kerja, menentukan tool.")
private val EXECUTOR = RoleInfo("executor", "⚙️", "Pelaksana (Executor)",
    "Langkah rutin; bisa model lebih kecil & cepat. Memakai preset ⚡ cepat dari Profil Model.",
    "Membaca & mengedit file, menulis kode, menjalankan tool, build & test, memperbaiki error.")
private val REVIEWER = RoleInfo("reviewer", "🔍", "Peninjau (Reviewer)",
    "Opsional. Bila kosong, task selesai tanpa tahap peninjauan.",
    "Memeriksa hasil & perubahan kode, menilai kualitas, mendeteksi kesalahan sebelum task dinyatakan selesai.")
private val ONLINE = RoleInfo("online", "🌐", "Model eskalasi online",
    "Dipakai hanya bila model lokal (termasuk Perencana) tetap gagal DAN sakelar eskalasi online aktif.", "")

/** JSON untuk PUT /ai/agent-models: role -> {connection_id, model} atau null (kosongkan). */
fun roleJson(key: String, cid: String?, model: String?): JsonObject = JsonObject(
    mapOf(key to if (cid == null || model == null) JsonNull else
        JsonObject(mapOf("connection_id" to JsonPrimitive(cid), "model" to JsonPrimitive(model)))),
)

private fun AgentModels.role(key: String): AgentRoleModel? = when (key) {
    "planner" -> planner
    "executor" -> executor
    "reviewer" -> reviewer
    else -> online
}

private fun emptyRoleText(key: String) = when (key) {
    "online" -> "— tidak diatur"
    "reviewer" -> "— tidak dipakai"
    else -> "— memakai model aktif"
}

/** Bagian AI Agent di Model AI: model per peran, eskalasi online, dan pengelolaan RAM. */
@Composable
fun AgentModelsSection(vm: AppViewModel, hub: AiModelHubState, isAdmin: Boolean, onOpenLab: () -> Unit,
                       onOpenAgentTasks: () -> Unit) {
    var picking by remember { mutableStateOf<RoleInfo?>(null) }
    var saving by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(hub.conns) { if (hub.conns != null && hub.loaded == null) hub.refreshLoaded() }

    fun save(body: JsonObject, msg: String = "Pengaturan agent disimpan") {
        if (saving) return
        saving = true
        scope.launch {
            apiCall { hub.c.api.agentModelsUpdate(body) }.onSuccess { hub.agent = it; vm.toast(msg) }
                .onFailure { vm.toast(it.message ?: "Gagal menyimpan") }
            saving = false
        }
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(10.dp),
           verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Pembagian tugas model AI Agent", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            InfoButton("AI Agent multi-model",
                "Atur model berbeda per peran AI Agent. Peran yang kosong memakai model aktif" +
                    (hub.agent?.default?.let { " (${it.model})" } ?: "") + ".\n\n" +
                    "Bila model gagal berulang (format salah, error, atau verifikasi gagal), langkah itu otomatis " +
                    "diambil alih Perencana (eskalasi), lalu model online bila diizinkan.")
        }
        if (!isAdmin) Text("Mode lihat saja — hanya admin yang bisa mengubah pengaturan agent.", color = WarnAmber,
                           style = MaterialTheme.typography.bodySmall)
        hub.agentError?.let { ErrorCard(it) { scope.launch { hub.loadAgent() } } }

        val a = hub.agent
        if (a == null) {
            if (hub.agentError == null) CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
        } else {
            // ---- peran ----
            AiSection("Peran model") {
                listOf(PLANNER, EXECUTOR, REVIEWER).forEachIndexed { i, r ->
                    if (i > 0) HorizontalDivider()
                    RoleRow(r, a.role(r.key), isAdmin) { picking = r }
                }
            }

            // ---- eskalasi online ----
            AiSection("🌐 Eskalasi online", "Mati (bawaan): 100% lokal, model online tidak pernah dipakai.\n\nNyala: bila model " +
                "lokal (termasuk Perencana) tetap gagal, langkah itu dikirim ke model eskalasi online. Isi kode proyek ikut " +
                "terkirim ke penyedia online dan bisa berbayar.") {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Izinkan eskalasi ke API online", style = MaterialTheme.typography.bodyMedium)
                        Text(if (a.allow_online) "Diizinkan — dipakai hanya setelah model lokal gagal" else "Mati — 100% lokal",
                             style = MaterialTheme.typography.labelSmall, color = if (a.allow_online) WarnAmber else OkGreen)
                    }
                    Switch(checked = a.allow_online, enabled = isAdmin && !saving,
                           onCheckedChange = { save(JsonObject(mapOf("allow_online" to JsonPrimitive(it)))) })
                }
                if (a.allow_online && a.online == null) Text("⚠ Model online belum diatur — eskalasi online tidak akan terjadi.",
                                                             color = WarnAmber, style = MaterialTheme.typography.labelSmall)
                HorizontalDivider()
                RoleRow(ONLINE, a.online, isAdmin) { picking = ONLINE }
                HorizontalDivider()
                Stepper("Eskalasi setelah verifikasi gagal", "kali berturut-turut", a.escalate_after_failures, 1..10,
                        isAdmin && !saving,
                        info = "Berapa kali build/test boleh gagal berturut-turut sebelum langkah perbaikan diambil alih " +
                            "model yang lebih kuat (Perencana). Kecil = cepat minta bantuan, besar = Pelaksana dicoba lebih lama.") {
                    save(JsonObject(mapOf("escalate_after_failures" to JsonPrimitive(it))))
                }
            }

            // ---- RAM ----
            AiSection("🧠 Pengelolaan RAM", "Batas model lokal yang boleh ada di RAM sekaligus (termasuk model chat). Bila " +
                "penuh, model yang paling lama tidak dipakai dibongkar dulu. Pi 16 GB: 2 cukup untuk model 9B + 4B. Model yang " +
                "sedang dipakai agent / Uji Model tidak pernah dibongkar.") {
                Stepper("Model lokal termuat bersamaan", "model (RAM Pi)", a.max_loaded_models, 1..4, isAdmin && !saving,
                        info = "Makin besar makin jarang bongkar-muat (lebih cepat), tapi butuh RAM lebih banyak. " +
                            "Bila RAM tidak cukup, llama-server gagal memuat model.") {
                    save(JsonObject(mapOf("max_loaded_models" to JsonPrimitive(it))))
                }
                Text("Efek: dengan batas ${a.max_loaded_models}, Perencana & Pelaksana " +
                         (if (a.max_loaded_models >= 2) "bisa tetap di RAM bersamaan." else "bergantian dimuat (lebih lambat, hemat RAM)."),
                     style = MaterialTheme.typography.bodySmall)
                hub.status?.settings?.let {
                    Text("Bongkar otomatis model chat bila idle: " +
                             (if (it.idle_unload_minutes > 0) "${it.idle_unload_minutes} menit" else "tidak pernah") +
                             " (atur di Konfigurasi → Parameter Chat)", style = MaterialTheme.typography.labelSmall)
                }
                val loaded = hub.loaded
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(when {
                        loaded == null -> "Memeriksa model di RAM…"
                        !hub.loadedSupported -> "Status RAM tidak dilaporkan koneksi lokal."
                        loaded.isEmpty() -> "Tidak ada model lokal di RAM."
                        else -> "Di RAM sekarang (${loaded.size}/${a.max_loaded_models}):"
                    }, style = MaterialTheme.typography.labelMedium, modifier = Modifier.weight(1f))
                    TextButton(enabled = !hub.loadedChecking, onClick = { scope.launch { hub.refreshLoaded() } }) { Text("Periksa") }
                }
                loaded?.forEach { Text("• ${it.model} (${it.connection.name})", style = MaterialTheme.typography.bodySmall) }
            }

            // ---- rekomendasi & task ----
            AiSection("Rekomendasi model", "Laboratorium Model menguji model dengan kasus yang meniru kerja agent, lalu " +
                "merekomendasikan model terbaik untuk tiap peran (dapat diterapkan dengan satu ketukan).") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onOpenLab, modifier = Modifier.weight(1f)) { Text("🧪 Laboratorium") }
                    OutlinedButton(onClick = onOpenAgentTasks, modifier = Modifier.weight(1f)) { Text("🤖 Task agent") }
                }
            }
        }
        Spacer(Modifier.height(16.dp))
    }

    picking?.let { r ->
        ModelPickerDialog(
            title = "${r.icon} ${r.title}", c = hub.c, conns = hub.connections,
            onlyOnline = r.key == "online", current = hub.agent?.role(r.key),
            clearLabel = if (r.key == "online") "Tidak diatur" else if (r.key == "reviewer") "Tanpa peninjau" else "Pakai model aktif",
            onDismiss = { picking = null },
        ) { cid, model -> picking = null; save(roleJson(r.key, cid, model), "Peran ${r.title} disimpan") }
    }
}

@Composable
private fun RoleRow(r: RoleInfo, t: AgentRoleModel?, isAdmin: Boolean, onEdit: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("${r.icon} ${r.title}", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f, fill = false))
                InfoButton(r.title, (if (r.tasks.isNotBlank()) "Tugas: ${r.tasks}\n\n" else "") + r.hint)
            }
            if (r.tasks.isNotBlank()) Text(r.tasks, style = MaterialTheme.typography.labelSmall,
                                           color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2,
                                           overflow = TextOverflow.Ellipsis)
            Text(
                if (t != null) "${t.model} · ${t.connection_name}${if (t.location == "online") " (online)" else ""}"
                else emptyRoleText(r.key),
                color = if (t != null) OkGreen else MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall, fontWeight = if (t != null) FontWeight.Bold else null,
                maxLines = 2, overflow = TextOverflow.Ellipsis,
            )
        }
        if (isAdmin) TextButton(onClick = onEdit) { Text("Ubah") }
    }
}

@Composable
private fun Stepper(label: String, unit: String, value: Int, range: IntRange, enabled: Boolean, info: String,
                    onChange: (Int) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f, fill = false))
                InfoButton(label, info)
            }
            Text("$value $unit", style = MaterialTheme.typography.labelSmall)
        }
        TextButton(enabled = enabled && value > range.first, onClick = { onChange(value - 1) }) { Text("−") }
        Text("$value", style = MaterialTheme.typography.titleMedium)
        TextButton(enabled = enabled && value < range.last, onClick = { onChange(value + 1) }) { Text("+") }
    }
}

/** Pilih koneksi lalu model; onPick(null, null) = kosongkan. */
@Composable
fun ModelPickerDialog(
    title: String, c: ApiClient, conns: List<AIConnection>, onlyOnline: Boolean, current: AgentRoleModel?,
    clearLabel: String, onDismiss: () -> Unit, onPick: (String?, String?) -> Unit,
) {
    var location by remember { mutableStateOf(current?.location ?: if (onlyOnline) "online" else "local") }
    var selConn by remember { mutableStateOf(current?.connection_id) }
    var models by remember { mutableStateOf<List<AIModel>?>(null) }
    var selModel by remember { mutableStateOf(current?.model) }
    var loading by remember { mutableStateOf(false) }
    var err by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(selConn) {
        val id = selConn ?: return@LaunchedEffect
        loading = true; models = null; err = null
        apiCall { c.api.aiModels(id) }.onSuccess { models = it.models }.onFailure { err = it.message }
        loading = false
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(location == "local", { location = "local"; selConn = null; models = null }, label = { Text("Lokal") })
                    FilterChip(location == "online", { location = "online"; selConn = null; models = null }, label = { Text("Online") })
                }
                val list = conns.filter { it.location == location }
                if (list.isEmpty()) Text("Belum ada koneksi ${locationLabel(location)}. Tambahkan di Model AI → Model & Koneksi.",
                                         style = MaterialTheme.typography.bodySmall)
                list.forEach { cn ->
                    Row(Modifier.fillMaxWidth().clickable { selConn = cn.id; selModel = null }, verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(selConn == cn.id, { selConn = cn.id; selModel = null })
                        Text(cn.name, style = MaterialTheme.typography.bodyMedium)
                    }
                }
                if (selConn != null) {
                    HorizontalDivider()
                    if (loading) CircularProgressIndicator(Modifier.heightIn(max = 24.dp))
                    err?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                    models?.let { ms -> if (ms.isEmpty()) Text("Penyedia tidak mengembalikan model.", style = MaterialTheme.typography.bodySmall) }
                    models?.forEach { m ->
                        Row(Modifier.fillMaxWidth().clickable { selModel = m.id }, verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selModel == m.id, { selModel = m.id })
                            Text(m.id, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(enabled = selConn != null && selModel != null, onClick = { onPick(selConn, selModel) }) { Text("Simpan") }
        },
        dismissButton = {
            Row {
                TextButton(onClick = { onPick(null, null) }) { Text(clearLabel) }
                TextButton(onClick = onDismiss) { Text("Batal") }
            }
        },
    )
}
