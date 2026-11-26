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

/** Dialog Laboratorium Model: memulai uji/kalibrasi dan melihat detail hasil per kasus. */
@Composable
internal fun StartDialog(c: ApiClient, onDismiss: () -> Unit, onStart: (List<AgentModelTarget>, String) -> Unit) {
    var mode by remember { mutableStateOf("kalibrasi") }
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
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(mode == "kalibrasi", { mode = "kalibrasi" }, label = { Text("🎯 Kalibrasi (3 varian)") })
                    FilterChip(mode == "cepat", { mode = "cepat" }, label = { Text("Uji cepat") })
                    InfoButton("Mode uji", "🎯 Kalibrasi: model diuji dengan 3 varian pengaturan (mis. berpikir ON, " +
                        "berpikir OFF, suhu rendah). Varian terbaik menjadi preset ⭐ kualitas, varian tercepat yang skornya " +
                        "hampir sama menjadi preset ⚡ cepat. Bila hasilnya bagus (skor ≥ 60, format JSON selalu benar) " +
                        "profil disimpan otomatis ke server & GitHub; bila belum, kamu dapat saran penyesuaian. " +
                        "Butuh waktu ±3× uji cepat.\n\nUji cepat: menguji profil yang berlaku sekarang (1 varian).")
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Centang model yang mau diuji", style = MaterialTheme.typography.labelMedium, modifier = Modifier.weight(1f))
                    InfoButton("Cara kerja uji", "Model lokal diuji satu per satu (dimuat bergantian ke RAM Pi). Tiap model bisa " +
                        "makan beberapa menit sampai puluhan menit — aman ditinggal, hasilnya tersimpan.\n\nModel online " +
                        "memakai API (butuh internet & bisa berbayar), jadi disembunyikan secara bawaan.")
                }
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
        confirmButton = { TextButton(enabled = chosen.isNotEmpty(), onClick = { onStart(chosen.toList(), mode) }) { Text("Mulai (${chosen.size})") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } },
    )
}

@Composable
internal fun RunDetailDialog(c: ApiClient, id: String, isAdmin: Boolean, onDismiss: () -> Unit, onChanged: () -> Unit,
                            onOpenProfiles: () -> Unit, onSaved: () -> Unit) {
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
                // ---- kalibrasi: hasil per varian + keputusan profil ----
                if (r.variants.size > 1) {
                    HorizontalDivider()
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("🎯 Varian kalibrasi", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                        InfoButton("Varian kalibrasi", "⭐ = dipilih jadi preset kualitas (skor tertinggi).\n" +
                            "⚡ = dipilih jadi preset cepat (paling cepat per kasus, skor paling banyak 5 poin di bawah terbaik).")
                    }
                    val pick = r.profile_decision?.pilihan.orEmpty()
                    r.variants.forEach { v ->
                        val badge = listOfNotNull(if (pick["kualitas"] == v.key) "⭐" else null,
                                                  if (pick["cepat"] == v.key) "⚡" else null).joinToString("")
                        Column {
                            Text("$badge ${v.key} · ${v.label}", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold)
                            v.describe?.let { Text(it, style = MaterialTheme.typography.labelSmall) }
                            v.summary?.let { s ->
                                Text("skor ${s.score.toInt()} · ${s.avg_seconds.toInt()} dtk/kasus · format ${s.format_ok}/${s.total}" +
                                         (if (s.thinking_tokens > 0) " · ±${s.thinking_tokens} token berpikir" else ""),
                                     color = scoreColor(s.score), style = MaterialTheme.typography.labelSmall)
                            } ?: Text("${v.results.size}/6 kasus…", style = MaterialTheme.typography.labelSmall)
                        }
                    }
                    r.profile_decision?.let { d ->
                        val saved = d.saved
                        Card(colors = CardDefaults.cardColors(containerColor = (if (saved) OkGreen else WarnAmber).copy(alpha = 0.12f))) {
                            Column(Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text(if (saved) "💾 Profil disimpan otomatis (server & GitHub)"
                                     else "⚠ Perlu penyesuaian — profil belum disimpan",
                                     fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                                d.saran.forEach { Text("💡 $it", style = MaterialTheme.typography.labelSmall) }
                                Row {
                                    if (!saved && isAdmin) TextButton(onClick = {
                                        scope.launch {
                                            apiCall { c.api.benchSaveProfile(id) }.onSuccess {
                                                onSaved(); apiCall { c.api.benchRun(id) }.onSuccess { run = it }
                                            }
                                        }
                                    }) { Text("Simpan tetap") }
                                    TextButton(onClick = onOpenProfiles) { Text("Buka Profil Model") }
                                }
                            }
                        }
                    }
                    Text("Hasil per kasus di bawah = varian terbaik.", style = MaterialTheme.typography.labelSmall)
                }
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
                if (r.results.isNotEmpty()) Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Hasil per kasus", style = MaterialTheme.typography.labelMedium, modifier = Modifier.weight(1f))
                    InfoButton("Hasil per kasus", "Ketuk sebuah kasus untuk melihat jawaban asli model.\n\n✅ lulus penuh · 🟡 sebagian " +
                        "· ❌ salah · 🚫 format JSON tool salah (agent tidak bisa memakai jawabannya).")
                }
                if (r.log.isNotEmpty()) {
                    Text("Log proses", style = MaterialTheme.typography.titleSmall, modifier = Modifier.padding(top = 6.dp))
                    r.log.forEach { LogLine(it) }
                }
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
