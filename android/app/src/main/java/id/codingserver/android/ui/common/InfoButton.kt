package id.codingserver.android.ui.common

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Info
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

/**
 * Tombol (i) kecil di samping judul/tombol/pengaturan. Penjelasan fungsi disembunyikan di sini agar layar
 * tetap ringkas; diketuk -> muncul kartu info, ditutup dengan "Mengerti".
 */
@Composable
fun InfoButton(title: String, text: String, modifier: Modifier = Modifier) {
    var open by rememberSaveable { mutableStateOf(false) }
    IconButton(onClick = { open = true }, modifier = modifier.size(32.dp)) {
        Icon(Icons.Outlined.Info, contentDescription = "Info: $title", tint = MaterialTheme.colorScheme.primary,
             modifier = Modifier.size(18.dp))
    }
    if (open) AlertDialog(
        onDismissRequest = { open = false },
        icon = { Icon(Icons.Outlined.Info, null, tint = MaterialTheme.colorScheme.primary) },
        title = { Text(title) },
        text = { Text(text, style = MaterialTheme.typography.bodyMedium) },
        confirmButton = { TextButton(onClick = { open = false }) { Text("Mengerti") } },
    )
}

/** Baris judul + tombol info di sebelahnya. */
@Composable
fun TitleWithInfo(title: String, info: String, modifier: Modifier = Modifier,
                  style: androidx.compose.ui.text.TextStyle = MaterialTheme.typography.titleMedium) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        Text(title, style = style, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
        InfoButton(title, info)
    }
}
