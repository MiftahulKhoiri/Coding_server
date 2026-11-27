package id.codingserver.android.ui.ai

import androidx.compose.animation.animateContentSize
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.BenchLive
import id.codingserver.android.data.api.BenchLogEntry
import id.codingserver.android.data.api.BenchRun
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.common.InfoButton
import id.codingserver.android.ui.theme.ErrRed
import id.codingserver.android.ui.theme.Mono
import id.codingserver.android.ui.theme.OkGreen
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private val TIME = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

private fun phaseText(l: BenchLive): Pair<String, Color> = when (l.phase) {
    "loading" -> "📦 Memuat model ke RAM" to Color(0xFF6D4C41)
    "prompt" -> "📖 Membaca prompt" + (l.approx_prompt_tokens?.let { " ±$it token" } ?: "") to Color(0xFF00897B)
    "thinking" -> "🧠 Berpikir · ${l.reasoning_tokens} token" + (l.tps?.let { " · $it tok/dtk" } ?: "") to Color(0xFF8E24AA)
    "writing" -> "✍️ Menulis jawaban · ${l.tokens} token" + (l.tps?.let { " · $it tok/dtk" } ?: "") to Color(0xFF1E88E5)
    "checking" -> "🧪 Memeriksa hasil (format & tes sandbox)" to OkGreen
    else -> "⏳ ${l.phase}" to Color.Gray
}

private fun kindColor(kind: String): Color = when (kind) {
    "error" -> ErrRed
    "score", "done" -> OkGreen
    "case" -> Color(0xFF1E88E5)
    "think" -> Color(0xFF8E24AA)
    else -> Color.Unspecified
}

/** Panel log langsung di bawah kartu uji yang sedang berjalan: tahap, teks yang sedang ditulis, dan riwayat log. */
@Composable
fun BenchLiveLog(c: ApiClient, runId: String) {
    var run by remember(runId) { mutableStateOf<BenchRun?>(null) }
    var showAll by remember(runId) { mutableStateOf(false) }
    LaunchedEffect(runId) {
        while (true) {
            apiCall { c.api.benchRun(runId) }.onSuccess { run = it }
            if (run?.status !in setOf(null, "PENDING", "RUNNING")) break
            delay(2000)
        }
    }
    val r = run ?: return
    Column(Modifier.fillMaxWidth().animateContentSize(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        r.live?.let { l -> LiveModelPanel(l) }
        if (r.log.isNotEmpty()) {
            HorizontalDivider()
            val lines = if (showAll) r.log else r.log.takeLast(8)
            Text("Log proses", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
            lines.forEach { LogLine(it) }
            if (r.log.size > 8) TextButton(onClick = { showAll = !showAll }) {
                Text(if (showAll) "Tampilkan 8 terakhir" else "Tampilkan semua (${r.log.size})")
            }
        }
    }
}

/**
 * Proses model secara langsung: tahap (memuat / membaca prompt / berpikir / menulis), kecepatan, dan teks yang
 * sedang keluar dari model. Dipakai Laboratorium (Uji Model) dan AI Agent.
 */
@Composable
fun LiveModelPanel(l: BenchLive, header: String? = null, textMaxHeight: Int = 160) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        header?.let { Text(it, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold) }
        val (txt, col) = phaseText(l)
        val tr = rememberInfiniteTransition(label = "live")
        val blink by tr.animateFloat(0.35f, 1f, infiniteRepeatable(tween(700), RepeatMode.Reverse), label = "blink")
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.width(10.dp).heightIn(min = 10.dp, max = 10.dp).clip(RoundedCornerShape(50))
                    .alpha(blink).background(col))
            Spacer(Modifier.width(8.dp))
            Text(txt, color = col, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold,
                 modifier = Modifier.weight(1f))
            Text("${l.elapsed.toInt()} dtk", style = MaterialTheme.typography.labelSmall)
            InfoButton("Tahap proses model",
                "📦 Memuat model: file model dibaca ke RAM Pi (1–3 menit).\n" +
                    "📖 Membaca prompt: model memproses instruksi & riwayat sebelum menjawab — di CPU Pi bagian " +
                    "paling lama (bisa beberapa menit), belum ada teks yang keluar.\n" +
                    "🧠 Berpikir: model penalaran (mis. Qwen3.5) menulis pikirannya dulu.\n" +
                    "✍️ Menulis jawaban: teks jawaban keluar token demi token.\n" +
                    "🧪 Memeriksa: format JSON dicek & kode dijalankan di sandbox terhadap tes tersembunyi.")
        }
        if (l.text.isNotBlank()) {
            Text(if (l.phase == "thinking") "Isi pikiran model (langsung):" else "Yang sedang ditulis model (langsung):",
                 style = MaterialTheme.typography.labelSmall)
            val scroll = rememberScrollState()
            LaunchedEffect(l.text) { scroll.scrollTo(scroll.maxValue) }
            Box(Modifier.fillMaxWidth().heightIn(max = textMaxHeight.dp).clip(RoundedCornerShape(6.dp))
                    .background(Color(0xFF1E1E1E)).padding(8.dp).verticalScroll(scroll)) {
                Text(l.text + "▌", style = Mono, color = if (l.phase == "thinking") Color(0xFFCE93D8) else Color(0xFFE0E0E0))
            }
        } else if (l.phase == "prompt") {
            Text("Model sedang membaca instruksi & konteks — teks muncul di sini begitu model mulai berpikir/menulis.",
                 style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
fun LogLine(e: BenchLogEntry) {
    Row {
        Text(TIME.format(Date((e.ts * 1000).toLong())), style = MaterialTheme.typography.labelSmall,
             color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(end = 6.dp))
        Text(e.text, style = MaterialTheme.typography.bodySmall, color = kindColor(e.kind))
    }
}
