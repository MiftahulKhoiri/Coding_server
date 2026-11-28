package id.codingserver.android.ui.terminal

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import id.codingserver.android.data.settings.TerminalPrefs
import id.codingserver.android.ui.common.InfoButton

internal data class ThemeInfo(val key: String, val label: String, val bg: Color, val fg: Color, val accent: Color)

internal val TERMINAL_THEMES = listOf(
    ThemeInfo("dark", "Gelap", Color(0xFF1E1E1E), Color(0xFFD4D4D4), Color(0xFF569CD6)),
    ThemeInfo("light", "Terang", Color(0xFFFAFAFA), Color(0xFF1F1F1F), Color(0xFF0451A5)),
    ThemeInfo("solarized", "Solarized", Color(0xFF002B36), Color(0xFF93A1A1), Color(0xFF268BD2)),
    ThemeInfo("monokai", "Monokai", Color(0xFF272822), Color(0xFFF8F8F2), Color(0xFFA6E22E)),
    ThemeInfo("retro", "Retro hijau", Color(0xFF0A0F0A), Color(0xFF33FF66), Color(0xFF66FF99)),
)

/** Pengaturan tampilan terminal: perubahan langsung diterapkan (terlihat di belakang dialog) dan disimpan. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TerminalSettingsDialog(p: TerminalPrefs, onChange: (TerminalPrefs) -> Unit, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Tampilan terminal", modifier = Modifier.weight(1f))
                InfoButton("Tampilan terminal", "Semua perubahan langsung diterapkan dan disimpan di HP ini.\n\n" +
                    "Tip: cubit dua jari di layar terminal untuk memperbesar/memperkecil huruf (seperti Termux). " +
                    "Jumlah kolom & baris menyesuaikan otomatis dan dikirim ke server.")
            }
        },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                // Pratinjau
                val th = TERMINAL_THEMES.firstOrNull { it.key == p.theme } ?: TERMINAL_THEMES[0]
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(th.bg).padding(8.dp)) {
                    val style = TextStyle(fontFamily = FontFamily.Monospace, fontSize = p.fontSize.sp,
                                          lineHeight = (p.fontSize * p.lineHeight * 1.2f).sp)
                    Text("~/proyek$ ls -la", color = th.accent, style = style)
                    Text("main.py  README.md  test_calc.py", color = th.fg, style = style)
                    Text("~/proyek$ █", color = th.accent, style = style)
                }

                Text("Ukuran huruf: ${p.fontSize}", style = MaterialTheme.typography.titleSmall)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextButton(enabled = p.fontSize > 8, onClick = { onChange(p.copy(fontSize = p.fontSize - 1)) }) { Text("A−") }
                    Slider(p.fontSize.toFloat(), { onChange(p.copy(fontSize = it.toInt())) }, valueRange = 8f..28f, steps = 19,
                           modifier = Modifier.weight(1f))
                    TextButton(enabled = p.fontSize < 28, onClick = { onChange(p.copy(fontSize = p.fontSize + 1)) }) { Text("A+") }
                }

                Text("Jarak baris: ${"%.1f".format(p.lineHeight)}", style = MaterialTheme.typography.titleSmall)
                Slider(p.lineHeight, { onChange(p.copy(lineHeight = (Math.round(it * 10) / 10f))) }, valueRange = 1f..1.6f, steps = 5)

                Text("Tema warna", style = MaterialTheme.typography.titleSmall)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    TERMINAL_THEMES.forEach { t ->
                        val sel = t.key == p.theme
                        Column(Modifier.clip(RoundedCornerShape(8.dp)).background(t.bg)
                                .border(if (sel) 3.dp else 1.dp, if (sel) MaterialTheme.colorScheme.primary else Color.Gray,
                                        RoundedCornerShape(8.dp))
                                .clickable { onChange(p.copy(theme = t.key)) }.padding(horizontal = 10.dp, vertical = 6.dp)) {
                            Text("$ ls", color = t.accent, style = TextStyle(fontFamily = FontFamily.Monospace, fontSize = 12.sp))
                            Text(t.label, color = t.fg, style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }

                Text("Kursor", style = MaterialTheme.typography.titleSmall)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf("block" to "█ Blok", "bar" to "▏Garis", "underline" to "▁ Bawah").forEach { (k, l) ->
                        FilterChip(p.cursorStyle == k, { onChange(p.copy(cursorStyle = k)) }, label = { Text(l) })
                    }
                }
                SwitchRow("Kursor berkedip", p.cursorBlink) { onChange(p.copy(cursorBlink = it)) }

                HorizontalDivider()
                SwitchRow("Baris tombol khusus", p.showKeys,
                          "ESC, TAB, ^C, ^D, panah, dan tombol ⌨ untuk memunculkan/menyembunyikan keyboard.") {
                    onChange(p.copy(showKeys = it))
                }
                SwitchRow("Tombol tambahan", p.extraKeys,
                          "Baris kedua: ^A (awal baris), ^E (akhir baris), ^R (cari riwayat), ^U/^W (hapus), PgUp/PgDn, dan simbol \$ * ' \" ; : = _.") {
                    onChange(p.copy(extraKeys = it))
                }
                SwitchRow("Ketuk = keyboard muncul", p.tapKeyboard,
                          "Mati: keyboard hanya muncul lewat tombol ⌨ (enak untuk sekadar membaca output).") {
                    onChange(p.copy(tapKeyboard = it))
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Selesai") } },
        dismissButton = { TextButton(onClick = { onChange(TerminalPrefs()) }) { Text("Reset") } },
    )
}

@Composable
private fun SwitchRow(label: String, checked: Boolean, info: String? = null, onChange: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
        if (info != null) InfoButton(label, info)
        Switch(checked, onChange)
    }
}
