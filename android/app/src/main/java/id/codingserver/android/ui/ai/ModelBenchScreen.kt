package id.codingserver.android.ui.ai

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material3.Icon
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.draw.rotate
import id.codingserver.android.data.api.BenchRecommendation
import id.codingserver.android.ui.common.InfoButton
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.AIConnection
import id.codingserver.android.data.api.AgentModelTarget
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.BenchOverview
import id.codingserver.android.data.api.BenchRun
import id.codingserver.android.data.api.BenchStart
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.common.formatDuration
import id.codingserver.android.ui.common.formatTime
import id.codingserver.android.ui.theme.ErrRed
import id.codingserver.android.ui.theme.Mono
import id.codingserver.android.ui.theme.OkGreen
import id.codingserver.android.ui.theme.WarnAmber
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

internal fun scoreColor(score: Double): Color = when {
    score >= 80 -> OkGreen
    score >= 60 -> Color(0xFF7CB342)
    score >= 40 -> WarnAmber
    else -> ErrRed
}

private fun runLabel(s: String) = when (s) {
    "PENDING" -> "Menunggu giliran"
    "RUNNING" -> "Berjalan"
    "COMPLETED" -> "Selesai"
    "FAILED" -> "Gagal"
    "CANCELLED" -> "Dibatalkan"
    else -> s
}

/** Uji Model: jalankan kasus uji agent yang sama ke beberapa model, bandingkan skor & kecepatan. */
@Composable
fun ModelBenchScreen(vm: AppViewModel, onOpenProfiles: () -> Unit = {}) {
    val client by vm.client.collectAsState()
    val user by vm.user.collectAsState()
    val isAdmin = user?.permissions?.contains("ai_manage") == true
    val c = client ?: return
    var data by remember { mutableStateOf<BenchOverview?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var showStart by remember { mutableStateOf(false) }
    var detail by remember { mutableStateOf<String?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()

    val ctx = androidx.compose.ui.platform.LocalContext.current
    LaunchedEffect(reload) {
        while (true) {
            apiCall { c.api.benchOverview() }.onSuccess { data = it; error = null }.onFailure { error = it.message }
            val running = data?.runs.orEmpty().any { it.status == "PENDING" || it.status == "RUNNING" }
            // Uji berjalan -> pemantau latar belakang aktif: notifikasi saat selesai walau aplikasi diminimalkan.
            if (running) id.codingserver.android.agent.AgentMonitorService.start(ctx)
            if (!running) break
            delay(3000)
        }
    }

    // Status buka/tutup bagian & kartu (bertahan saat layar diputar).
    var lbOpen by rememberSaveable { mutableStateOf(true) }
    var histOpen by rememberSaveable { mutableStateOf(false) }
    var openItems by rememberSaveable { mutableStateOf(setOf<String>()) }
    fun toggle(id: String) { openItems = if (id in openItems) openItems - id else openItems + id }

    fun applyRecommendation(rec: BenchRecommendation) {
        val planner = rec.planner ?: return
        scope.launch {
            val body = buildMap {
                putAll(roleJson("planner", planner.connection_id, planner.model))
                rec.executor?.let { putAll(roleJson("executor", it.connection_id, it.model)) }
                rec.reviewer?.let { putAll(roleJson("reviewer", it.connection_id, it.model)) }
            }
            apiCall { c.api.agentModelsUpdate(JsonObject(body)) }
                .onSuccess { vm.toast("Peran model agent diterapkan") }
                .onFailure { vm.toast(it.message ?: "Gagal") }
        }
    }

    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(enabled = isAdmin, onClick = { showStart = true }) { Text("🧪 Mulai uji") }
                    OutlinedButton(onClick = { reload++ }) { Text("Muat ulang") }
                    InfoButton("Uji Model",
                        "Setiap model diberi ${data?.cases?.size ?: 6} kasus yang meniru kerja AI Agent: format JSON tool, " +
                            "menyusun rencana, memperbaiki bug, menulis fungsi, membaca error, dan jujur soal hasil tes.\n\n" +
                            "Kode buatan model dijalankan di sandbox terhadap tes tersembunyi.\n\n" +
                            "Uji berjalan di latar belakang (aman ditinggal / aplikasi ditutup) dan bergiliran dengan task agent." +
                            if (!isAdmin) "\n\nHanya admin yang bisa menjalankan uji." else "")
                }
                error?.let { ErrorCard(it) { reload++ } }
            }
        }
        val d = data
        if (d == null) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        else {
            // ---- uji yang sedang berjalan: selalu tampil lengkap dengan log langsung ----
            val running = d.runs.filter { it.status == "PENDING" || it.status == "RUNNING" }
            if (running.isNotEmpty()) {
                item { Text("⏳ Sedang berjalan (${running.size})", style = MaterialTheme.typography.titleMedium) }
                items(running, key = { "run" + it.id }) { r -> RunRow(c, r, expanded = true, onToggle = {}) { detail = r.id } }
            }

            // ---- peringkat (dropdown) + rekomendasi ----
            if (d.leaderboard.isNotEmpty()) {
                item { SectionHeader("🏆 Peringkat", d.leaderboard.size, lbOpen) { lbOpen = !lbOpen } }
                if (lbOpen) {
                    val rec = d.recommendation
                    if (rec.planner != null) item { RecommendationRow(rec, isAdmin) { applyRecommendation(rec) } }
                    itemsIndexed(d.leaderboard, key = { _, r -> "lb" + r.id }) { i, r ->
                        LeaderRow(i + 1, r, expanded = "lb" + r.id in openItems, onToggle = { toggle("lb" + r.id) }) { detail = r.id }
                    }
                }
            }

            // ---- riwayat uji (dropdown) ----
            val done = d.runs.filter { it.status != "PENDING" && it.status != "RUNNING" }
            item { SectionHeader("📜 Riwayat uji", done.size, histOpen) { histOpen = !histOpen } }
            if (histOpen) {
                if (done.isEmpty()) item { Text("Belum ada uji selesai. Tekan \"Mulai uji\" lalu pilih model.", style = MaterialTheme.typography.bodySmall) }
                items(done, key = { "h" + it.id }) { r ->
                    RunRow(c, r, expanded = "h" + r.id in openItems, onToggle = { toggle("h" + r.id) }) { detail = r.id }
                }
            }
            item { Spacer(Modifier.height(24.dp)) }
        }
    }

    if (showStart) StartDialog(c, onDismiss = { showStart = false }) { targets, mode ->
        showStart = false
        scope.launch {
            apiCall { c.api.benchStart(BenchStart(targets, mode)) }
                .onSuccess {
                    vm.toast((if (mode == "kalibrasi") "Kalibrasi " else "Uji ") + "${targets.size} model dimulai di latar belakang")
                    reload++
                }
                .onFailure { error = it.message }
        }
    }
    detail?.let { id ->
        RunDetailDialog(c, id, isAdmin, onDismiss = { detail = null }, onChanged = { reload++ },
                        onOpenProfiles = { detail = null; onOpenProfiles() }, onSaved = { vm.toast("Profil disimpan") })
    }
}

@Composable
internal fun ScoreBar(score: Double) {
    val p by animateFloatAsState((score / 100).toFloat().coerceIn(0f, 1f), tween(900), label = "score")
    LinearProgressIndicator(progress = { p }, color = scoreColor(score), trackColor = scoreColor(score).copy(alpha = 0.18f),
                            modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)))
}

@Composable
private fun SectionHeader(title: String, count: Int, open: Boolean, onClick: () -> Unit) {
    val rot by animateFloatAsState(if (open) 180f else 0f, tween(250), label = "chev")
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick),
         colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer)) {
        Row(Modifier.padding(horizontal = 12.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("$title ($count)", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            Icon(Icons.Default.ExpandMore, if (open) "Tutup" else "Buka", Modifier.rotate(rot))
        }
    }
}

@Composable
private fun RecommendationRow(rec: BenchRecommendation, isAdmin: Boolean, onApply: () -> Unit) {
    val p = rec.planner ?: return
    Card(colors = CardDefaults.cardColors(containerColor = OkGreen.copy(alpha = 0.10f))) {
        Row(Modifier.padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("⭐ Rekomendasi", style = MaterialTheme.typography.titleSmall)
                Text("🧠 ${p.model}" + (rec.executor?.let { "  ·  ⚙️ ${it.model}" } ?: ""),
                     style = MaterialTheme.typography.labelSmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
            InfoButton("Rekomendasi peran",
                "Dihitung dari hasil uji model lokal.\n\n🧠 Perencana & 🔍 Peninjau: ${p.model} (skor ${p.score.toInt()}) — skor tertinggi.\n" +
                    (rec.executor?.let { "⚙️ Pelaksana: ${it.model} (skor ${it.score.toInt()}${it.avg_tps?.let { t -> ", $t tok/dtk" } ?: ""}) — " +
                        "tercepat di antara model yang skornya ≥ 60.\n" } ?: "") +
                    "\n\"Terapkan\" mengisi peran di AI Pengaturan → AI Agent. Bisa diubah lagi kapan saja.")
            if (isAdmin) TextButton(onClick = onApply) { Text("Terapkan") }
        }
    }
}

@Composable
private fun ScoreBadge(score: Double) {
    Text("${score.toInt()}", color = scoreColor(score), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
}

@Composable
private fun Chevron(open: Boolean) {
    val rot by animateFloatAsState(if (open) 180f else 0f, tween(250), label = "chev")
    Icon(Icons.Default.ExpandMore, if (open) "Tutup" else "Buka", Modifier.rotate(rot))
}

@Composable
private fun LeaderRow(rank: Int, r: BenchRun, expanded: Boolean, onToggle: () -> Unit, onDetail: () -> Unit) {
    val s = r.summary ?: return
    Card(Modifier.fillMaxWidth().clickable(onClick = onToggle).animateContentSize()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(when (rank) { 1 -> "🥇"; 2 -> "🥈"; 3 -> "🥉"; else -> "#$rank" }, style = MaterialTheme.typography.titleMedium)
                Spacer(Modifier.width(8.dp))
                Text(r.model, Modifier.weight(1f), style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                ScoreBadge(s.score)
                Chevron(expanded)
            }
            if (expanded) {
                Text(r.connection_name + if (r.location == "online") " (online)" else "", style = MaterialTheme.typography.labelSmall)
                ScoreBar(s.score)
                Text(s.verdict, color = scoreColor(s.score), style = MaterialTheme.typography.labelMedium)
                Text("lulus ${s.passed}/${s.total} · format ${s.format_ok}/${s.total} · " +
                         (s.avg_tps?.let { "$it tok/dtk · " } ?: "") + "±${s.avg_seconds.toInt()} dtk/kasus",
                     style = MaterialTheme.typography.labelSmall)
                TextButton(onClick = onDetail) { Text("Lihat detail per kasus") }
            }
        }
    }
}

@Composable
private fun RunRow(c: ApiClient, r: BenchRun, expanded: Boolean, onToggle: () -> Unit, onDetail: () -> Unit) {
    val active = r.status == "PENDING" || r.status == "RUNNING"
    // Jam berdetak tiap detik selama uji berjalan (durasi tidak menunggu polling).
    var now by remember { mutableStateOf(System.currentTimeMillis() / 1000.0) }
    LaunchedEffect(active) { while (active) { now = System.currentTimeMillis() / 1000.0; delay(1000) } }
    Card(Modifier.fillMaxWidth().clickable(onClick = if (active) onDetail else onToggle).animateContentSize()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (active) { CircularProgressIndicator(Modifier.heightIn(max = 18.dp).width(18.dp), strokeWidth = 2.dp); Spacer(Modifier.width(8.dp)) }
                Text((if (r.mode == "kalibrasi") "🎯 " else "") + r.model, Modifier.weight(1f),
                     style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                val col = when (r.status) { "COMPLETED" -> OkGreen; "FAILED" -> ErrRed; "RUNNING" -> WarnAmber; else -> Color.Gray }
                if (!active && r.summary != null) ScoreBadge(r.summary.score)
                else Text(runLabel(r.status), color = col, style = MaterialTheme.typography.labelMedium)
                if (!active) Chevron(expanded)
            }
            if (active) {
                LinearProgressIndicator(progress = { if (r.total_cases > 0) r.done_cases.toFloat() / r.total_cases else 0f },
                                        modifier = Modifier.fillMaxWidth())
                if (r.current.isNotBlank()) Text("${r.current} (${r.done_cases}/${r.total_cases} selesai)",
                                                 style = MaterialTheme.typography.bodySmall)
            }
            if (active || expanded) {
                Text(runLabel(r.status) + " · " + formatTime(r.created_at) + (r.started_at?.let { st ->
                    " · " + formatDuration(((r.finished_at ?: now) - st).toLong().coerceAtLeast(0))
                } ?: ""), style = MaterialTheme.typography.labelSmall)
                r.summary?.let { Text("skor ${it.score.toInt()} · ${it.verdict}", color = scoreColor(it.score), style = MaterialTheme.typography.bodySmall) }
                if (r.error.isNotBlank()) Text(r.error, color = ErrRed, style = MaterialTheme.typography.bodySmall, maxLines = 3)
            }
            // Log langsung: selalu tampil selama uji berjalan, tanda program sedang bekerja.
            if (active) {
                HorizontalDivider(Modifier.padding(vertical = 4.dp))
                BenchLiveLog(c, r.id)
            } else if (expanded) {
                TextButton(onClick = onDetail) { Text("Lihat detail & log") }
            }
        }
    }
}
