package id.codingserver.android.ui.ai

import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.AgentModelTarget
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.ApiJson
import id.codingserver.android.data.api.BenchStart
import id.codingserver.android.data.api.ModelPreset
import id.codingserver.android.data.api.ModelProfile
import id.codingserver.android.data.api.ModelProfileImport
import id.codingserver.android.data.api.ModelProfileUpdate
import id.codingserver.android.data.api.ModelProfiles
import id.codingserver.android.data.api.ProfilePurpose
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.common.InfoButton
import id.codingserver.android.ui.common.formatTime
import id.codingserver.android.ui.theme.ErrRed
import id.codingserver.android.ui.theme.OkGreen
import id.codingserver.android.ui.theme.WarnAmber
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

private fun sourceLabel(s: String): Pair<String, Color> = when (s) {
    "kalibrasi" -> "🎯 Hasil kalibrasi" to OkGreen
    "manual" -> "✏️ Diatur manual" to Color(0xFF1E88E5)
    "impor" -> "📥 Diimpor" to Color(0xFF8E24AA)
    else -> "📄 Bawaan (rekomendasi resmi)" to Color.Gray
}

private fun syncLabel(s: String?): Pair<String, Color> = when (s) {
    "ok" -> "☁ Tersimpan di server & GitHub" to OkGreen
    "gagal" -> "⚠ Belum ter-push ke GitHub" to WarnAmber
    "tidak_aktif" -> "Sinkron GitHub nonaktif" to Color.Gray
    "tertunda" -> "Menunggu sinkron" to WarnAmber
    else -> "Belum disinkronkan" to Color.Gray
}

fun presetText(p: ModelPreset): String = listOfNotNull(
    p.temperature?.let { "temp $it" }, p.top_p?.let { "top_p $it" }, p.top_k?.let { "top_k $it" },
    p.thinking?.let { if (it) "berpikir ON" else "berpikir OFF" }, "max ${p.max_tokens}",
).joinToString(" · ")

/** Profil Model: pengaturan khusus tiap model (hasil kalibrasi Uji Model), bisa diedit, diekspor, disinkronkan. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ModelProfilesScreen(vm: AppViewModel, onOpenBench: () -> Unit) {
    val client by vm.client.collectAsState()
    val user by vm.user.collectAsState()
    val isAdmin = user?.permissions?.contains("admin") == true
    val c = client ?: return
    var data by remember { mutableStateOf<ModelProfiles?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var reload by remember { mutableIntStateOf(0) }
    var open by rememberSaveable { mutableStateOf(setOf<String>()) }
    var editing by remember { mutableStateOf<ModelProfile?>(null) }
    var confirmReset by remember { mutableStateOf<ModelProfile?>(null) }
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current

    LaunchedEffect(reload) {
        apiCall { c.api.modelProfiles() }.onSuccess { data = it; error = null }.onFailure { error = it.message }
    }

    val importer = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            runCatching {
                val text = ctx.contentResolver.openInputStream(uri)!!.bufferedReader().use { it.readText() }
                ApiJson.decodeFromString(JsonObject.serializer(), text)
            }.onSuccess { obj ->
                apiCall { c.api.modelProfileImport(ModelProfileImport(obj)) }
                    .onSuccess { vm.toast("Profil ${it.model} diimpor"); reload++ }
                    .onFailure { vm.toast(it.message ?: "Gagal impor") }
            }.onFailure { vm.toast("File bukan JSON profil yang valid") }
        }
    }

    fun calibrate(p: ModelProfile) {
        scope.launch {
            // Cari koneksi lokal yang menyediakan model ini.
            var cid: String? = null
            apiCall { c.api.aiConnections() }.onSuccess { list ->
                for (cn in list.connections) {
                    val has = apiCall { c.api.aiModels(cn.id) }.getOrNull()?.models?.any { it.id == p.model } == true
                    if (has) { cid = cn.id; break }
                }
            }
            val id = cid ?: run { vm.toast("Model ${p.model} tidak ditemukan di koneksi mana pun"); return@launch }
            apiCall { c.api.benchStart(BenchStart(listOf(AgentModelTarget(id, p.model)), mode = "kalibrasi")) }
                .onSuccess { vm.toast("Kalibrasi ${p.model} dimulai di latar belakang"); onOpenBench() }
                .onFailure { vm.toast(it.message ?: "Gagal memulai kalibrasi") }
        }
    }

    fun share(p: ModelProfile) {
        val json = ApiJson.encodeToString(ModelProfile.serializer(), p)
        val send = Intent(Intent.ACTION_SEND).apply {
            type = "application/json"
            putExtra(Intent.EXTRA_SUBJECT, p.file.ifBlank { "${p.model}.json" })
            putExtra(Intent.EXTRA_TEXT, json)
        }
        ctx.startActivity(Intent.createChooser(send, "Ekspor profil ${p.model}"))
    }

    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        item {
            FlowRow(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.Center,
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = { reload++ }) { Text("Muat ulang") }
                if (isAdmin) OutlinedButton(onClick = { importer.launch("*/*") }) { Text("📥 Impor") }
                OutlinedButton(onClick = onOpenBench) { Text("🧪 Lab") }
                InfoButton("Profil Model",
                    "Setiap model punya pengaturan sendiri: suhu (temperature), top_p/top_k, mode berpikir, max token, " +
                        "dan aturan prompt tambahan.\n\n" +
                        "• Preset \"kualitas\" dipakai Perencana, Peninjau & AI Chat.\n" +
                        "• Preset \"cepat\" dipakai Pelaksana.\n\n" +
                        "Profil awal diambil dari rekomendasi resmi pembuat model. Jalankan 🎯 Kalibrasi agar diuji 3 varian " +
                        "di Pi ini — hasil yang bagus disimpan otomatis; yang belum bagus diberi saran.\n\n" +
                        "File disimpan di server (${data?.dir ?: "model_profiles/"}) dan otomatis di-commit ke GitHub.")
            }
            error?.let { ErrorCard(it) { reload++ } }
        }
        val d = data
        if (d == null) item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        else items(d.profiles, key = { it.model }) { p ->
            ProfileCard(p, d.purposes, expanded = p.model in open, isAdmin = isAdmin,
                onToggle = { open = if (p.model in open) open - p.model else open + p.model },
                onEdit = { editing = p }, onCalibrate = { calibrate(p) }, onShare = { share(p) },
                onSync = {
                    scope.launch {
                        apiCall { c.api.modelProfileSync(p.model) }.onSuccess { vm.toast(syncLabel(it.sync?.status).first); reload++ }
                            .onFailure { vm.toast(it.message ?: "Gagal") }
                    }
                }, onReset = { confirmReset = p })
        }
        item { Spacer(Modifier.height(24.dp)) }
    }

    editing?.let { p ->
        ProfileEditDialog(p, data?.purposes.orEmpty(), onDismiss = { editing = null }) { upd ->
            editing = null
            scope.launch {
                apiCall { c.api.modelProfileUpdate(p.model, upd) }.onSuccess { vm.toast("Profil ${p.model} disimpan"); reload++ }
                    .onFailure { vm.toast(it.message ?: "Gagal menyimpan") }
            }
        }
    }
    confirmReset?.let { p ->
        AlertDialog(onDismissRequest = { confirmReset = null }, title = { Text("Kembalikan ke bawaan?") },
            text = { Text("File profil ${p.model} dihapus (juga dari GitHub). Model kembali memakai rekomendasi resmi.") },
            confirmButton = {
                TextButton(onClick = {
                    confirmReset = null
                    scope.launch { apiCall { c.api.modelProfileReset(p.model) }.onSuccess { reload++ } }
                }) { Text("Kembalikan", color = ErrRed) }
            },
            dismissButton = { TextButton(onClick = { confirmReset = null }) { Text("Batal") } })
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ProfileCard(p: ModelProfile, purposes: List<ProfilePurpose>, expanded: Boolean, isAdmin: Boolean,
                        onToggle: () -> Unit, onEdit: () -> Unit, onCalibrate: () -> Unit, onShare: () -> Unit,
                        onSync: () -> Unit, onReset: () -> Unit) {
    val (src, srcCol) = sourceLabel(p.source)
    Card(Modifier.fillMaxWidth().clickable(onClick = onToggle).animateContentSize()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(p.model, style = MaterialTheme.typography.titleSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(src + if (!p.active) " · nonaktif" else "", color = srcCol, style = MaterialTheme.typography.labelSmall)
                }
                if (p.status == "perlu_penyesuaian") Text("⚠", color = WarnAmber, modifier = Modifier.padding(end = 4.dp))
                Icon(Icons.Default.ExpandMore, if (expanded) "Tutup" else "Buka")
            }
            // Kegunaan selalu terlihat: memudahkan memilih model untuk keperluan tertentu.
            FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                p.kegunaan.forEach { k ->
                    val label = purposes.firstOrNull { it.key == k }?.label?.substringBefore(" (") ?: k
                    AssistChip(onClick = onToggle, label = { Text(label, style = MaterialTheme.typography.labelSmall) },
                               modifier = Modifier.height(28.dp))
                }
            }
            if (expanded) {
                if (p.catatan.isNotBlank()) Text(p.catatan, style = MaterialTheme.typography.bodySmall)
                Text("⭐ Kualitas: ${presetText(p.preset.kualitas)}", style = MaterialTheme.typography.labelSmall)
                Text("⚡ Cepat: ${presetText(p.preset.cepat)}", style = MaterialTheme.typography.labelSmall)
                if (p.prompt_tambahan.isNotBlank()) Text("Prompt tambahan: ${p.prompt_tambahan}", style = MaterialTheme.typography.labelSmall)
                p.kalibrasi?.let { k ->
                    HorizontalDivider()
                    Text("Kalibrasi ${formatTime(k.tanggal)}", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
                    k.varian.forEach { v ->
                        val badges = listOfNotNull(if (k.pilihan["kualitas"] == v.key) "⭐" else null,
                                                   if (k.pilihan["cepat"] == v.key) "⚡" else null).joinToString("")
                        Text("$badges ${v.key} · ${v.label}: skor ${v.score?.toInt() ?: "-"} · ${v.avg_seconds?.toInt() ?: "-"} dtk/kasus · " +
                                 "format ${v.format_ok ?: "-"}/${v.total ?: "-"}", style = MaterialTheme.typography.labelSmall)
                    }
                    k.saran.forEach { Text("💡 $it", style = MaterialTheme.typography.labelSmall, color = WarnAmber) }
                }
                val (sync, syncCol) = syncLabel(p.sync?.status)
                Text(sync + (p.sync?.message?.takeIf { p.sync.status == "gagal" }?.let { ": $it" } ?: ""),
                     color = syncCol, style = MaterialTheme.typography.labelSmall, maxLines = 3)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    if (isAdmin) TextButton(onClick = onEdit) { Text("✏️ Edit") }
                    if (isAdmin) TextButton(onClick = onCalibrate) { Text("🎯 Kalibrasi") }
                    TextButton(onClick = onShare) { Text("📤 Ekspor") }
                    if (isAdmin && p.source != "bawaan") TextButton(onClick = onSync) { Text("☁ Sinkron") }
                    if (isAdmin && p.source != "bawaan") TextButton(onClick = onReset) { Text("↺ Bawaan", color = ErrRed) }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ProfileEditDialog(p: ModelProfile, purposes: List<ProfilePurpose>, onDismiss: () -> Unit,
                              onSave: (ModelProfileUpdate) -> Unit) {
    var active by remember { mutableStateOf(p.active) }
    var kegunaan by remember { mutableStateOf(p.kegunaan.toSet()) }
    var catatan by remember { mutableStateOf(p.catatan) }
    var extra by remember { mutableStateOf(p.prompt_tambahan) }
    var kualitas by remember { mutableStateOf(p.preset.kualitas) }
    var cepat by remember { mutableStateOf(p.preset.cepat) }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(p.model, maxLines = 2, overflow = TextOverflow.Ellipsis) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Profil aktif", Modifier.weight(1f))
                    InfoButton("Profil aktif", "Mati: model memakai pengaturan umum lama (Parameter chat & suhu agent ≤ 0,4).")
                    Switch(active, { active = it })
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Kegunaan", style = MaterialTheme.typography.titleSmall, modifier = Modifier.weight(1f))
                    InfoButton("Kegunaan", "Catatan untuk apa profil/model ini cocok dipakai, agar nanti mudah memilih " +
                        "model untuk peran agent atau chat. Diisi otomatis dari hasil kalibrasi, bisa diubah.")
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    purposes.forEach { pu ->
                        FilterChip(pu.key in kegunaan, {
                            kegunaan = if (pu.key in kegunaan) kegunaan - pu.key else kegunaan + pu.key
                        }, label = { Text(pu.label.substringBefore(" ("), style = MaterialTheme.typography.labelSmall) })
                    }
                }
                OutlinedTextField(catatan, { catatan = it }, label = { Text("Catatan / fungsi profil") },
                                  modifier = Modifier.fillMaxWidth().heightIn(min = 70.dp))
                OutlinedTextField(extra, { extra = it }, label = { Text("Prompt tambahan (aturan khusus model ini)") },
                                  modifier = Modifier.fillMaxWidth().heightIn(min = 70.dp))
                PresetEditor("⭐ Kualitas (Perencana, Peninjau, Chat)", kualitas, p.thinking_supported) { kualitas = it }
                PresetEditor("⚡ Cepat (Pelaksana)", cepat, p.thinking_supported) { cepat = it }
            }
        },
        confirmButton = {
            Button(onClick = {
                onSave(ModelProfileUpdate(active, kegunaan.toList(), catatan, extra, kualitas, cepat))
            }) { Text("Simpan") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Batal") } },
    )
}

@Composable
private fun PresetEditor(title: String, p: ModelPreset, thinkingSupported: Boolean?, onChange: (ModelPreset) -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall)
            Text("Temperature: ${"%.2f".format(p.temperature ?: 0.7)}", style = MaterialTheme.typography.labelMedium)
            Slider((p.temperature ?: 0.7).toFloat(), { onChange(p.copy(temperature = Math.round(it * 20) / 20.0)) },
                   valueRange = 0f..1.5f)
            Text("top_p: ${"%.2f".format(p.top_p ?: 1.0)}", style = MaterialTheme.typography.labelMedium)
            Slider((p.top_p ?: 1.0).toFloat(), { onChange(p.copy(top_p = Math.round(it * 20) / 20.0)) }, valueRange = 0.05f..1f)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                NumField("top_k", p.top_k?.toString().orEmpty(), Modifier.weight(1f)) { onChange(p.copy(top_k = it.toIntOrNull())) }
                NumField("max token", p.max_tokens.toString(), Modifier.weight(1f)) {
                    onChange(p.copy(max_tokens = (it.toIntOrNull() ?: 2048).coerceIn(64, 32768)))
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                NumField("min_p", p.min_p?.toString().orEmpty(), Modifier.weight(1f)) { onChange(p.copy(min_p = it.toDoubleOrNull())) }
                NumField("presence", p.presence_penalty?.toString().orEmpty(), Modifier.weight(1f)) {
                    onChange(p.copy(presence_penalty = it.toDoubleOrNull()))
                }
            }
            if (thinkingSupported != false) Row(verticalAlignment = Alignment.CenterVertically,
                                                horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("Berpikir:", style = MaterialTheme.typography.labelMedium)
                listOf(null to "Bawaan model", true to "ON", false to "OFF").forEach { (v, l) ->
                    FilterChip(p.thinking == v, { onChange(p.copy(thinking = v)) },
                               label = { Text(l, style = MaterialTheme.typography.labelSmall) })
                }
            }
        }
    }
}

@Composable
private fun NumField(label: String, value: String, modifier: Modifier, onChange: (String) -> Unit) {
    var text by remember(value) { mutableStateOf(value) }
    OutlinedTextField(text, { text = it.filter { ch -> ch.isDigit() || ch == '.' || ch == '-' }; onChange(text) },
                      label = { Text(label, style = MaterialTheme.typography.labelSmall) }, singleLine = true,
                      keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = modifier)
}
