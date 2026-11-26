package id.codingserver.android.ui.ai

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.NetworkCheck
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
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
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.AIApply
import id.codingserver.android.data.api.AIConnection
import id.codingserver.android.data.api.AIConnectionIn
import id.codingserver.android.data.api.AIPreset
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ConfirmDialog
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.common.InfoButton
import id.codingserver.android.ui.theme.ErrRed
import id.codingserver.android.ui.theme.OkGreen
import id.codingserver.android.ui.theme.WarnAmber
import kotlinx.coroutines.launch

/** Model & Koneksi: pilih Lokal / Online → koneksi → model → Terapkan; kelola & uji koneksi. */
@Composable
fun AiModelConnections(vm: AppViewModel, hub: AiModelHubState, isAdmin: Boolean, onOpenChat: () -> Unit) {
    val scope = rememberCoroutineScope()
    var editing by remember { mutableStateOf<AIConnection?>(null) }
    var adding by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf<AIConnection?>(null) }
    var applyError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(hub.selConn) { hub.selConn?.let { hub.fetchModels(it) } }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(10.dp),
           verticalArrangement = Arrangement.spacedBy(10.dp)) {
        ActiveModelCard(vm, hub, isAdmin, onOpenChat)
        if (!isAdmin) Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Mode lihat saja", color = WarnAmber, modifier = Modifier.weight(1f))
            InfoButton("Mode lihat saja", "Hanya admin yang bisa mengganti model dan mengelola koneksi. Kamu tetap bisa memakai AI Chat.")
        }
        hub.connError?.let { ErrorCard(it) { scope.launch { hub.loadConnections() } } }

        // ---- koneksi ----
        AiSection("Koneksi", "Server/penyedia tempat model berada.\n\nLokal: model berjalan di Raspberry Pi (llama-server) " +
            "atau PC lain di jaringanmu — gratis & data tidak keluar.\n\nOnline: memakai API penyedia (OpenAI, OpenRouter, " +
            "Groq, DeepSeek, Anthropic, Gemini…) — butuh internet & API key, bisa berbayar.\n\n\"Uji\" mencoba mengambil " +
            "daftar model dari koneksi tersebut.") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(hub.location == "local", { hub.chooseLocation("local") }, label = { Text("Lokal") })
                FilterChip(hub.location == "online", { hub.chooseLocation("online") }, label = { Text("Online (API)") })
            }
            val all = hub.conns
            val list = all.orEmpty().filter { it.location == hub.location }
            when {
                all == null && hub.connError == null -> CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                list.isEmpty() -> Text(if (hub.location == "online") "Belum ada koneksi online." else "Belum ada koneksi lokal.",
                                       style = MaterialTheme.typography.bodySmall)
            }
            list.forEach { cn ->
                ConnectionRow(cn, selected = hub.selConn == cn.id, isAdmin = isAdmin,
                              check = hub.checks[cn.id], checking = hub.checking[cn.id] == true,
                              onSelect = { hub.chooseConnection(cn.id) },
                              onTest = { scope.launch { hub.testConnection(cn) } },
                              onEdit = { editing = cn }, onDelete = { deleting = cn })
            }
            if (isAdmin) OutlinedButton(onClick = { adding = true }) {
                Text("+ Tambah koneksi ${locationLabel(hub.location)}")
            }
        }

        // ---- daftar model & pengelolaan ----
        val cid = hub.selConn
        if (cid != null) AiSection("Daftar model",
            "Pilih model lalu tekan Terapkan.\n\n" +
                (if (hub.location == "local") "Model lokal dimuat ke RAM Pi saat diterapkan; model chat sebelumnya dibongkar " +
                    "(kecuali sedang dipakai agent / Uji Model). Status: termuat = sudah di RAM, belum dimuat = masih di disk."
                 else "Model online langsung aktif (butuh internet & API key).")) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(hub.connections.firstOrNull { it.id == cid }?.name ?: "", style = MaterialTheme.typography.labelMedium,
                     modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                TextButton(onClick = { scope.launch { hub.fetchModels(cid) } }) { Text("Muat ulang") }
            }
            if (hub.loadingModels) CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
            hub.modelsError?.let { Text("Gagal memuat model: $it", color = ErrRed, style = MaterialTheme.typography.bodySmall) }
            val active = hub.status?.let { st -> if (st.connection_id == cid) st.model else null }
            hub.models?.let { ms ->
                if (ms.isEmpty()) Text("Penyedia tidak mengembalikan model.", style = MaterialTheme.typography.bodySmall)
                ms.forEach { m ->
                    Row(Modifier.fillMaxWidth().clickable { hub.selModel = m.id }.padding(vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        RadioButton(selected = hub.selModel == m.id, onClick = { hub.selModel = m.id })
                        Column(Modifier.weight(1f)) {
                            Text(m.id, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                            val extra = listOfNotNull(if (m.id == active) "aktif" else null, m.status?.let { modelStatusLabel(it) },
                                                      m.context_length?.let { "konteks $it" })
                            if (extra.isNotEmpty()) Text(extra.joinToString(" · "), style = MaterialTheme.typography.labelSmall,
                                color = if (m.status == "loaded" || m.id == active) OkGreen else MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
            applyError?.let { Text(it, color = ErrRed, style = MaterialTheme.typography.bodySmall) }
            val busy = hub.status?.status == "loading"
            Button(
                enabled = isAdmin && hub.selModel != null && !busy,
                onClick = {
                    val m = hub.selModel ?: return@Button
                    applyError = null
                    scope.launch {
                        apiCall { hub.c.api.aiApply(AIApply(cid, m)) }
                            .onSuccess { hub.status = it; vm.toast("Menerapkan $m …") }
                            .onFailure { applyError = it.message }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            ) { Text(if (busy) "Sedang memuat…" else if (hub.selModel != null && hub.selModel == active) "Terapkan ulang model" else "Terapkan model") }
        } else Text("Pilih koneksi untuk melihat daftar model.", style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(16.dp))
    }

    if (adding || editing != null) ConnectionDialog(editing, hub.location, hub.presets,
                                                   onDismiss = { adding = false; editing = null }) { body ->
        val e = editing
        scope.launch {
            apiCall { if (e == null) hub.c.api.aiAddConnection(body) else hub.c.api.aiUpdateConnection(e.id, body) }
                .onSuccess { cn ->
                    vm.toast(if (e == null) "Koneksi ${cn.name} ditambahkan" else "Koneksi ${cn.name} diperbarui")
                    hub.loadConnections()
                    hub.chooseLocation(cn.location)
                    hub.chooseConnection(cn.id)
                    hub.fetchModels(cn.id)
                }
                .onFailure { vm.toast(it.message ?: "Gagal menyimpan koneksi") }
        }
    }
    deleting?.let { cn ->
        ConfirmDialog("Hapus koneksi", "Hapus \"${cn.name}\"? Model dari koneksi ini tidak bisa dipakai lagi sampai koneksi ditambahkan ulang.",
                      "Hapus", onConfirm = {
            scope.launch {
                apiCall { hub.c.api.aiDeleteConnection(cn.id) }
                    .onSuccess {
                        if (hub.selConn == cn.id) { hub.selConn = null; hub.selModel = null; hub.models = null }
                        hub.checks.remove(cn.id)
                        hub.loadConnections()
                    }
                    .onFailure { vm.toast(it.message ?: "Gagal menghapus koneksi") }
            }
        }, onDismiss = { deleting = null })
    }
}

@Composable
private fun ConnectionRow(cn: AIConnection, selected: Boolean, isAdmin: Boolean, check: ConnectionCheck?, checking: Boolean,
                          onSelect: () -> Unit, onTest: () -> Unit, onEdit: () -> Unit, onDelete: () -> Unit) {
    Card(
        Modifier.fillMaxWidth().clickable(onClick = onSelect),
        border = if (selected) BorderStroke(2.dp, MaterialTheme.colorScheme.primary) else null,
    ) {
        Column(Modifier.padding(start = 4.dp, end = 4.dp, top = 6.dp, bottom = 6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                RadioButton(selected = selected, onClick = onSelect)
                Column(Modifier.weight(1f)) {
                    Text(cn.name, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text("${kindLabel(cn.kind)} · ${cn.base_url}" +
                             if (cn.location == "online") (if (cn.has_key) " · key ✓" else " · tanpa key") else "",
                         style = MaterialTheme.typography.bodySmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
                if (checking) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                else IconButton(onClick = onTest) { Icon(Icons.Default.NetworkCheck, "Uji koneksi") }
                if (isAdmin) {
                    IconButton(onClick = onEdit) { Icon(Icons.Default.Edit, "Ubah") }
                    IconButton(onClick = onDelete) { Icon(Icons.Default.Delete, "Hapus") }
                }
            }
            check?.let {
                HorizontalDivider(Modifier.padding(horizontal = 8.dp))
                Text((if (it.ok) "✓ " else "✗ ") + it.text, color = if (it.ok) OkGreen else ErrRed,
                     style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(start = 12.dp, top = 4.dp),
                     maxLines = 3, overflow = TextOverflow.Ellipsis)
            }
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
        title = { Text(if (initial == null) "Tambah koneksi ${locationLabel(location)}" else "Ubah koneksi") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (initial == null) {
                    if (choices.isEmpty()) Text("Daftar penyedia belum dimuat dari server. Tutup lalu coba lagi.",
                                                color = ErrRed, style = MaterialTheme.typography.bodySmall)
                    else ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }) {
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
                }
                preset?.note?.takeIf { it.isNotBlank() }?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
                OutlinedTextField(name, { name = it }, label = { Text("Nama") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(url, { url = it }, label = { Text("URL dasar") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                val needsKey = preset?.needs_key == true || initial?.location == "online"
                OutlinedTextField(key, { key = it }, singleLine = true,
                    label = { Text(if (initial?.has_key == true) "API key (kosongkan = tidak diubah)" else if (needsKey) "API key" else "API key (opsional)") },
                    visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Keamanan API key", style = MaterialTheme.typography.labelMedium, modifier = Modifier.weight(1f))
                    InfoButton("Keamanan API key", "API key disimpan terenkripsi di server dan tidak pernah dikirim balik ke HP.")
                }
            }
        },
        confirmButton = {
            TextButton(enabled = name.isNotBlank() && url.startsWith("http") && (initial != null || preset != null), onClick = {
                val p = preset
                val kind = initial?.kind ?: p?.kind ?: return@TextButton
                val loc = initial?.location ?: p?.location ?: return@TextButton
                onSave(AIConnectionIn(name.trim(), kind, loc, url.trim(), key.ifBlank { null }))
                onDismiss()
            }) { Text("Simpan") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } },
    )
}
