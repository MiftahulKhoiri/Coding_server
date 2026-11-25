package id.codingserver.android.ui.ai

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

private fun scoreColor(score: Double): Color = when {
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
fun ModelBenchScreen(vm: AppViewModel) {
    val client by vm.client.collectAsState()
    val user by vm.user.collectAsState()
    val isAdmin = user?.permissions?.contains("admin") == true
    val c = client ?: return
    var data by remember { mutableStateOf<BenchOverview?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var showStart by remember { mutableStateOf(false) }
    var detail by remember { mutableStateOf<String?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(reload) {
        while (true) {
            apiCall { c.api.benchOverview() }.onSuccess { data = it; error = null }.onFailure { error = it.message }
            val running = data?.runs.orEmpty().any { it.status == "PENDING" || it.status == "RUNNING" }
            if (!running) break
            delay(3000)
        }
    }

    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Setiap model diberi ${data?.cases?.size ?: 6} kasus yang meniru kerja AI Agent: format JSON tool, " +
                         "menyusun rencana, memperbaiki bug, menulis fungsi, membaca error, dan jujur soal hasil tes. " +
                         "Kode buatan model dijalankan di sandbox terhadap tes tersembunyi. Uji berjalan di latar belakang " +
                         "dan bergiliran dengan task agent.", style = MaterialTheme.typography.bodySmall)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(enabled = isAdmin, onClick = { showStart = true }) { Text("🧪 Mulai uji") }
                    OutlinedButton(onClick = { reload++ }) { Text("Muat ulang") }
                }
                if (!isAdmin) Text("Hanya admin yang bisa menjalankan uji.", color = WarnAmber, style = MaterialTheme.typography.labelSmall)
                error?.let { ErrorCard(it) { reload++ } }
            }
        }
        val d = data
        if (d == null) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        else {
            val rec = d.recommendation
            if (rec.planner != null) item {
                Card(colors = CardDefaults.cardColors(containerColor = OkGreen.copy(alpha = 0.10f))) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text("⭐ Rekomendasi peran (model lokal)", style = MaterialTheme.typography.titleSmall)
                        Text("🧠 Perencana & 🔍 Peninjau: ${rec.planner.model} (skor ${rec.planner.score.toInt()})",
                             style = MaterialTheme.typography.bodySmall)
                        rec.executor?.let {
                            Text("⚙️ Pelaksana: ${it.model} (skor ${it.score.toInt()}${it.avg_tps?.let { t -> ", $t tok/dtk" } ?: ""})",
                                 style = MaterialTheme.typography.bodySmall)
                        }
                        if (isAdmin) Button(onClick = {
                            scope.launch {
                                val body = buildMap {
                                    putAll(roleJson("planner", rec.planner.connection_id, rec.planner.model))
                                    rec.executor?.let { putAll(roleJson("executor", it.connection_id, it.model)) }
                                    rec.reviewer?.let { putAll(roleJson("reviewer", it.connection_id, it.model)) }
                                }
                                apiCall { c.api.agentModelsUpdate(JsonObject(body)) }
                                    .onSuccess { vm.toast("Peran model agent diterapkan") }
                                    .onFailure { vm.toast(it.message ?: "Gagal") }
                            }
                        }) { Text("Terapkan rekomendasi") }
                    }
                }
            }
            if (d.leaderboard.isNotEmpty()) {
                item { Text("🏆 Peringkat", style = MaterialTheme.typography.titleMedium) }
                items(d.leaderboard, key = { "lb" + it.id }) { r -> LeaderRow(d.leaderboard.indexOf(r) + 1, r) { detail = r.id } }
            }
            item { Text("Riwayat uji", style = MaterialTheme.typography.titleMedium) }
            if (d.runs.isEmpty()) item { Text("Belum ada uji. Tekan \"Mulai uji\" lalu pilih model.", style = MaterialTheme.typography.bodySmall) }
            items(d.runs, key = { it.id }) { r -> RunRow(r) { detail = r.id } }
            item { Spacer(Modifier.height(24.dp)) }
        }
    }

    if (showStart) StartDialog(c, onDismiss = { showStart = false }) { targets ->
        showStart = false
        scope.launch {
            apiCall { c.api.benchStart(BenchStart(targets)) }
                .onSuccess { vm.toast("Uji ${targets.size} model dimulai di latar belakang"); reload++ }
                .onFailure { error = it.message }
        }
    }
    detail?.let { id -> RunDetailDialog(c, id, isAdmin, onDismiss = { detail = null }, onChanged = { reload++ }) }
}

@Composable
private fun ScoreBar(score: Double) {
    val p by animateFloatAsState((score / 100).toFloat().coerceIn(0f, 1f), tween(900), label = "score")
    LinearProgressIndicator(progress = { p }, color = scoreColor(score), trackColor = scoreColor(score).copy(alpha = 0.18f),
                            modifier = Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(4.dp)))
}

@Composable
private fun LeaderRow(rank: Int, r: BenchRun, onClick: () -> Unit) {
    val s = r.summary ?: return
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(when (rank) { 1 -> "🥇"; 2 -> "🥈"; 3 -> "🥉"; else -> "#$rank" }, style = MaterialTheme.typography.titleMedium)
                Spacer(Modifier.width(8.dp))
                Column(Modifier.weight(1f)) {
                    Text(r.model, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(r.connection_name + if (r.location == "online") " (online)" else "", style = MaterialTheme.typography.labelSmall)
                }
                Text("${s.score.toInt()}", color = scoreColor(s.score), style = MaterialTheme.typography.headlineSmall,
                     fontWeight = FontWeight.Bold)
            }
            ScoreBar(s.score)
            Text(s.verdict, color = scoreColor(s.score), style = MaterialTheme.typography.labelMedium)
            Text("lulus ${s.passed}/${s.total} · format ${s.format_ok}/${s.total} · " +
                     (s.avg_tps?.let { "$it tok/dtk · " } ?: "") + "±${s.avg_seconds.toInt()} dtk/kasus",
                 style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun RunRow(r: BenchRun, onClick: () -> Unit) {
    val active = r.status == "PENDING" || r.status == "RUNNING"
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (active) { CircularProgressIndicator(Modifier.heightIn(max = 18.dp).width(18.dp), strokeWidth = 2.dp); Spacer(Modifier.width(8.dp)) }
                Text(r.model, Modifier.weight(1f), style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                val col = when (r.status) { "COMPLETED" -> OkGreen; "FAILED" -> ErrRed; "RUNNING" -> WarnAmber; else -> Color.Gray }
                Text(runLabel(r.status), color = col, style = MaterialTheme.typography.labelMedium)
            }
            if (active) {
                LinearProgressIndicator(progress = { if (r.total_cases > 0) r.done_cases.toFloat() / r.total_cases else 0f },
                                        modifier = Modifier.fillMaxWidth())
                if (r.current.isNotBlank()) Text(r.current, style = MaterialTheme.typography.bodySmall)
            }
            r.summary?.let { Text("skor ${it.score.toInt()} · ${it.verdict}", color = scoreColor(it.score), style = MaterialTheme.typography.bodySmall) }
            if (r.error.isNotBlank()) Text(r.error, color = ErrRed, style = MaterialTheme.typography.bodySmall, maxLines = 3)
            Text(formatTime(r.created_at) + (r.started_at?.let { st ->
                (r.finished_at ?: (System.currentTimeMillis() / 1000.0)).let { " · ${formatDuration((it - st).toLong())}" }
            } ?: ""), style = MaterialTheme.typography.labelSmall)
        }
    }
}

@Composable
private fun StartDialog(c: ApiClient, onDismiss: () -> Unit, onStart: (List<AgentModelTarget>) -> Unit) {
    var conns by remember { mutableStateOf<List<AIConnection>>(emptyList()) }
    val models = remember { mutableStateListOf<Pair<AIConnection, String>>() }
    val chosen = remember { mutableStateListOf<AgentModelTarget>() }
    var loading by remember { mutableStateOf(true) }
    var showOnline by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        apiCall { c.api.aiConnections() }.onSuccess { conns = it.connections }
        for (cn in conns) apiCall { c.api.aiModels(cn.id) }.onSuccess { list -> list.models.forEach { models.add(cn to it.id) } }
        loading = false
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Pilih model untuk diuji") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("Model lokal diuji satu per satu (dimuat bergantian). Tiap model bisa makan beberapa menit sampai " +
                         "puluhan menit di Pi — aman ditinggal, hasilnya tersimpan.", style = MaterialTheme.typography.labelSmall)
                if (loading) CircularProgressIndicator(Modifier.heightIn(max = 24.dp))
                val visible = models.filter { showOnline || it.first.location == "local" }
                visible.groupBy { it.first }.forEach { (cn, ms) ->
                    Text(cn.name + if (cn.location == "online") " (online)" else "", style = MaterialTheme.typography.titleSmall,
                         modifier = Modifier.padding(top = 6.dp))
                    ms.forEach { (_, m) ->
                        val t = AgentModelTarget(cn.id, m)
                        Row(Modifier.fillMaxWidth().clickable { if (t in chosen) chosen.remove(t) else chosen.add(t) },
                            verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(t in chosen, { if (it) chosen.add(t) else chosen.remove(t) })
                            Text(m, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                if (!loading && models.any { it.first.location == "online" }) TextButton(onClick = { showOnline = !showOnline }) {
                    Text(if (showOnline) "Sembunyikan model online" else "Tampilkan model online (memakai API)")
                }
            }
        },
        confirmButton = { TextButton(enabled = chosen.isNotEmpty(), onClick = { onStart(chosen.toList()) }) { Text("Mulai (${chosen.size})") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } },
    )
}

@Composable
private fun RunDetailDialog(c: ApiClient, id: String, isAdmin: Boolean, onDismiss: () -> Unit, onChanged: () -> Unit) {
    var run by remember(id) { mutableStateOf<BenchRun?>(null) }
    var open by remember(id) { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(id) {
        while (true) {
            apiCall { c.api.benchRun(id) }.onSuccess { run = it }
            if (run?.status !in setOf("PENDING", "RUNNING")) break
            delay(3000)
        }
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(run?.model ?: "Uji model", maxLines = 2, overflow = TextOverflow.Ellipsis) },
        text = {
            val r = run
            if (r == null) CircularProgressIndicator()
            else Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                r.summary?.let { s ->
                    Text("Skor ${s.score.toInt()} — ${s.verdict}", color = scoreColor(s.score), fontWeight = FontWeight.Bold)
                    ScoreBar(s.score)
                    Text("Total ${formatDuration(s.total_seconds.toLong())} · ${s.tokens} token" +
                             (s.avg_tps?.let { " · $it tok/dtk" } ?: ""), style = MaterialTheme.typography.labelSmall)
                }
                if (r.current.isNotBlank()) Text(r.current, style = MaterialTheme.typography.bodySmall)
                if (r.error.isNotBlank()) Text(r.error, color = ErrRed, style = MaterialTheme.typography.bodySmall)
                HorizontalDivider()
                r.results.forEach { cr ->
                    val icon = when { cr.score >= 0.99 -> "✅"; cr.score >= 0.5 -> "🟡"; !cr.format_ok -> "🚫"; else -> "❌" }
                    Column(Modifier.fillMaxWidth().clickable { open = if (open == cr.id) null else cr.id }) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("$icon ${cr.title}", Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
                            Text("${(cr.score * 100).toInt()}", color = scoreColor(cr.score * 100), fontWeight = FontWeight.Bold)
                        }
                        Text(cr.note, style = MaterialTheme.typography.bodySmall)
                        Text(listOfNotNull(cr.tool?.let { "tool: $it" }, "${cr.seconds.toInt()} dtk",
                                           cr.tps?.let { "$it tok/dtk" }, cr.prompt_tokens?.let { "prompt $it tok" })
                                 .joinToString(" · "), style = MaterialTheme.typography.labelSmall)
                        if (open == cr.id && cr.output.isNotBlank()) SelectionContainer { Text(cr.output, style = Mono) }
                    }
                    HorizontalDivider()
                }
                if (r.results.isNotEmpty()) Text("Ketuk kasus untuk melihat jawaban model.", style = MaterialTheme.typography.labelSmall)
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Tutup") } },
        dismissButton = {
            val r = run
            if (isAdmin && r != null) {
                if (r.status == "PENDING" || r.status == "RUNNING") TextButton(onClick = {
                    scope.launch { apiCall { c.api.benchCancel(id) }.onSuccess { run = it; onChanged() } }
                }) { Text("Batalkan") }
                else TextButton(onClick = {
                    scope.launch { apiCall { c.api.benchDelete(id) }.onSuccess { onChanged(); onDismiss() } }
                }) { Text("Hapus") }
            }
        },
    )
}
