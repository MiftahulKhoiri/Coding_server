package id.codingserver.android.ui.common

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.settings.EditorFonts

/** Pilihan jenis huruf monospace untuk Code Editor & Terminal (font dibundel di aset web/fonts). */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MonoFontChips(current: String, onPick: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        EditorFonts.forEach { (id, name) -> FilterChip(current == id, { onPick(id) }, label = { Text(name) }) }
    }
}
