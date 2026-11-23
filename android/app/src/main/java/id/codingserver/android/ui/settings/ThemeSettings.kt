package id.codingserver.android.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.Card
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.theme.AccentPalette
import id.codingserver.android.ui.theme.ThemeMode
import id.codingserver.android.ui.theme.isAppDark

/** Pengaturan tampilan aplikasi: mode terang/gelap, warna aksen, latar AMOLED. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ThemeSettingsCard(vm: AppViewModel) {
    val theme by vm.appTheme.collectAsState()
    val dark = isAppDark(theme)
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Tampilan", style = MaterialTheme.typography.titleMedium)

            Text("Mode", style = MaterialTheme.typography.labelLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ThemeMode.entries.forEach { m ->
                    FilterChip(selected = theme.mode == m, onClick = { vm.setAppTheme(theme.copy(mode = m)) }, label = { Text(m.label) })
                }
            }

            Text("Warna tema", style = MaterialTheme.typography.labelLarge)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                AccentPalette.entries.forEach { p ->
                    val enabled = p != AccentPalette.DYNAMIC || AccentPalette.dynamicSupported
                    AccentSwatch(p, dark, selected = theme.accent == p, enabled = enabled) { vm.setAppTheme(theme.copy(accent = p)) }
                }
            }
            if (!AccentPalette.dynamicSupported) {
                Text("\"Dinamis\" (warna dari wallpaper) butuh Android 12 ke atas.", style = MaterialTheme.typography.bodySmall)
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Hitam pekat (AMOLED)")
                    Text("Latar hitam murni di mode gelap, hemat baterai.", style = MaterialTheme.typography.bodySmall)
                }
                Switch(theme.amoled, { vm.setAppTheme(theme.copy(amoled = it)) }, enabled = dark)
            }
        }
    }
}

@Composable
private fun AccentSwatch(p: AccentPalette, dark: Boolean, selected: Boolean, enabled: Boolean, onClick: () -> Unit) {
    val primary = if (dark) p.darkPrimary else p.lightPrimary
    val fill = if (p == AccentPalette.DYNAMIC)
        Brush.sweepGradient(listOf(Color(0xFFEF5350), Color(0xFFFFCA28), Color(0xFF66BB6A), Color(0xFF42A5F5), Color(0xFFAB47BC), Color(0xFFEF5350)))
    else Brush.linearGradient(listOf(primary, if (dark) p.darkSecondary else p.lightSecondary))
    Column(
        Modifier.width(60.dp).alpha(if (enabled) 1f else 0.4f)
            .clickable(enabled = enabled, role = Role.RadioButton, onClick = onClick)
            .semantics { this.selected = selected; contentDescription = "Warna ${p.label}" },
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            Modifier.size(40.dp).clip(CircleShape).background(fill)
                .border(if (selected) 3.dp else 1.dp, if (selected) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.outline, CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            if (selected) Icon(Icons.Default.Check, null, tint = if (p == AccentPalette.DYNAMIC) Color.White else contrastOn(primary))
        }
        Text(p.label, style = MaterialTheme.typography.labelSmall, textAlign = TextAlign.Center, maxLines = 1)
    }
}

private fun contrastOn(c: Color) = if (0.2126f * c.red + 0.7152f * c.green + 0.0722f * c.blue > 0.5f) Color(0xFF111111) else Color.White
