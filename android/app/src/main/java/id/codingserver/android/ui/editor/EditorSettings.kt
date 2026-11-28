package id.codingserver.android.ui.editor

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.InfoButton

/** Pengaturan perilaku Code Editor (font & warna ada di Pengaturan → Font / Warna). */
@Composable
fun EditorSettingsDialog(vm: AppViewModel, onDismiss: () -> Unit) {
    val prefs by vm.editorPrefs.collectAsState()
    @Composable
    fun Toggle(label: String, value: Boolean, info: String? = null, onChange: (Boolean) -> Unit) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically) {
                Text(label, modifier = Modifier.weight(1f, fill = false))
                if (info != null) InfoButton(label, info)
            }
            Switch(value, onChange)
        }
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Pengaturan editor") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("Jenis huruf", style = MaterialTheme.typography.titleSmall)
                id.codingserver.android.ui.common.MonoFontChips(prefs.fontFamily) { vm.setEditorPrefs(prefs.copy(fontFamily = it)) }
                Text("Ukuran huruf: ${prefs.fontSize}", style = MaterialTheme.typography.titleSmall)
                Slider(prefs.fontSize.toFloat(), { vm.setEditorPrefs(prefs.copy(fontSize = it.toInt())) }, valueRange = 9f..28f)
                androidx.compose.material3.HorizontalDivider()
                Toggle("Language server", prefs.lsp, "Autocomplete pintar, error saat mengetik, info simbol, ke definisi, " +
                    "referensi & ganti nama lintas file. Dijalankan di server untuk C/C++, Python, JS/TS, Go, PHP, HTML, " +
                    "CSS, JSON, dan Bash.") { vm.setEditorPrefs(prefs.copy(lsp = it)) }
                Toggle("Ketuk kode = keyboard muncul", prefs.tapKeyboard, "Aktif: mengetuk kode langsung memunculkan " +
                    "keyboard.\nMati: ketukan hanya memindah kursor, enak untuk membaca kode. Keyboard dibuka/ditutup " +
                    "dengan tombol ⌨. Menggeser layar tidak pernah memunculkan keyboard.") { vm.setEditorPrefs(prefs.copy(tapKeyboard = it)) }
                Toggle("Baris tombol ekstra", prefs.keyBar) { vm.setEditorPrefs(prefs.copy(keyBar = it)) }
                Toggle("Simpan otomatis", prefs.autoSave, "Disimpan ±2 detik setelah berhenti mengetik.") {
                    vm.setEditorPrefs(prefs.copy(autoSave = it)) }
                Toggle("Word wrap", prefs.wordWrap) { vm.setEditorPrefs(prefs.copy(wordWrap = it)) }
                Text("Lebar tab: ${prefs.tabSize}", style = MaterialTheme.typography.bodyMedium)
                Slider(prefs.tabSize.toFloat(), { vm.setEditorPrefs(prefs.copy(tabSize = it.toInt())) }, valueRange = 2f..8f, steps = 5)
                Text("Warna editor: Pengaturan → Warna, atau ⋮ → Pengaturan warna editor.",
                     style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Tutup") } },
    )
}
