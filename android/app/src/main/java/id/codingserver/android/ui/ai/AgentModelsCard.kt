package id.codingserver.android.ui.ai

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
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
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.AIConnection
import id.codingserver.android.data.api.AIModel
import id.codingserver.android.data.api.AgentModels
import id.codingserver.android.data.api.AgentRoleModel
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.theme.OkGreen
import id.codingserver.android.ui.theme.WarnAmber
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

private data class RoleInfo(val key: String, val icon: String, val title: String, val hint: String)

private val ROLES = listOf(
    RoleInfo("planner", "🧠", "Perencana", "Memahami tugas, memeriksa proyek, menyusun rencana. Juga target eskalasi pertama. Pilih model paling pintar."),
    RoleInfo("executor", "⚙️", "Pelaksana", "Langkah rutin: baca/edit file, build & test. Bisa model lebih kecil & cepat."),
    RoleInfo("reviewer", "🔍", "Peninjau", "Opsional: memeriksa hasil sebelum task dinyatakan selesai."),
    RoleInfo("online", "🌐", "Eskalasi online", "Dipakai hanya bila model lokal gagal berulang DAN sakelar online di bawah aktif."),
)

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

/** Kartu "Model Agent": peran model untuk AI Coding Agent + eskalasi + tombol Uji Model. */
@Composable
fun AgentModelsCard(vm: AppViewModel, c: ApiClient, conns: List<AIConnection>, isAdmin: Boolean, onOpenBench: () -> Unit) {
    var cfg by remember { mutableStateOf<AgentModels?>(null) }
    var picking by remember { mutableStateOf<RoleInfo?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) { apiCall { c.api.agentModels() }.onSuccess { cfg = it } }

    fun save(body: JsonObject, msg: String = "Peran model disimpan") {
        scope.launch {
            apiCall { c.api.agentModelsUpdate(body) }.onSuccess { cfg = it; vm.toast(msg) }
                .onFailure { vm.toast(it.message ?: "Gagal menyimpan") }
        }
    }

    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Model Agent (multi-model)", style = MaterialTheme.typography.titleMedium)
            Text("Atur model berbeda per peran AI Agent. Peran yang kosong memakai model aktif" +
                     (cfg?.default?.let { " (${it.model})" } ?: "") + ".",
                 style = MaterialTheme.typography.bodySmall)
            val c0 = cfg
            if (c0 == null) CircularProgressIndicator(Modifier.heightIn(max = 24.dp))
            else {
                ROLES.forEach { r ->
                    val t = c0.role(r.key)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("${r.icon} ${r.title}", style = MaterialTheme.typography.titleSmall)
                            Text(
                                when {
                                    t != null -> "${t.model} · ${t.connection_name}${if (t.location == "online") " (online)" else ""}"
                                    r.key == "online" -> "— tidak diatur"
                                    r.key == "reviewer" -> "— tidak dipakai"
                                    else -> "— model aktif"
                                },
                                color = if (t != null) OkGreen else MaterialTheme.colorScheme.onSurfaceVariant,
                                style = MaterialTheme.typography.bodySmall, fontWeight = if (t != null) FontWeight.Bold else null,
                            )
                            Text(r.hint, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        if (isAdmin) TextButton(onClick = { picking = r }) { Text("Ubah") }
                    }
                    HorizontalDivider()
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Izinkan eskalasi ke API online", style = MaterialTheme.typography.bodyMedium)
                        Text(if (c0.allow_online) "Kode proyek bisa dikirim ke penyedia online saat eskalasi."
                             else "100% lokal: model online tidak pernah dipakai.",
                             style = MaterialTheme.typography.labelSmall, color = if (c0.allow_online) WarnAmber else OkGreen)
                    }
                    Switch(checked = c0.allow_online, enabled = isAdmin,
                           onCheckedChange = { save(JsonObject(mapOf("allow_online" to JsonPrimitive(it)))) })
                }
                Stepper("Eskalasi setelah verifikasi gagal", "kali berturut-turut", c0.escalate_after_failures, 1..10, isAdmin) {
                    save(JsonObject(mapOf("escalate_after_failures" to JsonPrimitive(it))))
                }
                Stepper("Model lokal termuat bersamaan", "model (RAM Pi)", c0.max_loaded_models, 1..4, isAdmin) {
                    save(JsonObject(mapOf("max_loaded_models" to JsonPrimitive(it))))
                }
            }
            OutlinedButton(onClick = onOpenBench, modifier = Modifier.fillMaxWidth()) { Text("🧪 Uji Model — cari model yang pas") }
        }
    }

    picking?.let { r ->
        ModelPickerDialog(
            title = "${r.icon} Model ${r.title}", c = c, conns = conns,
            onlyOnline = false, current = cfg?.role(r.key),
            clearLabel = if (r.key == "online") "Tidak diatur" else if (r.key == "reviewer") "Tanpa peninjau" else "Pakai model aktif",
            onDismiss = { picking = null },
        ) { cid, model -> picking = null; save(roleJson(r.key, cid, model)) }
    }
}

@Composable
private fun Stepper(label: String, unit: String, value: Int, range: IntRange, enabled: Boolean, onChange: (Int) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodyMedium)
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
                if (list.isEmpty()) Text("Belum ada koneksi ${if (location == "local") "lokal" else "online"}. Tambahkan di halaman Model AI.",
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
