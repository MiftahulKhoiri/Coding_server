package id.codingserver.android.ui.ai

import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.AIConnection
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.ContextIn
import id.codingserver.android.data.api.ContextModel
import id.codingserver.android.data.api.ContextStatus
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.theme.OkGreen
import id.codingserver.android.ui.theme.WarnAmber
import kotlinx.coroutines.launch

/** Pilihan ukuran konteks (token). 0 = ikut bawaan (khusus per model). */
private val CTX_CHOICES = listOf(4096, 8192, 12288, 16384, 24576, 32768)

private fun fmt(v: Int?) = when {
    v == null || v == 0 -> "-"
    v % 1024 == 0 -> "${v / 1024}K"
    else -> "$v"
}

/**
 * Konteks model llama-server (mode router): bawaan semua model + per model. CODING_SERVER menulis file preset,
 * router memuatnya ulang tanpa restart; model yang konteksnya berubah dimuat ulang saat dipakai berikutnya.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ModelContextSection(vm: AppViewModel, c: ApiClient, conns: List<AIConnection>?, isAdmin: Boolean) {
    val routers = conns.orEmpty().filter { it.kind == "llama_router" }
    var cid by remember(routers) { mutableStateOf(routers.firstOrNull()?.id) }
    var st by remember { mutableStateOf<ContextStatus?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<ContextModel?>(null) }
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboardManager.current

    suspend fun load() {
        val id = cid ?: return
        apiCall { c.api.aiContext(id) }.onSuccess { st = it; error = null }.onFailure { error = it.message }
    }
    LaunchedEffect(cid) { st = null; load() }

    fun save(body: ContextIn, msg: String) {
        if (saving) return
        saving = true
        scope.launch {
            apiCall { c.api.aiContextSave(body) }.onSuccess { st = it; vm.toast(msg) }
                .onFailure { vm.toast(it.message ?: "Gagal menyimpan") }
            saving = false
        }
    }

    AiSection("📏 Konteks model", "Ukuran konteks = berapa banyak teks (riwayat kerja agent, isi file, instruksi) yang " +
        "bisa dilihat model sekaligus. Terlalu kecil → agent sering lupa isi file dan mengulang langkah; terlalu besar → " +
        "butuh RAM lebih banyak dan sedikit lebih lambat.\n\nPerkiraan RAM tambahan: tiap +8K token ≈ +0,5–1 GB per model " +
        "yang termuat. Pi 16 GB dengan 1 model 7B: 16K aman. Dengan 2 model termuat bersamaan, tetap 8K.\n\n" +
        "Disimpan di file preset llama-server; router membacanya ulang tanpa restart. Model yang konteksnya berubah " +
        "dimuat ulang saat dipakai berikutnya.") {
        if (routers.isEmpty()) {
            Text("Belum ada koneksi llama-server (mode router). Pengaturan konteks hanya untuk model lokal di llama-server.",
                 style = MaterialTheme.typography.bodySmall)
            return@AiSection
        }
        if (routers.size > 1) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            routers.forEach { r -> FilterChip(selected = cid == r.id, onClick = { cid = r.id }, label = { Text(r.name) }) }
        }
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
        val s = st ?: run { if (error == null) Text("Memuat…", style = MaterialTheme.typography.bodySmall); return@AiSection }

        if (s.problems.isNotEmpty()) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("⚠ Belum aktif di llama-server:", color = WarnAmber, fontWeight = FontWeight.Bold,
                     style = MaterialTheme.typography.bodySmall)
                s.problems.forEach { Text("• $it", color = WarnAmber, style = MaterialTheme.typography.bodySmall) }
                Text("Jalankan sekali di Raspberry Pi (butuh sandi sudo):", style = MaterialTheme.typography.labelMedium)
                SelectionContainer {
                    Text(s.fix_command, fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.labelSmall)
                }
                Row {
                    TextButton(onClick = { clipboard.setText(AnnotatedString(s.fix_command)); vm.toast("Perintah disalin") }) {
                        Text("Salin perintah")
                    }
                    TextButton(onClick = { scope.launch { load() } }) { Text("Periksa lagi") }
                }
            }
            HorizontalDivider()
        } else {
            Text("✓ llama-server memakai pengaturan ini", color = OkGreen, style = MaterialTheme.typography.labelMedium)
        }

        Text("Bawaan semua model: ${fmt(s.default_ctx)}" + if (s.default_ctx == null) " (mengikuti llama-server)" else "",
             style = MaterialTheme.typography.bodyMedium)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            CTX_CHOICES.forEach { v ->
                FilterChip(selected = s.default_ctx == v, enabled = isAdmin && !saving,
                           onClick = { save(ContextIn(s.connection_id, default_ctx = v), "Konteks bawaan: ${fmt(v)}") },
                           label = { Text(fmt(v)) })
            }
        }
        HorizontalDivider()
        Text("Per model (ketuk untuk mengubah):", style = MaterialTheme.typography.labelMedium)
        s.models.forEach { m ->
            Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(m.id, style = MaterialTheme.typography.bodySmall,
                         fontWeight = if (m.status == "loaded") FontWeight.Bold else null)
                    Text(buildString {
                        append(if (m.status == "loaded") "di RAM · " else "")
                        append("dipakai ${fmt(m.ctx)}")
                        if (m.configured != null && m.configured != m.ctx) append(" → ${fmt(m.configured)} saat dimuat ulang")
                        if (m.override != null) append(" · khusus model ini")
                    }, style = MaterialTheme.typography.labelSmall,
                         color = if (m.configured != null && m.configured != m.ctx) WarnAmber else MaterialTheme.colorScheme.onSurfaceVariant)
                }
                TextButton(enabled = isAdmin && !saving, onClick = { editing = m }) { Text(fmt(m.override ?: m.configured ?: m.ctx)) }
            }
        }
        Text("File: ${s.preset_file}", style = MaterialTheme.typography.labelSmall)
    }

    editing?.let { m ->
        AlertDialog(
            onDismissRequest = { editing = null },
            title = { Text("Konteks ${m.id}") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Sekarang dipakai: ${fmt(m.ctx)}. Bila model sedang di RAM, ia dimuat ulang dengan ukuran baru.",
                         style = MaterialTheme.typography.bodySmall)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        FilterChip(selected = m.override == null, onClick = {
                            editing = null
                            save(ContextIn(st!!.connection_id, models = mapOf(m.id to 0)), "${m.id}: ikut bawaan")
                        }, label = { Text("Ikut bawaan") })
                        CTX_CHOICES.forEach { v ->
                            FilterChip(selected = m.override == v, onClick = {
                                editing = null
                                save(ContextIn(st!!.connection_id, models = mapOf(m.id to v)), "${m.id}: ${fmt(v)}")
                            }, label = { Text(fmt(v)) })
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { editing = null }) { Text("Tutup") } },
        )
    }
}
