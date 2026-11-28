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
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.theme.AppFonts
import id.codingserver.android.ui.theme.AppTextScales
import id.codingserver.android.ui.theme.appFontFamily
import id.codingserver.android.ui.common.TitleWithInfo
import id.codingserver.android.ui.editor.EditorPresetRow
import id.codingserver.android.ui.terminal.TERMINAL_THEMES

/** Pengaturan → Font: jenis & ukuran huruf tampilan aplikasi (editor & terminal diatur di layarnya masing-masing). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FontSettingsCard(vm: AppViewModel) {
    val theme by vm.appTheme.collectAsState()
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            TitleWithInfo("Font tampilan", "Jenis & ukuran huruf seluruh tampilan aplikasi (menu, pengaturan, dialog). " +
                "Huruf kode diatur terpisah: Code Editor → ⋮ → Pengaturan editor, dan Terminal → ⚙.")
            Text("Jenis huruf", style = MaterialTheme.typography.titleSmall)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                AppFonts.forEach { (key, name) ->
                    FilterChip(theme.font == key, { vm.setAppTheme(theme.copy(font = key)) },
                        label = { Text(name, fontFamily = appFontFamily(key)) })
                }
            }
            Text("Ukuran teks", style = MaterialTheme.typography.titleSmall)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                AppTextScales.forEach { (scale, name) ->
                    FilterChip(kotlin.math.abs(theme.textScale - scale) < 0.01f, { vm.setAppTheme(theme.copy(textScale = scale)) },
                        label = { Text(name) })
                }
            }
            Text("Contoh: Proyek tes · 4 file · AI Agent selesai ✓", style = MaterialTheme.typography.bodyLarge,
                 modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(6.dp))
                     .padding(10.dp))
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
