package id.codingserver.android.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import id.codingserver.android.data.settings.EditorFonts
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.TitleWithInfo
import id.codingserver.android.ui.editor.EditorPresetRow
import id.codingserver.android.ui.terminal.TERMINAL_THEMES

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun FontPicker(label: String, current: String, size: Int, sizeRange: ClosedFloatingPointRange<Float>,
                       onFont: (String) -> Unit, onSize: (Int) -> Unit) {
    Text(label, style = MaterialTheme.typography.titleSmall)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        EditorFonts.forEach { (id, name) ->
            FilterChip(current == id, { onFont(id) }, label = { Text(name) })
        }
    }
    Text("Ukuran: $size", style = MaterialTheme.typography.bodySmall)
    Slider(size.toFloat(), { onSize(it.toInt()) }, valueRange = sizeRange)
    Text("Contoh ukuran: fun main() { println(\"Halo\") }", fontSize = size.sp, fontFamily = FontFamily.Monospace,
         modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(6.dp))
             .padding(8.dp))
}

/** Pengaturan → Font: jenis & ukuran huruf Code Editor dan Terminal. */
@Composable
fun FontSettingsCard(vm: AppViewModel) {
    val ed by vm.editorPrefs.collectAsState()
    val term by vm.terminalPrefs.collectAsState()
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            TitleWithInfo("Font", "Jenis huruf monospace yang dibundel di aplikasi (lisensi SIL OFL). Fira Code punya " +
                "ligatur (=> != tampil menyatu). Ubuntu Mono lebih ramping: muat lebih banyak kolom di layar HP.")
            FontPicker("Code Editor", ed.fontFamily, ed.fontSize, 9f..28f,
                onFont = { vm.setEditorPrefs(ed.copy(fontFamily = it)) }, onSize = { vm.setEditorPrefs(ed.copy(fontSize = it)) })
            HorizontalDivider(Modifier.padding(vertical = 6.dp))
            FontPicker("Terminal", term.fontFamily, term.fontSize, 8f..28f,
                onFont = { vm.setTerminalPrefs(term.copy(fontFamily = it)) }, onSize = { vm.setTerminalPrefs(term.copy(fontSize = it)) })
        }
    }
}

/** Pengaturan → Warna: tema aplikasi, warna Code Editor, tema Terminal. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ColorSettingsCards(vm: AppViewModel) {
    ThemeSettingsCard(vm)
    val ed by vm.editorPrefs.collectAsState()
    val term by vm.terminalPrefs.collectAsState()
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            TitleWithInfo("Warna Code Editor", "Preset mengatur warna teks & latar editor sekaligus mode gelap/terang. " +
                "Warna HEX sendiri bisa diatur di Code Editor → ⋮ → Pengaturan warna editor.")
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Editor gelap", Modifier.weight(1f)); Switch(ed.darkTheme, { vm.setEditorPrefs(ed.copy(darkTheme = it)) })
            }
            EditorPresetRow { p -> vm.setEditorPrefs(ed.copy(textColor = p.text, backgroundColor = p.background, darkTheme = p.dark)) }
            if (ed.textColor.isNotBlank() || ed.backgroundColor.isNotBlank()) TextButton(onClick = {
                vm.setEditorPrefs(ed.copy(textColor = "", backgroundColor = ""))
            }) { Text("Kembalikan warna otomatis") }
        }
    }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Tema Terminal", style = MaterialTheme.typography.titleMedium)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                TERMINAL_THEMES.forEach { t ->
                    val sel = term.theme == t.key
                    Column(Modifier.background(t.bg, RoundedCornerShape(8.dp))
                            .border(if (sel) 3.dp else 1.dp, if (sel) MaterialTheme.colorScheme.primary else Color.Gray,
                                    RoundedCornerShape(8.dp))
                            .clickable { vm.setTerminalPrefs(term.copy(theme = t.key)) }.padding(horizontal = 10.dp, vertical = 6.dp)) {
                        Text("$ ls", color = t.fg, fontFamily = FontFamily.Monospace)
                        Text(t.label, color = t.accent, style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}
