package id.codingserver.android.ui.ai

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.AIApply
import id.codingserver.android.data.api.AIConnection
import id.codingserver.android.data.api.AIConnectionIn
import id.codingserver.android.data.api.AIModel
import id.codingserver.android.data.api.AIPreset
import id.codingserver.android.data.api.AISettings
import id.codingserver.android.data.api.AIStatus
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ConfirmDialog
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.theme.ErrRed
import id.codingserver.android.ui.theme.OkGreen
import id.codingserver.android.ui.theme.WarnAmber
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Pengaturan Model AI: pilih Lokal / Online -> koneksi -> model -> Terapkan (seperti ai_asisten). */
@Composable
fun AiModelScreen(vm: AppViewModel, onOpenChat: () -> Unit) {
    val client by vm.client.collectAsState()
    val user by vm.user.collectAsState()
    val isAdmin = user?.permissions?.contains("admin") == true
    var status by remember { mutableStateOf<AIStatus?>(null) }
    var location by remember { mutableStateOf("local") }
    var conns by remember { mutableStateOf<List<AIConnection>>(emptyList()) }
    var presets by remember { mutableStateOf<List<AIPreset>>(emptyList()) }
    var selConn by remember { mutableStateOf<String?>(null) }
    var models by remember { mutableStateOf<List<AIModel>?>(null) }
    var selModel by remember { mutableStateOf<String?>(null) }
    var loadingModels by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var editing by remember { mutableStateOf<AIConnection?>(null) }
    var adding by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf<AIConnection?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()
    val c = client ?: return

    LaunchedEffect(reload) {
        apiCall { c.api.aiConnections() }.onSuccess { conns = it.connections }.onFailure { error = it.message }
        apiCall { c.api.aiPresets() }.onSuccess { presets = it.presets }
    }
    LaunchedEffect(Unit) {
        var first = true
        while (true) {
            apiCall { c.api.aiStatus() }.onSuccess { st ->
                status = st
                if (first) {
                    first = false
                    val cid = st.selected.connection_id
                    conns.firstOrNull { it.id == cid }?.let { location = it.location }
                    if (cid != null) { selConn = cid; selModel = st.selected.model }
                }
            }
            delay(if (status?.status == "loading") 1500 else 6000)
        }
    }

    fun fetchModels(cid: String) {
        loadingModels = true; models = null; error = null
        scope.launch {
            apiCall { c.api.aiModels(cid) }.onSuccess { models = it.models }.onFailure { error = it.message }
            loadingModels = false
        }
    }
    LaunchedEffect(selConn) { selConn?.let { fetchModels(it) } }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        // ---- status ----
        status?.let { st ->
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp)) {
                    Text("Model aktif", style = MaterialTheme.typography.titleMedium)
                    val (txt, col) = when (st.status) {
                        "ready" -> "SIAP: ${st.model}" to OkGreen
                        "loading" -> "MEMUAT: ${st.target ?: ""}" to WarnAmber
                        "error" -> "GAGAL" to ErrRed
                        else -> "Tidak ada model dimuat" to MaterialTheme.colorScheme.onSurfaceVariant
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        if (st.status == "loading") CircularProgressIndicator(Modifier.padding(end = 8.dp).heightIn(max = 18.dp))
                        Text(txt, color = col, style = MaterialTheme.typography.titleSmall)
                    }
                    st.connection?.let { Text("${it.name} (${if (it.location == "local") "lokal" else "online"})", style = MaterialTheme.typography.bodySmall) }
                    if (st.message.isNotBlank()) Text(st.message, style = MaterialTheme.typography.bodySmall)
                    if (st.status == "ready" && st.loaded_by_us)
                        Text("Dibongkar otomatis bila idle ${st.settings.idle_unload_minutes} menit", style = MaterialTheme.typography.labelSmall)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (st.status == "ready") Button(onClick = onOpenChat) { Text("Buka AI Chat") }
                        if (isAdmin && st.status in setOf("ready", "error")) OutlinedButton(onClick = {
                            scope.launch { apiCall { c.api.aiUnload() }.onSuccess { status = it } }
                        }) { Text("Bongkar model") }
                    }
                }
            }
        }
        if (!isAdmin) Text("Hanya admin yang bisa mengganti model. Kamu tetap bisa memakai AI Chat.", color = WarnAmber)
        error?.let { ErrorCard(it) }

        // ---- 1. lokasi ----
        Text("1. Jenis model", style = MaterialTheme.typography.titleSmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(location == "local", { location = "local"; selConn = null; models = null }, label = { Text("Lokal (di Pi / jaringan)") })
            FilterChip(location == "online", { location = "online"; selConn = null; models = null }, label = { Text("Online (API)") })
        }

        // ---- 2. koneksi ----
        Text("2. Koneksi", style = MaterialTheme.typography.titleSmall)
        val list = conns.filter { it.location == location }
        if (list.isEmpty()) Text(if (location == "online") "Belum ada koneksi online. Tambahkan (OpenAI, OpenRouter, Groq, DeepSeek, Anthropic, Gemini…) beserta API key."
                                 else "Belum ada koneksi lokal.", style = MaterialTheme.typography.bodySmall)
        list.forEach { cn ->
            Card(
                Modifier.fillMaxWidth().clickable { selConn = cn.id; selModel = null },
                border = if (selConn == cn.id) BorderStroke(2.dp, MaterialTheme.colorScheme.primary) else null,
                colors = CardDefaults.cardColors(),
            ) {
                Row(Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(selected = selConn == cn.id, onClick = { selConn = cn.id; selModel = null })
                    Column(Modifier.weight(1f)) {
                        Text(cn.name, style = MaterialTheme.typography.titleSmall)
                        Text("${kindLabel(cn.kind)} · ${cn.base_url}" + if (cn.location == "online") (if (cn.has_key) " · key ✓" else " · tanpa key") else "",
                             style = MaterialTheme.typography.bodySmall)
                    }
                    if (isAdmin) {
                        IconButton(onClick = { editing = cn }) { Icon(Icons.Default.Edit, "Ubah") }
                        IconButton(onClick = { deleting = cn }) { Icon(Icons.Default.Delete, "Hapus") }
                    }
                }
            }
        }
        if (isAdmin) OutlinedButton(onClick = { adding = true }) { Text("+ Tambah koneksi ${if (location == "local") "lokal" else "online"}") }

        // ---- 3. model ----
        if (selConn != null) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("3. Pilih model", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                TextButton(onClick = { selConn?.let { fetchModels(it) } }) { Text("Muat ulang daftar") }
            }
            if (loadingModels) CircularProgressIndicator()
            models?.let { ms ->
                if (ms.isEmpty()) Text("Penyedia tidak mengembalikan model.", style = MaterialTheme.typography.bodySmall)
                ms.forEach { m ->
                    Row(Modifier.fillMaxWidth().clickable { selModel = m.id }.padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(selected = selModel == m.id, onClick = { selModel = m.id })
                        Column(Modifier.weight(1f)) {
                            Text(m.id, style = MaterialTheme.typography.bodyMedium)
                            val extra = listOfNotNull(m.status?.let { s -> statusLabel(s) }, m.context_length?.let { "konteks $it" })
                            if (extra.isNotEmpty()) Text(extra.joinToString(" · "), style = MaterialTheme.typography.labelSmall,
                                                         color = if (m.status == "loaded") OkGreen else MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
            val busy = status?.status == "loading"
            Button(
                enabled = isAdmin && selModel != null && !busy,
                onClick = {
                    val cid = selConn ?: return@Button
                    val m = selModel ?: return@Button
                    scope.launch {
                        apiCall { c.api.aiApply(AIApply(cid, m)) }
                            .onSuccess { status = it; vm.toast("Menerapkan $m …") }
                            .onFailure { error = it.message }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            ) { Text(if (busy) "Sedang memuat…" else "Terapkan model") }
            Text(if (location == "local") "Model lokal dimuat ke RAM Pi saat diterapkan; model sebelumnya dibongkar."
                 else "Model online langsung aktif (butuh internet & API key).", style = MaterialTheme.typography.labelSmall)
        }

        // ---- 4. parameter ----
        status?.let { st -> if (isAdmin) ParamsCard(st.settings) { s ->
            scope.launch { apiCall { c.api.aiSettings(s) }.onSuccess { status = it; vm.toast("Pengaturan AI disimpan") }.onFailure { error = it.message } }
        } }
    }

    if (adding || editing != null) ConnectionDialog(editing, location, presets, onDismiss = { adding = false; editing = null }) { body ->
        scope.launch {
            val e = editing
            apiCall { if (e == null) c.api.aiAddConnection(body) else c.api.aiUpdateConnection(e.id, body) }
                .onSuccess { cn -> reload++; selConn = cn.id; location = cn.location; fetchModels(cn.id) }
                .onFailure { error = it.message }
        }
    }
    deleting?.let { cn ->
        ConfirmDialog("Hapus koneksi", "Hapus \"${cn.name}\"?", "Hapus", onConfirm = {
            scope.launch {
                apiCall { c.api.aiDeleteConnection(cn.id) }.onSuccess { if (selConn == cn.id) selConn = null; reload++ }
                    .onFailure { error = it.message }
            }
        }, onDismiss = { deleting = null })
    }
}

fun kindLabel(k: String) = when (k) {
    "llama_router" -> "llama-server"
    "openai" -> "OpenAI-compatible"
    "anthropic" -> "Anthropic"
    "gemini" -> "Gemini"
    else -> k
}

private fun statusLabel(s: String) = when (s) {
    "loaded" -> "termuat"
    "loading" -> "sedang dimuat"
    "unloaded" -> "belum dimuat"
    "failed" -> "gagal dimuat"
    else -> s
}

@Composable
private fun ParamsCard(initial: AISettings, onSave: (AISettings) -> Unit) {
    var prompt by remember(initial) { mutableStateOf(initial.system_prompt) }
    var temp by remember(initial) { mutableStateOf(initial.temperature.toFloat()) }
    var maxTok by remember(initial) { mutableStateOf(initial.max_tokens.toString()) }
    var idle by remember(initial) { mutableStateOf(initial.idle_unload_minutes.toString()) }
    var hist by remember(initial) { mutableStateOf(initial.history_messages.toString()) }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("4. Parameter chat", style = MaterialTheme.typography.titleSmall)
            OutlinedTextField(prompt, { prompt = it }, label = { Text("System prompt") }, modifier = Modifier.fillMaxWidth().heightIn(min = 90.dp))
            Text("Temperature: ${"%.2f".format(temp)}")
            Slider(temp, { temp = it }, valueRange = 0f..1.5f)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedTextField(maxTok, { maxTok = it.filter(Char::isDigit) }, label = { Text("Max token") }, singleLine = true,
                                  keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.weight(1f))
                OutlinedTextField(hist, { hist = it.filter(Char::isDigit) }, label = { Text("Riwayat pesan") }, singleLine = true,
                                  keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.weight(1f))
            }
            OutlinedTextField(idle, { idle = it.filter(Char::isDigit) }, label = { Text("Bongkar otomatis bila idle (menit, 0 = tidak)") },
                              singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth())
            Button(onClick = {
                onSave(AISettings(prompt, temp.toDouble(), maxTok.toIntOrNull()?.coerceIn(16, 65536) ?: 2048,
                                  idle.toIntOrNull() ?: 15, hist.toIntOrNull() ?: 20))
            }) { Text("Simpan parameter") }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ConnectionDialog(initial: AIConnection?, location: String, presets: List<AIPreset>, onDismiss: () -> Unit,
                             onSave: (AIConnectionIn) -> Unit) {
    val choices = presets.filter { it.location == (initial?.location ?: location) }
    var preset by remember { mutableStateOf(choices.firstOrNull { it.kind == initial?.kind } ?: choices.firstOrNull()) }
    var name by remember { mutableStateOf(initial?.name ?: preset?.name ?: "") }
    var url by remember { mutableStateOf(initial?.base_url ?: preset?.base_url ?: "") }
    var key by remember { mutableStateOf("") }
    var expanded by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (initial == null) "Tambah koneksi" else "Ubah koneksi") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (initial == null) ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
                    OutlinedTextField(preset?.name ?: "", {}, readOnly = true, label = { Text("Penyedia") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                        modifier = Modifier.menuAnchor(MenuAnchorType.PrimaryNotEditable).fillMaxWidth())
                    ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
                        choices.forEach { p ->
                            DropdownMenuItem(text = { Text(p.name) }, onClick = {
                                preset = p; name = p.name; url = p.base_url; expanded = false
                            })
                        }
                    }
                }
                preset?.note?.takeIf { it.isNotBlank() }?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                OutlinedTextField(name, { name = it }, label = { Text("Nama") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(url, { url = it }, label = { Text("URL dasar") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                val needsKey = preset?.needs_key == true || initial?.location == "online"
                OutlinedTextField(key, { key = it }, singleLine = true,
                    label = { Text(if (initial?.has_key == true) "API key (kosongkan = tidak diubah)" else if (needsKey) "API key" else "API key (opsional)") },
                    visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
                Text("API key disimpan terenkripsi di server dan tidak pernah dikirim balik ke HP.", style = MaterialTheme.typography.labelSmall)
            }
        },
        confirmButton = {
            TextButton(enabled = url.startsWith("http") && (initial != null || preset != null), onClick = {
                val kind = initial?.kind ?: preset!!.kind
                val loc = initial?.location ?: preset!!.location
                onSave(AIConnectionIn(name.trim(), kind, loc, url.trim(), key.ifBlank { null }))
                onDismiss()
            }) { Text("Simpan") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } },
    )
}
