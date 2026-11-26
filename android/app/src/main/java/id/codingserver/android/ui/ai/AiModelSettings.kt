package id.codingserver.android.ui.ai

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.AISettings
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.theme.ErrRed
import kotlinx.coroutines.launch

/** Konfigurasi AI: Profil Model (per model) dan Parameter Chat (global AI Chat). */
@Composable
fun AiModelSettings(vm: AppViewModel, hub: AiModelHubState, isAdmin: Boolean, onOpenLab: () -> Unit) {
    val section by vm.aiConfigSection.collectAsState()
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.padding(horizontal = 10.dp, vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(section == "profil", { vm.selectAiConfigSection("profil") }, label = { Text("🎛 Profil Model") })
            FilterChip(section == "parameter", { vm.selectAiConfigSection("parameter") }, label = { Text("💬 Parameter Chat") })
        }
        Box(Modifier.weight(1f).fillMaxWidth()) {
            if (section == "parameter") ChatParams(vm, hub, isAdmin)
            else ModelProfilesScreen(vm, onOpenBench = onOpenLab)
        }
    }
}

@Composable
private fun ChatParams(vm: AppViewModel, hub: AiModelHubState, isAdmin: Boolean) {
    val scope = rememberCoroutineScope()
    var saveError by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(10.dp),
           verticalArrangement = Arrangement.spacedBy(10.dp)) {
        val st = hub.status
        if (st == null) {
            if (hub.statusError != null) Text("Pengaturan tidak bisa dimuat: ${hub.statusError}", color = ErrRed)
            else CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
        } else if (isAdmin) {
            ParamsCard(st.settings, saving) { s ->
                saving = true; saveError = null
                scope.launch {
                    apiCall { hub.c.api.aiSettings(s) }.onSuccess { hub.status = it; vm.toast("Parameter chat disimpan") }
                        .onFailure { saveError = it.message }
                    saving = false
                }
            }
            saveError?.let { Text("Gagal menyimpan: $it", color = ErrRed, style = MaterialTheme.typography.bodySmall) }
        } else {
            val s = st.settings
            AiSection("Parameter chat", "Hanya admin yang bisa mengubah parameter chat.") {
                Text("Temperature: ${"%.2f".format(s.temperature)}", style = MaterialTheme.typography.bodySmall)
                Text("Max token: ${s.max_tokens}", style = MaterialTheme.typography.bodySmall)
                Text("Riwayat pesan: ${s.history_messages}", style = MaterialTheme.typography.bodySmall)
                Text("Bongkar otomatis bila idle: " + if (s.idle_unload_minutes > 0) "${s.idle_unload_minutes} menit" else "tidak pernah",
                     style = MaterialTheme.typography.bodySmall)
            }
        }
        Spacer(Modifier.height(16.dp))
    }
}

@Composable
private fun ParamsCard(initial: AISettings, saving: Boolean, onSave: (AISettings) -> Unit) {
    var prompt by remember(initial) { mutableStateOf(initial.system_prompt) }
    var temp by remember(initial) { mutableStateOf(initial.temperature.toFloat()) }
    var maxTok by remember(initial) { mutableStateOf(initial.max_tokens.toString()) }
    var idle by remember(initial) { mutableStateOf(initial.idle_unload_minutes.toString()) }
    var hist by remember(initial) { mutableStateOf(initial.history_messages.toString()) }
    val changed = prompt != initial.system_prompt || temp.toDouble() != initial.temperature ||
        maxTok != initial.max_tokens.toString() || idle != initial.idle_unload_minutes.toString() ||
        hist != initial.history_messages.toString()
    AiSection("Parameter chat", "System prompt: instruksi dasar untuk AI Chat.\nTemperature: makin tinggi makin " +
        "kreatif, makin rendah makin konsisten (agent selalu memakai ≤ 0,4).\nMax token: panjang jawaban maksimum.\n" +
        "Riwayat pesan: jumlah pesan lama yang ikut dikirim.\n\nCatatan: bila model punya Profil Model aktif, suhu & " +
        "pengaturan sampling diambil dari profil (preset kualitas); suhu di sini dipakai bila profil dinonaktifkan.\n" +
        "Bongkar otomatis: model lokal dilepas dari RAM bila tidak dipakai sekian menit (0 = tidak pernah).") {
        OutlinedTextField(prompt, { prompt = it }, label = { Text("System prompt") },
                          modifier = Modifier.fillMaxWidth().heightIn(min = 90.dp))
        Text("Temperature: ${"%.2f".format(temp)}")
        Slider(temp, { temp = it }, valueRange = 0f..1.5f)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            OutlinedTextField(maxTok, { maxTok = it.filter(Char::isDigit) }, label = { Text("Max token") }, singleLine = true,
                              keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.weight(1f))
            OutlinedTextField(hist, { hist = it.filter(Char::isDigit) }, label = { Text("Riwayat pesan") }, singleLine = true,
                              keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.weight(1f))
        }
        OutlinedTextField(idle, { idle = it.filter(Char::isDigit) }, label = { Text("Bongkar otomatis bila idle (menit, 0 = tidak)") },
                          singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                          modifier = Modifier.fillMaxWidth())
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(enabled = changed && !saving, onClick = {
                onSave(AISettings(prompt, temp.toDouble(), maxTok.toIntOrNull()?.coerceIn(16, 65536) ?: 2048,
                                  idle.toIntOrNull() ?: 15, hist.toIntOrNull() ?: 20))
            }) { Text(if (saving) "Menyimpan…" else "Simpan parameter") }
            OutlinedButton(enabled = changed && !saving, onClick = {
                prompt = initial.system_prompt; temp = initial.temperature.toFloat()
                maxTok = initial.max_tokens.toString(); idle = initial.idle_unload_minutes.toString()
                hist = initial.history_messages.toString()
            }) { Text("Batalkan") }
        }
    }
}
