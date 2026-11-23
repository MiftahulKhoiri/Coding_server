package id.codingserver.android.ui.ai

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.AIProposalItem
import id.codingserver.android.data.api.AIStatus
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.formatTime
import id.codingserver.android.ui.editor.EditorController
import id.codingserver.android.ui.theme.ErrRed
import id.codingserver.android.ui.theme.Mono
import id.codingserver.android.ui.theme.OkGreen
import id.codingserver.android.ui.theme.WarnAmber
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Potong teks markdown menjadi bagian teks biasa dan blok kode ```bahasa. */
data class MdPart(val code: Boolean, val text: String, val lang: String = "")

fun splitMarkdown(src: String): List<MdPart> {
    val out = mutableListOf<MdPart>()
    val re = Regex("```([\\w+#.-]*)[^\\n]*\\n([\\s\\S]*?)(```|$)")
    var last = 0
    for (m in re.findAll(src)) {
        if (m.range.first > last) out += MdPart(false, src.substring(last, m.range.first))
        out += MdPart(true, m.groupValues[2].trimEnd('\n'), m.groupValues[1])
        last = m.range.last + 1
    }
    if (last < src.length) out += MdPart(false, src.substring(last))
    return out.filter { it.text.isNotBlank() || it.code }
}

@Composable
fun AiChatScreen(vm: AppViewModel, editor: EditorController, onOpenModels: () -> Unit, onOpenEditor: () -> Unit) {
    val client by vm.client.collectAsState()
    val project by vm.project.collectAsState()
    val tabs by vm.tabs.collectAsState()
    val activeTab by vm.activeTab.collectAsState()
    val chat = vm.aiChat
    val ui by chat.ui.collectAsState()
    var status by remember { mutableStateOf<AIStatus?>(null) }
    var attach by remember { mutableStateOf(false) }
    var showHistory by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboardManager.current
    val active = tabs.firstOrNull { it.id == activeTab }

    LaunchedEffect(client) {
        val c = client ?: return@LaunchedEffect
        chat.refreshConversations()
        while (true) {
            apiCall { c.api.aiStatus() }.onSuccess { status = it }
            delay(if (status?.status == "loading") 2000 else 10000)
        }
    }
    LaunchedEffect(ui.messages.size, ui.messages.lastOrNull()?.content?.length) {
        if (ui.messages.isNotEmpty()) listState.animateScrollToItem(ui.messages.size - 1)
    }

    // File diubah AI / dibatalkan -> muat ulang tab editor yang membuka file itu (kecuali ada ketikan belum disimpan).
    LaunchedEffect(Unit) {
        chat.changed.collect { ch ->
            val c = vm.client.value ?: return@collect
            for (path in ch.paths) {
                val tab = vm.tabs.value.firstOrNull { it.projectId == ch.projectId && it.path == path } ?: continue
                if (!editor.hasTab(tab.id)) continue
                if (editor.isDirty(tab.id)) { vm.toast("$path punya perubahan belum disimpan — tidak dimuat ulang"); continue }
                apiCall { c.api.read(ch.projectId, path) }.onSuccess { f ->
                    if (!f.binary && f.content != null) {
                        editor.setDoc(tab.id, f.content, true)
                        vm.updateTab(tab.id) { it.copy(sha256 = f.sha256, dirty = false) }
                    }
                }
            }
            vm.toast(if (ch.paths.size == 1) "${ch.paths[0]} diperbarui" else "${ch.paths.size} file diperbarui")
        }
    }

    fun insertToEditor(code: String) {
        if (active == null) { vm.toast("Buka file di editor dulu"); return }
        scope.launch { editor.insert(code) }
        onOpenEditor()
    }

    Column(Modifier.fillMaxSize()) {
        // status model
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            val st = status
            val (label, color) = when (st?.status) {
                "ready" -> "● ${st.model}" to OkGreen
                "loading" -> "◌ ${st.message.ifBlank { "memuat…" }}" to WarnAmber
                "error" -> "✕ ${st.message}" to ErrRed
                null -> "…" to Color.Gray
                else -> "○ Belum ada model — ketuk untuk memilih" to Color.Gray
            }
            AssistChip(onClick = onOpenModels, label = { Text(label, color = color, maxLines = 1) }, modifier = Modifier.weight(1f))
            IconButton(onClick = { chat.refreshConversations(); showHistory = true }) { Icon(Icons.Default.History, "Riwayat") }
            IconButton(enabled = !ui.busy, onClick = { chat.newConversation() }) { Icon(Icons.Default.Add, "Percakapan baru") }
        }
        Text(ui.title, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(horizontal = 12.dp), maxLines = 1)
        HorizontalDivider()
        LazyColumn(state = listState, modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 8.dp),
                   verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (ui.messages.isEmpty()) item {
                Text(
                    "Tanya apa saja tentang kode. Centang \"Sertakan file editor\" agar AI membaca file yang sedang dibuka. " +
                        "Bila proyek terbuka, AI bisa langsung mengubah file: perubahan muncul sebagai kartu dengan diff " +
                        "(Terapkan / Tolak / Batalkan), atau diterapkan otomatis bila sakelar di bawah aktif.",
                    Modifier.padding(16.dp), style = MaterialTheme.typography.bodyMedium,
                )
            }
            itemsIndexed(ui.messages) { _, m ->
                MessageBubble(m, onCopy = { clipboard.setText(AnnotatedString(it)); vm.toast("Disalin") }, onInsert = ::insertToEditor)
                m.edits.forEach { e ->
                    EditCard(e, busy = e.id in ui.pending,
                             onApply = { chat.decide(e, true) { vm.toast(it) } },
                             onReject = { chat.decide(e, false) { vm.toast(it) } },
                             onRevert = { chat.revert(e) { vm.toast(it) } })
                }
            }
        }
        // input
        Column(Modifier.fillMaxWidth().padding(6.dp)) {
            if (project != null) Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Terapkan editan AI otomatis ke ${project?.name}", style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                Switch(ui.autoApply, { chat.setAutoApply(it) })
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = attach && active != null, enabled = active != null, onCheckedChange = { attach = it })
                Text(if (active != null) "Sertakan file editor (${active.name})" else "Sertakan file editor (tidak ada file terbuka)",
                     style = MaterialTheme.typography.bodySmall)
            }
            Row(verticalAlignment = Alignment.Bottom) {
                OutlinedTextField(ui.draft, { chat.setDraft(it) }, placeholder = { Text("Tulis pesan…") },
                                  modifier = Modifier.weight(1f).heightIn(max = 160.dp))
                if (ui.busy) IconButton(onClick = { chat.stop() }) { Icon(Icons.Default.Stop, "Hentikan") }
                else IconButton(enabled = ui.draft.isNotBlank(), onClick = {
                    val t = active
                    scope.launch {
                        val text = if (attach && t != null) editor.getDoc(t.id) else null
                        chat.send(ui.draft, project?.id, text, if (text != null) t?.path else null)
                    }
                }) { Icon(Icons.AutoMirrored.Filled.Send, "Kirim") }
            }
        }
    }

    if (showHistory) AlertDialog(
        onDismissRequest = { showHistory = false },
        title = { Text("Riwayat percakapan") },
        text = {
            LazyColumn(Modifier.heightIn(max = 420.dp)) {
                if (ui.conversations.isEmpty()) item { Text("Belum ada percakapan") }
                itemsIndexed(ui.conversations) { _, c ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f).clickable { chat.open(c.id, project?.id); showHistory = false }.padding(vertical = 6.dp)) {
                            Text(c.title, maxLines = 1)
                            Text("${c.messages} pesan · ${c.model ?: "-"} · ${formatTime(c.updated_at)}", style = MaterialTheme.typography.labelSmall)
                        }
                        IconButton(onClick = { chat.delete(c.id) { vm.toast(it) } }) { Icon(Icons.Default.Delete, "Hapus") }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = { showHistory = false }) { Text("Tutup") } },
    )
}

@Composable
private fun ThinkingDots() {
    val t = rememberInfiniteTransition(label = "think")
    val a by t.animateFloat(0.3f, 1f, infiniteRepeatable(tween(600), RepeatMode.Reverse), label = "a")
    Text("Berpikir…", Modifier.alpha(a), fontStyle = FontStyle.Italic, style = MaterialTheme.typography.bodyMedium)
}

@Composable
private fun MessageBubble(m: ChatMessage, onCopy: (String) -> Unit, onInsert: (String) -> Unit) {
    val mine = m.role == "user"
    var showReasoning by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxWidth(), contentAlignment = if (mine) Alignment.CenterEnd else Alignment.CenterStart) {
        Column(
            Modifier.widthIn(max = 360.dp)
                .background(
                    if (mine) MaterialTheme.colorScheme.primaryContainer
                    else if (m.error) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.surfaceVariant,
                    RoundedCornerShape(12.dp),
                )
                .padding(10.dp),
        ) {
            if (!mine && m.reasoning.isNotBlank()) {
                Text(if (showReasoning) "▾ Proses berpikir" else "▸ Proses berpikir", style = MaterialTheme.typography.labelSmall,
                     modifier = Modifier.clickable { showReasoning = !showReasoning })
                if (showReasoning) Text(m.reasoning, style = MaterialTheme.typography.bodySmall, fontStyle = FontStyle.Italic)
            }
            if (m.streaming && m.content.isEmpty()) ThinkingDots()
            SelectionContainer {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    splitMarkdown(m.content).forEach { part ->
                        if (part.code) {
                            Column(Modifier.fillMaxWidth().background(Color(0xFF1E1E1E), RoundedCornerShape(8.dp)).padding(8.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(part.lang.ifBlank { "kode" }, color = Color(0xFF9E9E9E), style = MaterialTheme.typography.labelSmall,
                                         modifier = Modifier.weight(1f))
                                    TextButton(onClick = { onCopy(part.text) }) { Text("Salin") }
                                    if (!m.streaming) TextButton(onClick = { onInsert(part.text) }) { Text("Ke editor") }
                                }
                                Text(part.text, style = Mono, color = Color(0xFFE0E0E0),
                                     modifier = Modifier.horizontalScroll(rememberScrollState()))
                            }
                        } else Text(part.text.trim('\n'), style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
            if (!mine && m.model.isNotBlank() && !m.streaming) Text(m.model, style = MaterialTheme.typography.labelSmall, color = Color.Gray)
        }
    }
}

/** Kartu perubahan file usulan AI: diff + aksi sesuai status. */
@Composable
private fun EditCard(e: AIProposalItem, busy: Boolean, onApply: () -> Unit, onReject: () -> Unit, onRevert: () -> Unit) {
    var showDiff by remember(e.id) { mutableStateOf(e.status == "pending") }
    val (label, color) = when (e.status) {
        "pending" -> "menunggu" to WarnAmber
        "approved" -> "diterapkan" to OkGreen
        "rejected" -> "ditolak" to Color.Gray
        "reverted" -> "dibatalkan" to Color.Gray
        else -> "gagal" to ErrRed
    }
    Column(
        Modifier.fillMaxWidth().padding(start = 12.dp)
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f), RoundedCornerShape(10.dp))
            .padding(8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f).clickable(enabled = !e.diff.isNullOrBlank()) { showDiff = !showDiff }) {
                Text((if (e.new_file) "✚ " else "✎ ") + e.path, style = MaterialTheme.typography.labelLarge, maxLines = 2)
                if (e.status != "failed") Text("+${e.additions}  −${e.deletions}" + if (e.new_file) "  · file baru" else "",
                                                 style = MaterialTheme.typography.labelSmall)
            }
            Text(label, color = color, style = MaterialTheme.typography.labelMedium)
        }
        if (!e.error.isNullOrBlank()) Text(e.error, color = ErrRed, style = MaterialTheme.typography.bodySmall)
        if (showDiff && !e.diff.isNullOrBlank()) DiffView(e.diff)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            when (e.status) {
                "pending" -> {
                    androidx.compose.material3.Button(onClick = onApply, enabled = !busy) { Text("Terapkan") }
                    OutlinedButton(onClick = onReject, enabled = !busy) { Text("Tolak") }
                }
                "approved" -> OutlinedButton(onClick = onRevert, enabled = !busy) { Text("Batalkan perubahan") }
            }
            if (!e.diff.isNullOrBlank()) TextButton(onClick = { showDiff = !showDiff }) { Text(if (showDiff) "Sembunyikan diff" else "Lihat diff") }
        }
    }
}

@Composable
private fun DiffView(diff: String) {
    Column(
        Modifier.fillMaxWidth().heightIn(max = 320.dp).background(Color(0xFF1E1E1E), RoundedCornerShape(6.dp))
            .verticalScroll(rememberScrollState()).horizontalScroll(rememberScrollState()).padding(6.dp),
    ) {
        diff.lineSequence().filterNot { it.startsWith("---") || it.startsWith("+++") }.forEach { line ->
            val c = when {
                line.startsWith("+") -> Color(0xFF81C784)
                line.startsWith("-") -> Color(0xFFEF9A9A)
                line.startsWith("@@") -> Color(0xFF64B5F6)
                else -> Color(0xFFBDBDBD)
            }
            Text(line.ifEmpty { " " }, style = Mono, color = c, softWrap = false)
        }
    }
}
