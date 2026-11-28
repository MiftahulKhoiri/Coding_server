package id.codingserver.android.ui.editor

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.size
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.GrepMatch
import id.codingserver.android.data.api.GrepRequest
import id.codingserver.android.data.api.GrepResult
import id.codingserver.android.data.api.ReplaceRequest
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ConfirmDialog
import kotlinx.coroutines.launch

/** Cari (teks / regex, huruf besar-kecil, kata utuh) di seluruh proyek, lalu ganti semua bila perlu. */
@Composable
fun ProjectSearchDialog(vm: AppViewModel, c: ApiClient, projectId: String, canWrite: Boolean, onDismiss: () -> Unit,
                        onOpen: (GrepMatch) -> Unit, onReplaced: (List<String>) -> Unit) {
    val scope = rememberCoroutineScope()
    var query by remember { mutableStateOf(lastQuery) }
    var replacement by remember { mutableStateOf("") }
    var regex by remember { mutableStateOf(false) }
    var caseSensitive by remember { mutableStateOf(false) }
    var wholeWord by remember { mutableStateOf(false) }
    var showReplace by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<GrepResult?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var confirm by remember { mutableStateOf(false) }

    fun search() {
        if (query.isBlank()) return
        lastQuery = query
        busy = true; error = null
        scope.launch {
            apiCall { c.api.grep(GrepRequest(projectId, query, regex, caseSensitive, wholeWord)) }
                .onSuccess { result = it }.onFailure { error = it.message; result = null }
            busy = false
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Cari di proyek") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedTextField(query, { query = it }, singleLine = true, label = { Text("Cari") },
                                  modifier = Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip(caseSensitive, { caseSensitive = !caseSensitive }, label = { Text("Aa") })
                    FilterChip(wholeWord, { wholeWord = !wholeWord }, label = { Text("Kata utuh") })
                    FilterChip(regex, { regex = !regex }, label = { Text(".* Regex") })
                }
                if (showReplace) OutlinedTextField(replacement, { replacement = it }, singleLine = true,
                    label = { Text(if (regex) "Ganti dengan (\\1 = grup 1)" else "Ganti dengan") }, modifier = Modifier.fillMaxWidth())
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Button(onClick = ::search, enabled = !busy && query.isNotBlank()) { Text("Cari") }
                    if (canWrite) OutlinedButton(onClick = {
                        if (!showReplace) showReplace = true else if (result?.matches?.isNotEmpty() == true) confirm = true
                    }, enabled = !busy && (!showReplace || result?.matches?.isNotEmpty() == true)) {
                        Text(if (showReplace) "Ganti semua" else "Ganti…")
                    }
                    if (busy) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                result?.let { r ->
                    Text("${r.matches.size}${if (r.truncated) "+" else ""} hasil di ${r.files} file",
                         style = MaterialTheme.typography.labelMedium)
                    LazyColumn(Modifier.heightIn(max = 340.dp)) {
                        items(r.matches) { m ->
                            Column(Modifier.fillMaxWidth().clickable { onOpen(m) }.padding(vertical = 4.dp)) {
                                Text("${m.path}:${m.line}", style = MaterialTheme.typography.labelSmall,
                                     color = MaterialTheme.colorScheme.primary)
                                Text(highlight(m), style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace,
                                     maxLines = 2)
                            }
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Tutup") } },
    )
    if (confirm) result?.let { r ->
        val files = r.matches.map { it.path }.distinct()
        ConfirmDialog("Ganti semua?",
            "Ganti ${r.matches.size}${if (r.truncated) "+" else ""} kemunculan \"$query\" dengan \"$replacement\" di ${files.size} file. " +
                "Setiap file tercatat di riwayat versi (bisa dipulihkan).",
            "Ganti semua", onConfirm = {
                busy = true
                scope.launch {
                    apiCall { c.api.replaceAll(ReplaceRequest(projectId, query, replacement, regex, caseSensitive, wholeWord,
                                                              if (r.truncated) null else files)) }
                        .onSuccess { out ->
                            vm.toast("${out.total} kemunculan diganti di ${out.files.size} file")
                            onReplaced(out.files.map { it.path })
                            result = null
                        }.onFailure { error = it.message }
                    busy = false
                }
            }, onDismiss = { confirm = false })
    }
}

/** Baris hasil dengan bagian yang cocok ditebalkan. Server memangkas indentasi (offset = jumlah karakter terbuang). */
private fun highlight(m: GrepMatch) = buildAnnotatedString {
    val t = m.text
    val at = m.column - 1 - m.offset
    if (at < 0 || at >= t.length || m.length <= 0) { append(t); return@buildAnnotatedString }
    val end = (at + m.length).coerceAtMost(t.length)
    append(t.substring(0, at))
    withStyle(SpanStyle(fontWeight = FontWeight.Bold, background = androidx.compose.ui.graphics.Color(0x55FFD54F))) {
        append(t.substring(at, end))
    }
    append(t.substring(end))
}

private var lastQuery = ""
