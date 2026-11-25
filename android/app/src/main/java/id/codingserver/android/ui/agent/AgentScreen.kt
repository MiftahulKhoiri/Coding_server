package id.codingserver.android.ui.agent

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.ContextCompat
import id.codingserver.android.agent.AgentMonitorService
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.AIDecisionIn
import id.codingserver.android.data.api.AIProposalItem
import id.codingserver.android.data.api.AgentEvent
import id.codingserver.android.data.api.AgentTask
import id.codingserver.android.data.api.AgentTaskCreate
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.ai.EditCard
import id.codingserver.android.ui.common.ConfirmDialog
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.common.formatDuration
import id.codingserver.android.ui.common.formatTime
import id.codingserver.android.ui.theme.ErrRed
import id.codingserver.android.ui.theme.Mono
import id.codingserver.android.ui.theme.OkGreen
import id.codingserver.android.ui.theme.WarnAmber
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

private val ACTIVE = setOf("PENDING", "PLANNING", "INSPECTING", "EXECUTING", "BUILDING", "TESTING", "REVIEWING", "FIXING")
private val TERMINAL = setOf("COMPLETED", "FAILED", "CANCELLED")

private fun statusLabel(s: String): Pair<String, Color> = when (s) {
    "PENDING" -> "Antre" to Color.Gray
    "PLANNING" -> "Merencanakan" to WarnAmber
    "INSPECTING" -> "Memeriksa" to WarnAmber
    "EXECUTING" -> "Mengerjakan" to WarnAmber
    "WAITING_APPROVAL" -> "Menunggu persetujuan" to Color(0xFF1E88E5)
    "BUILDING" -> "Build" to WarnAmber
    "TESTING" -> "Menguji" to WarnAmber
    "REVIEWING" -> "Meninjau" to WarnAmber
    "FIXING" -> "Memperbaiki" to WarnAmber
    "COMPLETED" -> "Selesai" to OkGreen
    "FAILED" -> "Gagal" to ErrRed
    "CANCELLED" -> "Dibatalkan" to Color.Gray
    "PAUSED" -> "Dijeda" to Color.Gray
    else -> s to Color.Gray
}

/** Agent Tasks: AI mengerjakan tugas di proyek (rencana → ubah file → uji → laporan) dengan persetujuan pengguna. */
@Composable
fun AgentScreen(vm: AppViewModel, onOpenModels: () -> Unit) {
    val client by vm.client.collectAsState()
    val project by vm.project.collectAsState()
    val target by vm.agentTarget.collectAsState()
    var selected by remember { mutableStateOf<String?>(null) }

    // Izin notifikasi (Android 13+) agar pemantau latar belakang bisa memberi kabar task selesai/butuh persetujuan.
    val ctx = LocalContext.current
    val notifPerm = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }
    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(ctx, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            notifPerm.launch(Manifest.permission.POST_NOTIFICATIONS)
    }
    // Dibuka dari notifikasi → langsung tampilkan detail task tersebut.
    LaunchedEffect(target) {
        target?.let { selected = it; vm.consumeAgentTarget() }
    }

    val c = client
    val p = project
    if (c == null) { Text("Hubungkan ke server dulu untuk memakai AI Agent.", Modifier.padding(16.dp)); return }
    val sel = selected
    // Detail task tetap bisa dibuka (mis. dari notifikasi) walau proyeknya belum/berbeda dibuka.
    if (sel != null) { TaskDetail(vm, c, p?.id ?: "", sel, onBack = { selected = null }); return }
    if (p == null) { Text("Buka proyek dulu untuk memakai AI Agent.", Modifier.padding(16.dp)); return }
    TaskList(vm, c, p.id, p.name, onOpen = { selected = it }, onOpenModels = onOpenModels)
}

@Composable
private fun TaskList(vm: AppViewModel, c: ApiClient, projectId: String, projectName: String,
                     onOpen: (String) -> Unit, onOpenModels: () -> Unit) {
    var tasks by remember { mutableStateOf<List<AgentTask>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var showNew by remember { mutableStateOf(false) }
    var reload by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current

    LaunchedEffect(projectId, reload) {
        while (true) {
            apiCall { c.api.agentTasks(projectId) }.onSuccess { tasks = it.tasks; error = null }
                .onFailure { error = it.message }
            // Ada task aktif → pemantau latar belakang menyala (tetap jalan walau aplikasi ditutup).
            if (tasks.orEmpty().any { it.status in ACTIVE }) AgentMonitorService.start(ctx)
            // Polling hanya selama ada task aktif; selain itu cukup sekali.
            if (tasks.orEmpty().none { it.status in ACTIVE }) break
            delay(3000)
        }
    }

    Scaffold(floatingActionButton = {
        FloatingActionButton(onClick = { showNew = true }) { Icon(Icons.Default.Add, "Task baru") }
    }) { pad ->
        Column(Modifier.padding(pad).fillMaxSize()) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("Proyek: $projectName", Modifier.weight(1f), style = MaterialTheme.typography.labelLarge)
                IconButton(onClick = { reload++ }) { Icon(Icons.Default.Refresh, "Muat ulang") }
            }
            error?.let { ErrorCard(it) { reload++ } }
            val list = tasks
            when {
                list == null && error == null -> LinearProgressIndicator(Modifier.fillMaxWidth().padding(12.dp))
                list.isNullOrEmpty() -> Text(
                    "Belum ada task. Tekan + lalu tulis tugasnya, mis. \"perbaiki error di main.py dan pastikan test lulus\". " +
                        "Agen akan memeriksa proyek, membuat rencana, mengusulkan perubahan (perlu persetujuanmu), " +
                        "menjalankan build/test di sandbox, lalu memberi laporan. Pastikan model sudah diterapkan di menu Model AI.",
                    Modifier.padding(16.dp), style = MaterialTheme.typography.bodyMedium,
                )
                else -> LazyColumn(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(list.orEmpty(), key = { it.id }) { t -> TaskRow(t) { onOpen(t.id) } }
                    item { androidx.compose.foundation.layout.Spacer(Modifier.heightIn(min = 72.dp)) }
                }
            }
        }
    }

    if (showNew) NewTaskDialog(onDismiss = { showNew = false }) { desc, auto ->
        showNew = false
        scope.launch {
            apiCall { c.api.agentCreate(AgentTaskCreate(projectId, desc, auto_apply = auto)) }
                .onSuccess { AgentMonitorService.start(ctx); onOpen(it.id) }
                .onFailure {
                    vm.toast(it.message ?: "Gagal membuat task")
                    if (it.message?.contains("Model AI") == true || it.message?.contains("model", true) == true) onOpenModels()
                }
        }
    }
}

@Composable
private fun TaskRow(t: AgentTask, onClick: () -> Unit) {
    val (label, color) = statusLabel(t.status)
    Card(Modifier.fillMaxWidth().padding(horizontal = 12.dp).clickable(onClick = onClick)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(t.title, Modifier.weight(1f), style = MaterialTheme.typography.titleSmall, maxLines = 2,
                     overflow = TextOverflow.Ellipsis)
                Text(label, color = color, style = MaterialTheme.typography.labelMedium)
            }
            if (t.status in ACTIVE || t.status == "WAITING_APPROVAL")
                LinearProgressIndicator(progress = { t.progress.toFloat().coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth())
            if (t.current_op.isNotBlank()) Text(t.current_op, style = MaterialTheme.typography.bodySmall, maxLines = 2,
                                                overflow = TextOverflow.Ellipsis)
            Text(
                "${formatTime(t.created_at)} · langkah ${t.steps_used}/${t.max_steps}" +
                    (t.duration?.let { " · ${formatDuration(it.toLong())}" } ?: "") +
                    (if (t.pending_proposals > 0) " · ${t.pending_proposals} proposal menunggu" else ""),
                style = MaterialTheme.typography.labelSmall,
            )
        }
    }
}

@Composable
private fun NewTaskDialog(onDismiss: () -> Unit, onCreate: (String, Boolean) -> Unit) {
    var desc by remember { mutableStateOf("") }
    var auto by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Task agen baru") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(desc, { desc = it }, label = { Text("Apa yang harus dikerjakan?") },
                                  modifier = Modifier.fillMaxWidth().heightIn(min = 120.dp), maxLines = 10)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(auto, { auto = it })
                    Text("Terapkan otomatis perubahan berisiko rendah/sedang (risiko TINGGI tetap minta persetujuan)",
                         style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = { TextButton(onClick = { onCreate(desc.trim(), auto) }, enabled = desc.isNotBlank()) { Text("Mulai") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } },
    )
}

@Composable
private fun TaskDetail(vm: AppViewModel, c: ApiClient, projectId: String, taskId: String, onBack: () -> Unit) {
    var task by remember(taskId) { mutableStateOf<AgentTask?>(null) }
    var proposals by remember(taskId) { mutableStateOf<List<AIProposalItem>>(emptyList()) }
    val events = remember(taskId) { mutableStateListOf<AgentEvent>() }
    var error by remember(taskId) { mutableStateOf<String?>(null) }
    var busy by remember(taskId) { mutableStateOf(false) }
    var tab by remember(taskId) { mutableIntStateOf(0) }
    var confirmCancel by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    var tick by remember(taskId) { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current
    // Proyek milik task (task bisa dibuka dari notifikasi saat proyek lain sedang terbuka).
    val pid = task?.project_id?.takeIf { it.isNotBlank() } ?: projectId

    suspend fun refresh() {
        apiCall { c.api.agentTask(taskId) }.onSuccess { task = it; error = null }.onFailure { error = it.message }
        // Mis. setelah proposal disetujui agen lanjut lagi → nyalakan lagi pemantau latar belakang.
        if (task?.status in ACTIVE) AgentMonitorService.start(ctx)
        val after = events.lastOrNull()?.id ?: 0
        apiCall { c.api.agentEvents(taskId, after) }.onSuccess { events.addAll(it.events) }
        apiCall { c.api.agentProposals(taskId) }.onSuccess { proposals = it.proposals }
    }

    LaunchedEffect(taskId, tick) {
        while (true) {
            refresh()
            val st = task?.status ?: break
            if (st in TERMINAL || st == "PAUSED") break
            delay(if (st == "WAITING_APPROVAL") 4000 else 2000)
        }
    }

    fun act(call: suspend () -> Unit) {
        busy = true
        scope.launch {
            runCatching { call() }
            busy = false
            tick++
        }
    }

    fun decide(e: AIProposalItem, approve: Boolean) = act {
        apiCall { c.api.aiDecide(e.id, AIDecisionIn(pid, approve, confirm_high_risk = e.risk == "HIGH")) }
            .onFailure { vm.toast(it.message ?: "Gagal") }
    }

    Column(Modifier.fillMaxSize()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Kembali") }
            Text(task?.title ?: "Task", Modifier.weight(1f), style = MaterialTheme.typography.titleMedium, maxLines = 1,
                 overflow = TextOverflow.Ellipsis)
        }
        error?.let { ErrorCard(it) { tick++ } }
        val t = task ?: run { LinearProgressIndicator(Modifier.fillMaxWidth().padding(12.dp)); return@Column }
        val (label, color) = statusLabel(t.status)
        Column(Modifier.padding(horizontal = 12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(label, color = color, style = MaterialTheme.typography.labelLarge, modifier = Modifier.weight(1f))
                Text("langkah ${t.steps_used}/${t.max_steps}" + (t.model?.let { " · $it" } ?: ""),
                     style = MaterialTheme.typography.labelSmall)
            }
            LinearProgressIndicator(progress = { t.progress.toFloat().coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth())
            if (t.current_op.isNotBlank()) Text(t.current_op, style = MaterialTheme.typography.bodySmall, maxLines = 3)
            if (t.error.isNotBlank()) Text(t.error, color = ErrRed, style = MaterialTheme.typography.bodySmall)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (t.status in ACTIVE) {
                    OutlinedButton(enabled = !busy, onClick = { act { apiCall { c.api.agentPause(taskId) }.onFailure { vm.toast(it.message ?: "") } } }) { Text("Jeda") }
                    OutlinedButton(enabled = !busy, onClick = { confirmCancel = true }) { Text("Batalkan") }
                }
                if (t.status == "PAUSED" || (t.status == "WAITING_APPROVAL" && t.pending_proposals == 0))
                    Button(enabled = !busy, onClick = { act { apiCall { c.api.agentResume(taskId) }.onFailure { vm.toast(it.message ?: "") } } }) { Text("Lanjutkan") }
                if (t.status == "WAITING_APPROVAL") OutlinedButton(enabled = !busy, onClick = { confirmCancel = true }) { Text("Batalkan") }
                if (t.status == "FAILED" || t.status == "CANCELLED")
                    Button(enabled = !busy, onClick = { act { apiCall { c.api.agentResume(taskId) }.onFailure { vm.toast(it.message ?: "") } } }) { Text("Ulangi") }
                if (t.status in TERMINAL || t.status == "PAUSED")
                    TextButton(enabled = !busy, onClick = { confirmDelete = true }) { Text("Hapus") }
            }
        }
        HorizontalDivider(Modifier.padding(top = 6.dp))
        val tabs = listOf("Perubahan (${proposals.size})", "Rencana", "Log", "Laporan")
        TabRow(selectedTabIndex = tab) {
            tabs.forEachIndexed { i, s -> Tab(selected = tab == i, onClick = { tab = i }, text = { Text(s, maxLines = 1) }) }
        }
        when (tab) {
            0 -> LazyColumn(Modifier.fillMaxSize().padding(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (t.status == "WAITING_APPROVAL") item {
                    Text("Agen menunggu keputusanmu atas perubahan di bawah sebelum menjalankan/menguji kode. " +
                             "Setelah semua diputuskan, task lanjut otomatis.",
                         style = MaterialTheme.typography.bodySmall, color = Color(0xFF1E88E5))
                }
                if (proposals.isEmpty()) item { Text("Belum ada perubahan file.", style = MaterialTheme.typography.bodyMedium) }
                items(proposals, key = { it.id }) { e ->
                    EditCard(e, busy = busy, onApply = { decide(e, true) }, onReject = { decide(e, false) }, onRevert = {
                        act { apiCall { c.api.aiRevert(e.id, AIDecisionIn(pid)) }.onFailure { vm.toast(it.message ?: "Gagal") } }
                    })
                }
            }
            1 -> LazyColumn(Modifier.fillMaxSize().padding(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                item { Text(t.description, style = MaterialTheme.typography.bodyMedium) }
                if (t.plan.isEmpty()) item { Text("Rencana belum dibuat.", style = MaterialTheme.typography.bodySmall) }
                items(t.plan) { s ->
                    val mark = when (s.status) { "done" -> "✓"; "in_progress" -> "▶"; "failed" -> "✗"; "skipped" -> "–"; else -> "○" }
                    Column {
                        Text("$mark ${s.id}. ${s.description}", style = MaterialTheme.typography.bodyMedium)
                        val extra = listOfNotNull(
                            s.files.takeIf { it.isNotEmpty() }?.joinToString(", "),
                            s.verification.takeIf { it.isNotBlank() }?.let { "cek: $it" },
                            "risiko ${s.risk}",
                        ).joinToString(" · ")
                        Text(extra, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
            2 -> LazyColumn(Modifier.fillMaxSize().padding(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                items(events, key = { it.id }) { ev -> EventRow(ev) }
            }
            else -> ReportView(t)
        }
    }

    if (confirmCancel) ConfirmDialog("Batalkan task?", "Proses yang sedang berjalan dihentikan. Perubahan yang sudah " +
        "diterapkan tetap ada (bisa dibatalkan per file).", "Batalkan task",
        onConfirm = { act { apiCall { c.api.agentCancel(taskId) }.onFailure { vm.toast(it.message ?: "") } } },
        onDismiss = { confirmCancel = false })
    if (confirmDelete) ConfirmDialog("Hapus task?", "Riwayat & log task dihapus. File proyek tidak berubah.", "Hapus",
        onConfirm = { act { apiCall { c.api.agentDelete(taskId) }.onSuccess { onBack() }.onFailure { vm.toast(it.message ?: "") } } },
        onDismiss = { confirmDelete = false })
}

private fun str(ev: AgentEvent, key: String): String =
    (ev.data[key] as? JsonPrimitive)?.contentOrNull.orEmpty()

@Composable
private fun EventRow(ev: AgentEvent) {
    val time = formatTime(ev.ts)
    when (ev.kind) {
        "thought" -> Text("💭 ${str(ev, "text")}", style = MaterialTheme.typography.bodySmall)
        "tool_call" -> Text("🔧 ${str(ev, "tool")} ${ev.data["args"] ?: ""}", style = Mono, maxLines = 4,
                            overflow = TextOverflow.Ellipsis)
        "observation" -> {
            var open by remember(ev.id) { mutableStateOf(false) }
            val ok = (ev.data["ok"] as? JsonPrimitive)?.contentOrNull != "false"
            Column(Modifier.fillMaxWidth().clickable { open = !open }) {
                Text((if (ok) "↳ " else "⚠ ") + str(ev, "tool") + if (open) "" else "  (ketuk untuk detail)",
                     color = if (ok) Color.Unspecified else ErrRed, style = MaterialTheme.typography.labelSmall)
                if (open) SelectionContainer { Text(str(ev, "text"), style = Mono) }
            }
        }
        "status" -> Text("[$time] ${statusLabel(str(ev, "status")).first}: ${str(ev, "message")}",
                         style = MaterialTheme.typography.labelSmall, color = Color.Gray)
        "error" -> Text("⚠ ${str(ev, "message")}", color = ErrRed, style = MaterialTheme.typography.bodySmall)
        "approval" -> Text("⏸ Menunggu persetujuan", color = Color(0xFF1E88E5), style = MaterialTheme.typography.bodySmall)
        "plan" -> Text("🗺 Rencana diperbarui", style = MaterialTheme.typography.labelSmall)
        "report" -> Text("📄 Laporan dibuat", style = MaterialTheme.typography.labelSmall)
        else -> Text("${ev.kind}: ${ev.data}", style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun ReportView(t: AgentTask) {
    val r = t.report
    LazyColumn(Modifier.fillMaxSize().padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (r == null) { item { Text("Laporan tersedia setelah task selesai.") }; return@LazyColumn }
        r.incomplete?.let { item { Text("Belum tuntas: $it", color = ErrRed) } }
        item { Text("Fakta terverifikasi server", style = MaterialTheme.typography.titleSmall) }
        item {
            Text("File diubah: ${r.verified.files_changed.joinToString(", ").ifBlank { "-" }}\n" +
                 "Menunggu persetujuan: ${r.verified.files_pending.joinToString(", ").ifBlank { "-" }}\n" +
                 "Tes lulus: ${r.verified.tests_passed} · tes gagal: ${r.verified.tests_failed} · langkah: ${r.verified.steps_used}",
                 style = MaterialTheme.typography.bodySmall)
        }
        items(r.verified.runs) { run ->
            val ok = run.status == "COMPLETED" && run.exit_code == 0
            Text("${if (ok) "✓" else "✗"} ${run.kind} ${run.target}: ${run.status} (exit ${run.exit_code ?: "-"})",
                 color = if (ok) OkGreen else ErrRed, style = MaterialTheme.typography.bodySmall)
        }
        item { HorizontalDivider() }
        item { Text("Ringkasan dari AI (belum tentu akurat)", style = MaterialTheme.typography.titleSmall) }
        item { SelectionContainer { Text(r.ai_generated.summary ?: "-", style = MaterialTheme.typography.bodyMedium) } }
        r.ai_generated.limitations?.takeIf { it.isNotBlank() }?.let { item { Text("Keterbatasan: $it", style = MaterialTheme.typography.bodySmall) } }
        r.ai_generated.remaining?.takeIf { it.isNotBlank() }?.let { item { Text("Sisa pekerjaan: $it", style = MaterialTheme.typography.bodySmall) } }
    }
}
