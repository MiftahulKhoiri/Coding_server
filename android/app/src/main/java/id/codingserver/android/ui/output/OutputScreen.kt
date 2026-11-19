package id.codingserver.android.ui.output

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.Artifact
import id.codingserver.android.data.api.Job
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.EditorTab
import id.codingserver.android.ui.common.formatBytes
import id.codingserver.android.ui.common.formatTime
import id.codingserver.android.ui.editor.DiagnosticParser
import id.codingserver.android.ui.editor.EditorController
import id.codingserver.android.ui.theme.ErrRed
import id.codingserver.android.ui.theme.Mono
import id.codingserver.android.ui.theme.OkGreen
import id.codingserver.android.ui.theme.WarnAmber
import kotlinx.coroutines.launch

fun statusColor(s: String) = when (s) {
    "COMPLETED" -> OkGreen
    "FAILED", "TIMEOUT" -> ErrRed
    "CANCELLED" -> WarnAmber
    else -> Color(0xFF64B5F6)
}

/** Build Output: status, output real-time, stdin, stop, durasi, lokasi artefak, error yang bisa diklik, riwayat. */
@Composable
fun OutputScreen(vm: AppViewModel, editor: EditorController, onGotoEditor: () -> Unit) {
    val run by vm.run.collectAsState()
    val client by vm.client.collectAsState()
    val project by vm.project.collectAsState()
    var tab by remember { mutableIntStateOf(0) }
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var stdin by remember { mutableStateOf("") }
    var artifacts by remember { mutableStateOf<List<Artifact>>(emptyList()) }
    var history by remember { mutableStateOf<List<Job>>(emptyList()) }
    val listState = rememberLazyListState()

    val r = run
    val finished = r?.status in setOf("COMPLETED", "FAILED", "TIMEOUT", "CANCELLED")
    val outputText = r?.combined?.joinToString("") { it.second } ?: ""
    val diags = remember(finished, r?.job?.process_id) {
        if (r != null && finished) DiagnosticParser.parse(outputText, r.job.file) else emptyList()
    }

    LaunchedEffect(finished, r?.job?.process_id) {
        if (r != null && finished) {
            val c = client ?: return@LaunchedEffect
            apiCall { c.api.artifacts(r.job.project_id) }.onSuccess { artifacts = it.artifacts }
            val tabId = "${r.job.project_id}:${r.job.file}"
            if (diags.isNotEmpty() && vm.activeTab.value == tabId) editor.setDiagnostics(diags)
        }
    }
    LaunchedEffect(tab, project) {
        if (tab == 1) {
            val c = client ?: return@LaunchedEffect
            apiCall { c.api.executions(project?.id) }.onSuccess { history = it.executions }
        }
    }
    LaunchedEffect(r?.version) { if (r != null && r.combined.isNotEmpty()) listState.animateScrollToItem(r.combined.size - 1) }

    Column(Modifier.fillMaxSize()) {
        TabRow(selectedTabIndex = tab) {
            Tab(tab == 0, { tab = 0 }, text = { Text("Output") })
            Tab(tab == 1, { tab = 1 }, text = { Text("Riwayat") })
        }
        if (tab == 1) {
            LazyColumn(Modifier.fillMaxSize()) {
                items(history, key = { it.process_id }) { j ->
                    Column(Modifier.fillMaxWidth().clickable {
                        val c = client ?: return@clickable
                        scope.launch { apiCall { c.api.job(j.process_id) }.onSuccess { full -> vm.attach(full); tab = 0 } }
                    }.padding(10.dp)) {
                        Text("${j.action.uppercase()} ${j.file} [${j.language}]", style = MaterialTheme.typography.bodyMedium)
                        Text("${j.status} · exit ${j.exit_code ?: "-"} · ${j.duration?.let { "%.2fs".format(it) } ?: "-"} · ${formatTime(j.created_at)}",
                             color = statusColor(j.status), style = MaterialTheme.typography.bodySmall)
                    }
                    HorizontalDivider()
                }
            }
            return@Column
        }
        if (r == null) {
            Text("Belum ada program yang dijalankan. Tekan ▶ di editor.", Modifier.padding(16.dp)); return@Column
        }
        Row(Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            AssistChip(onClick = {}, label = { Text(r.status, color = statusColor(r.status)) })
            Column(Modifier.weight(1f)) {
                Text("${r.job.action} · ${r.job.file}", style = MaterialTheme.typography.bodyMedium)
                val dur = r.job.duration?.let { "%.2f s".format(it) } ?: "…"
                Text("${r.job.language} · exit ${r.job.exit_code ?: "-"} · durasi $dur" + if (r.phase.isNotBlank() && !finished) " · ${r.phase}" else "",
                     style = MaterialTheme.typography.bodySmall)
            }
            if (!finished) Button(onClick = { vm.stopRun() }) { Text("Stop") }
        }
        if (r.job.error.isNotBlank()) Text(r.job.error, color = ErrRed, modifier = Modifier.padding(horizontal = 8.dp))
        r.job.preview_path?.let { path ->
            OutlinedButton(onClick = {
                val c = client ?: return@OutlinedButton
                scope.launch {
                    apiCall { c.api.previewToken(r.job.project_id, path) }.onSuccess { t ->
                        ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(c.baseUrl.trimEnd('/') + t.url)))
                    }.onFailure { vm.toast(it.message ?: "") }
                }
            }, modifier = Modifier.padding(horizontal = 8.dp)) { Text("Buka pratinjau HTML") }
        }
        if (diags.isNotEmpty()) {
            Column(Modifier.padding(horizontal = 8.dp)) {
                Text("${diags.size} masalah (ketuk untuk ke baris):", style = MaterialTheme.typography.labelMedium)
                diags.take(20).forEach { d ->
                    Text("${d.severity.uppercase()} baris ${d.line}: ${d.message}",
                        color = if (d.severity == "error") ErrRed else WarnAmber, style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.fillMaxWidth().clickable {
                            vm.addOrFocusTab(EditorTab(r.job.project_id, r.job.file, null))
                            onGotoEditor()
                            scope.launch { editor.setDiagnostics(diags); editor.gotoLine(d.line) }
                        }.padding(vertical = 2.dp))
                }
            }
        }
        SelectionContainer(Modifier.weight(1f).fillMaxWidth().background(Color(0xFF1E1E1E))) {
            LazyColumn(state = listState, modifier = Modifier.fillMaxSize().horizontalScroll(rememberScrollState()).padding(6.dp)) {
                items(r.combined.size) { i ->
                    val (stream, text) = r.combined[i]
                    Text(buildAnnotatedString {
                        withStyle(SpanStyle(color = if (stream == "stderr") Color(0xFFFF8A80) else Color(0xFFE0E0E0))) { append(text) }
                    }, style = Mono)
                }
            }
        }
        if (!finished) {
            Row(Modifier.fillMaxWidth().padding(6.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(stdin, { stdin = it }, label = { Text("Input (stdin)") }, singleLine = true, modifier = Modifier.weight(1f))
                TextButton(onClick = { vm.sendStdin(stdin + "\n"); stdin = "" }) { Text("Kirim") }
                TextButton(onClick = { vm.sendStdin("", eof = true) }) { Text("EOF") }
            }
        } else if (artifacts.isNotEmpty()) {
            Column(Modifier.padding(8.dp)) {
                Text("Artefak build:", style = MaterialTheme.typography.labelMedium)
                artifacts.take(5).forEach { a -> Text("${a.location} (${formatBytes(a.size)})", style = MaterialTheme.typography.bodySmall) }
            }
        }
    }
}
