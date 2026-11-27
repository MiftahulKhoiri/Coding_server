package id.codingserver.android.ui.ai

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoFixHigh
import androidx.compose.material.icons.filled.Dns
import androidx.compose.material.icons.filled.Psychology
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Science
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import id.codingserver.android.agent.AgentMonitorService
import id.codingserver.android.data.api.AIStatus
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.theme.ErrRed
import id.codingserver.android.ui.theme.OkGreen
import id.codingserver.android.ui.theme.WarnAmber
import kotlinx.coroutines.launch

/** Teks & warna status model aktif — dipakai Ringkasan dan Model & Koneksi. */
@Composable
fun aiStatusText(st: AIStatus): Pair<String, Color> = when (st.status) {
    "ready" -> "SIAP" to OkGreen
    "loading" -> "MEMUAT" to WarnAmber
    "error" -> "GAGAL" to ErrRed
    else -> "TIDAK ADA MODEL DIMUAT" to MaterialTheme.colorScheme.onSurfaceVariant
}

/** Kartu status model aktif + tombol Buka AI Chat / Bongkar model (admin). */
@Composable
fun ActiveModelCard(vm: AppViewModel, hub: AiModelHubState, isAdmin: Boolean, onOpenChat: () -> Unit) {
    val scope = rememberCoroutineScope()
    var confirmUnload by remember { mutableStateOf(false) }
    val st = hub.status
    AiSection("Model aktif", "Model yang dipakai AI Chat (dan AI Agent bila peran agent kosong).\n\n" +
        "Model lokal dibongkar otomatis dari RAM bila tidak dipakai selama ${st?.settings?.idle_unload_minutes ?: "-"} menit " +
        "(atur di Konfigurasi → Parameter Chat). Model yang sedang dipakai agent / Uji Model tidak bisa dibongkar sampai selesai.") {
        if (st == null) {
            if (hub.statusError != null) Text("Status tidak bisa dimuat: ${hub.statusError}", color = ErrRed,
                                              style = MaterialTheme.typography.bodySmall)
            else CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
            return@AiSection
        }
        val (label, col) = aiStatusText(st)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (st.status == "loading") CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp)
            StatusBadge(label, col)
        }
        val name = when (st.status) {
            "loading" -> st.target
            "ready" -> st.model
            else -> st.selected.model?.let { "$it (dipilih, belum dimuat)" }
        }
        Text(name ?: "Belum ada model dipilih", style = MaterialTheme.typography.titleMedium)
        st.connection?.let { cn ->
            Text("${cn.name} · ${kindLabel(cn.kind)} · ${locationLabel(cn.location)}", style = MaterialTheme.typography.bodySmall)
        }
        if (st.message.isNotBlank()) Text(st.message, style = MaterialTheme.typography.bodySmall,
                                          color = if (st.status == "error") ErrRed else MaterialTheme.colorScheme.onSurfaceVariant)
        if (hub.statusError != null) Text("Gagal memperbarui status: ${hub.statusError}", color = WarnAmber,
                                          style = MaterialTheme.typography.labelSmall)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (st.status == "ready") FilledTonalButton(onClick = onOpenChat) { Text("Buka AI Chat") }
            if (isAdmin && st.status in setOf("ready", "error")) OutlinedButton(onClick = { confirmUnload = true }) {
                Text("Bongkar model")
            }
        }
    }
    if (confirmUnload) id.codingserver.android.ui.common.ConfirmDialog(
        "Bongkar model?", "Model chat dilepas dari RAM. AI Chat memuatnya lagi saat kamu menerapkan model.", "Bongkar",
        onConfirm = {
            scope.launch {
                apiCall { hub.c.api.aiUnload() }.onSuccess { hub.status = it; vm.toast("Model dibongkar") }
                    .onFailure { vm.toast(it.message ?: "Gagal membongkar model") }
            }
        }, onDismiss = { confirmUnload = false })
}

/** Ringkasan AI: status penting dalam satu tampilan + akses cepat ke bagian lain. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AiModelOverview(vm: AppViewModel, hub: AiModelHubState, isAdmin: Boolean, onOpenChat: () -> Unit,
                    onOpen: (AiModelTab) -> Unit, onOpenAgentTasks: () -> Unit) {
    val scope = rememberCoroutineScope()
    var activeTasks by remember { mutableStateOf<Int?>(null) }
    var runningBench by remember { mutableStateOf<Int?>(null) }
    var workError by remember { mutableStateOf<String?>(null) }
    var refresh by remember { mutableIntStateOf(0) }

    LaunchedEffect(hub.conns, refresh) { if (hub.conns != null) hub.refreshLoaded() }
    LaunchedEffect(refresh) {
        workError = null
        apiCall { hub.c.api.agentTasks() }
            .onSuccess { l -> activeTasks = l.tasks.count { it.status in AgentMonitorService.ACTIVE } }
            .onFailure { workError = it.message }
        apiCall { hub.c.api.benchOverview() }
            .onSuccess { b -> runningBench = b.runs.count { it.status == "PENDING" || it.status == "RUNNING" } }
            .onFailure { workError = workError ?: it.message }
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(10.dp),
           verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("Ringkasan AI", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            IconButton(onClick = {
                refresh++
                scope.launch { hub.loadConnections(); hub.loadAgent() }
            }) { Icon(Icons.Default.Refresh, "Muat ulang") }
        }
        hub.connError?.let { ErrorCard(it) { scope.launch { hub.loadConnections() } } }

        ActiveModelCard(vm, hub, isAdmin, onOpenChat)

        // ---- RAM & koneksi ----
        AiSection("Model & koneksi", "Jumlah koneksi yang terdaftar dan model lokal yang saat ini ada di RAM Pi " +
            "(dibaca dari llama-server). Batas model termuat bersamaan diatur di bagian AI Agent → Pengelolaan RAM.") {
            val list = hub.conns
            if (list == null) Text("Memuat koneksi…", style = MaterialTheme.typography.bodySmall)
            else Text("${list.count { it.location == "local" }} koneksi lokal · ${list.count { it.location == "online" }} koneksi online",
                      style = MaterialTheme.typography.bodyMedium)
            val loaded = hub.loaded
            when {
                hub.loadedChecking && loaded == null -> CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                loaded == null -> {}
                !hub.loadedSupported -> Text("Status RAM tidak dilaporkan oleh koneksi lokal.", style = MaterialTheme.typography.bodySmall)
                else -> {
                    val limit = hub.agent?.max_loaded_models
                    Text("Model lokal di RAM: ${loaded.size}" + (limit?.let { " dari maks. $it" } ?: ""),
                         style = MaterialTheme.typography.bodyMedium,
                         color = if (limit != null && loaded.size >= limit) WarnAmber else MaterialTheme.colorScheme.onSurface)
                    loaded.forEach { Text("• ${it.model} (${it.connection.name})", style = MaterialTheme.typography.bodySmall) }
                }
            }
            if (isAdmin && !loaded.isNullOrEmpty()) UnloadAllButton(vm, hub)
        }

        // ---- AI Agent ----
        AiSection("AI Agent", "Model per peran agent, eskalasi online, dan proses yang sedang berjalan di server.") {
            val a = hub.agent
            if (a == null) {
                if (hub.agentError != null) Text(hub.agentError ?: "", color = ErrRed, style = MaterialTheme.typography.bodySmall)
                else CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
            } else {
                fun role(t: id.codingserver.android.data.api.AgentRoleModel?, empty: String) = t?.model ?: empty
                Text("🧠 Perencana: ${role(a.planner, "model aktif")}", style = MaterialTheme.typography.bodySmall)
                Text("⚙️ Pelaksana: ${role(a.executor, "model aktif")}", style = MaterialTheme.typography.bodySmall)
                Text("🔍 Peninjau: ${role(a.reviewer, "tidak dipakai")}", style = MaterialTheme.typography.bodySmall)
                Text("🔐 Izin ubah file: " + when (a.approval_mode) {
                    "penuh" -> "penuh (jalan terus)"; "otomatis" -> "otomatis (risiko tinggi menunggu)"
                    else -> "manual (menunggu persetujuan)" }, style = MaterialTheme.typography.bodySmall)
                Text(if (a.allow_online) "🌐 Eskalasi online: diizinkan (${a.online?.model ?: "model online belum diatur"})"
                     else "🌐 Eskalasi online: mati (100% lokal)",
                     color = if (a.allow_online) WarnAmber else OkGreen, style = MaterialTheme.typography.bodySmall)
            }
            val work = listOfNotNull(activeTasks?.let { "$it task agent aktif" }, runningBench?.let { "$it uji model berjalan" })
            if (work.isNotEmpty()) Text(work.joinToString(" · "), style = MaterialTheme.typography.labelMedium,
                                        color = if ((activeTasks ?: 0) + (runningBench ?: 0) > 0) WarnAmber
                                                else MaterialTheme.colorScheme.onSurfaceVariant)
            workError?.let { Text("Status proses tidak bisa dimuat: $it", color = ErrRed, style = MaterialTheme.typography.labelSmall) }
        }

        // ---- akses cepat ----
        Text("Akses cepat", style = MaterialTheme.typography.titleSmall)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            QuickButton(Icons.Default.SmartToy, "AI Chat", onOpenChat)
            QuickButton(Icons.Default.Psychology, "Kelola model") { onOpen(AiModelTab.MODELS) }
            QuickButton(Icons.Default.Dns, "Kelola koneksi") { onOpen(AiModelTab.MODELS) }
            QuickButton(Icons.Default.AutoFixHigh, "Peran AI Agent") { onOpen(AiModelTab.AGENT) }
            QuickButton(Icons.Default.Science, "Uji model") { onOpen(AiModelTab.LAB) }
            QuickButton(Icons.Default.Tune, "Profil model") { vm.selectAiConfigSection("profil"); onOpen(AiModelTab.CONFIG) }
            QuickButton(Icons.Default.AutoFixHigh, "Task agent", onOpenAgentTasks)
        }
        Spacer(Modifier.height(16.dp))
    }
}

@Composable
private fun QuickButton(icon: ImageVector, label: String, onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, modifier = Modifier.heightIn(min = 40.dp)) {
        Icon(icon, null, Modifier.size(18.dp))
        Spacer(Modifier.width(6.dp))
        Text(label)
    }
}
