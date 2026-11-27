package id.codingserver.android.ui.projects

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.InsertDriveFile
import androidx.compose.material.icons.filled.CreateNewFolder
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.FolderOpen
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.automirrored.filled.NoteAdd
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import id.codingserver.android.data.api.ApiClient
import id.codingserver.android.data.api.FavoriteRequest
import id.codingserver.android.data.api.FileCreate
import id.codingserver.android.data.api.FileEntry
import id.codingserver.android.data.api.FileMove
import id.codingserver.android.data.api.FileRename
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.common.ConfirmDialog
import id.codingserver.android.ui.common.ErrorCard
import id.codingserver.android.ui.common.InputDialog
import id.codingserver.android.ui.common.formatBytes
import kotlinx.coroutines.launch

private sealed interface Dlg {
    data class NewFile(val parent: String) : Dlg
    data class NewFolder(val parent: String) : Dlg
    data class Rename(val e: FileEntry) : Dlg
    data class Delete(val e: FileEntry) : Dlg
    data class Copy(val e: FileEntry) : Dlg
    data class Move(val e: FileEntry) : Dlg
}

private fun parentOf(path: String) = if (path.contains('/')) path.substringBeforeLast('/') else ""
private fun join(parent: String, name: String) = if (parent.isEmpty()) name else "$parent/$name"

/** Project Explorer: pohon folder, buka/buat/ganti nama/hapus/salin/pindah/cari/refresh. */
@OptIn(ExperimentalFoundationApi::class)
@Composable
fun ExplorerScreen(vm: AppViewModel, onOpenFile: (FileEntry) -> Unit, onRun: (FileEntry) -> Unit,
                   onInstall: (List<String>) -> Unit = {}) {
    val client by vm.client.collectAsState()
    val project by vm.project.collectAsState()
    val children = remember { mutableStateMapOf<String, List<FileEntry>>() }
    val expanded = remember { mutableStateListOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var dialog by remember { mutableStateOf<Dlg?>(null) }
    var installDlg by remember { mutableStateOf(false) }
    var searching by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }
    var searchContent by remember { mutableStateOf(false) }
    var results by remember { mutableStateOf<List<FileEntry>?>(null) }
    val scope = rememberCoroutineScope()
    val p = project
    val c = client

    if (p == null || c == null) {
        Text("Pilih proyek dulu di menu Proyek.", Modifier.padding(16.dp)); return
    }

    suspend fun load(path: String) {
        apiCall { c.api.tree(p.id, path, 1) }
            .onSuccess { children[path] = it.children ?: emptyList(); error = null }
            .onFailure { error = it.message }
    }

    fun refreshAll() = scope.launch { expanded.toList().forEach { load(it) } }

    LaunchedEffect(p.id) { children.clear(); expanded.clear(); expanded.add(""); load("") }

    // flatten pohon menjadi daftar baris (dengan kedalaman)
    val rows = remember(children.toMap(), expanded.toList()) {
        val out = mutableListOf<Pair<FileEntry, Int>>()
        fun walk(path: String, depth: Int) {
            children[path]?.forEach { e ->
                out += e to depth
                if (e.isFolder && e.path in expanded) walk(e.path, depth + 1)
            }
        }
        walk("", 0)
        out
    }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(p.name, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            IconButton(onClick = { dialog = Dlg.NewFile("") }) { Icon(Icons.AutoMirrored.Filled.NoteAdd, "File baru") }
            IconButton(onClick = { dialog = Dlg.NewFolder("") }) { Icon(Icons.Default.CreateNewFolder, "Folder baru") }
            IconButton(onClick = { searching = !searching; results = null }) { Icon(Icons.Default.Search, "Cari") }
            IconButton(onClick = { installDlg = true }) { Icon(Icons.Default.Download, "Instal dependensi") }
            IconButton(onClick = { refreshAll() }) { Icon(Icons.Default.Refresh, "Refresh") }
        }
        if (installDlg) InstallDepsDialog(c, p.id, onInstall = onInstall, onDismiss = { installDlg = false })
        if (searching) {
            Row(Modifier.padding(horizontal = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(query, { query = it }, singleLine = true, label = { Text(if (searchContent) "Cari isi file" else "Cari nama (*.py)") },
                    modifier = Modifier.weight(1f))
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Switch(searchContent, { searchContent = it })
                    Text("isi", style = MaterialTheme.typography.labelSmall)
                }
                IconButton(enabled = query.isNotBlank(), onClick = {
                    scope.launch {
                        apiCall { c.api.search(p.id, query, searchContent) }.onSuccess { results = it }.onFailure { error = it.message }
                    }
                }) { Icon(Icons.Default.Search, "Cari") }
            }
        }
        error?.let { ErrorCard(it) { refreshAll() } }
        HorizontalDivider()
        val res = results
        if (searching && res != null) {
            Text("${res.size} hasil", Modifier.padding(8.dp), style = MaterialTheme.typography.labelMedium)
            LazyColumn(Modifier.fillMaxSize()) {
                items(res) { e ->
                    Column(Modifier.fillMaxWidth().combinedClickable(onClick = { if (!e.isFolder) onOpenFile(e) }).padding(8.dp)) {
                        Text(e.path + (e.line?.let { ":$it" } ?: ""), style = MaterialTheme.typography.bodyMedium)
                        e.text?.let { Text(it, style = MaterialTheme.typography.bodySmall, maxLines = 1, overflow = TextOverflow.Ellipsis) }
                    }
                }
            }
        } else {
            LazyColumn(Modifier.fillMaxSize()) {
                items(rows, key = { it.first.path }) { (e, depth) ->
                    FileRow(e, depth, e.path in expanded,
                        onClick = {
                            if (e.isFolder) {
                                if (e.path in expanded) expanded.remove(e.path) else {
                                    expanded.add(e.path); scope.launch { load(e.path) }
                                }
                            } else onOpenFile(e)
                        },
                        onAction = { action ->
                            when (action) {
                                "open" -> if (!e.isFolder) onOpenFile(e)
                                "run" -> onRun(e)
                                "newfile" -> dialog = Dlg.NewFile(if (e.isFolder) e.path else parentOf(e.path))
                                "newfolder" -> dialog = Dlg.NewFolder(if (e.isFolder) e.path else parentOf(e.path))
                                "rename" -> dialog = Dlg.Rename(e)
                                "copy" -> dialog = Dlg.Copy(e)
                                "move" -> dialog = Dlg.Move(e)
                                "delete" -> dialog = Dlg.Delete(e)
                                "fav" -> scope.launch {
                                    apiCall { c.api.addFavorite(FavoriteRequest(p.id, e.path)) }.onSuccess { vm.toast("Ditambahkan ke favorit") }
                                }
                            }
                        })
                }
            }
        }
    }

    fun done(path: String) = scope.launch { load(path) }

    when (val d = dialog) {
        is Dlg.NewFile -> InputDialog("File baru di /${d.parent}", "Nama file (mis. main.py)", onConfirm = { name ->
            scope.launch {
                apiCall { c.api.create(FileCreate(p.id, join(d.parent, name), "file")) }
                    .onSuccess { done(d.parent); onOpenFile(FileEntry(it.name, it.path, "file")) }
                    .onFailure { vm.toast(it.message ?: "Gagal") }
            }
        }, onDismiss = { dialog = null })
        is Dlg.NewFolder -> InputDialog("Folder baru di /${d.parent}", "Nama folder", onConfirm = { name ->
            scope.launch {
                apiCall { c.api.create(FileCreate(p.id, join(d.parent, name), "folder")) }
                    .onSuccess { done(d.parent) }.onFailure { vm.toast(it.message ?: "Gagal") }
            }
        }, onDismiss = { dialog = null })
        is Dlg.Rename -> InputDialog("Ganti nama", "Nama baru", initial = d.e.name, onConfirm = { name ->
            scope.launch {
                apiCall { c.api.rename(FileRename(p.id, d.e.path, name)) }.onSuccess {
                    vm.renameTabs(p.id, d.e.path, it.path); done(parentOf(d.e.path))
                }.onFailure { vm.toast(it.message ?: "Gagal") }
            }
        }, onDismiss = { dialog = null })
        is Dlg.Copy -> InputDialog("Salin ke", "Path tujuan (folder atau nama baru)", initial = d.e.path + "_salinan", onConfirm = { dest ->
            scope.launch {
                apiCall { c.api.copy(FileMove(p.id, d.e.path, dest)) }.onSuccess { refreshAll() }.onFailure { vm.toast(it.message ?: "Gagal") }
            }
        }, onDismiss = { dialog = null })
        is Dlg.Move -> InputDialog("Pindahkan ke", "Path tujuan (folder atau nama baru)", initial = d.e.path, onConfirm = { dest ->
            scope.launch {
                apiCall { c.api.move(FileMove(p.id, d.e.path, dest)) }.onSuccess {
                    vm.renameTabs(p.id, d.e.path, it.path); refreshAll()
                }.onFailure { vm.toast(it.message ?: "Gagal") }
            }
        }, onDismiss = { dialog = null })
        is Dlg.Delete -> ConfirmDialog("Hapus", "Hapus ${if (d.e.isFolder) "folder" else "file"} \"${d.e.path}\"?" +
            if (d.e.isFolder) " Semua isinya ikut terhapus." else " (Versi lama tetap tersimpan di riwayat.)", "Hapus",
            onConfirm = {
                scope.launch {
                    apiCall { c.api.delete(p.id, d.e.path, recursive = d.e.isFolder) }
                        .onSuccess { vm.closeTab("${p.id}:${d.e.path}"); done(parentOf(d.e.path)) }
                        .onFailure { vm.toast(it.message ?: "Gagal") }
                }
            }, onDismiss = { dialog = null })
        null -> {}
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun FileRow(e: FileEntry, depth: Int, isExpanded: Boolean, onClick: () -> Unit, onAction: (String) -> Unit) {
    var menu by remember { mutableStateOf(false) }
    Row(
        Modifier.fillMaxWidth().combinedClickable(onClick = onClick, onLongClick = { menu = true })
            .padding(start = (8 + depth * 16).dp, end = 4.dp, top = 6.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            when { e.isFolder && isExpanded -> Icons.Default.FolderOpen; e.isFolder -> Icons.Default.Folder
                   else -> Icons.AutoMirrored.Filled.InsertDriveFile },
            null, Modifier.size(20.dp),
            tint = if (e.isFolder) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Column(Modifier.weight(1f).padding(start = 8.dp)) {
            Text(e.name, maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (!e.isFolder) Text("${formatBytes(e.size)} · ${e.language}", style = MaterialTheme.typography.labelSmall)
        }
        Box {
            IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, "Aksi") }
            DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                val items = buildList {
                    if (!e.isFolder) { add("open" to "Buka"); add("run" to "Jalankan") }
                    add("newfile" to "File baru"); add("newfolder" to "Folder baru")
                    add("rename" to "Ganti nama"); add("copy" to "Salin"); add("move" to "Pindahkan")
                    if (!e.isFolder) add("fav" to "Favorit")
                    add("delete" to "Hapus")
                }
                items.forEach { (k, label) -> DropdownMenuItem(text = { Text(label) }, onClick = { menu = false; onAction(k) }) }
            }
        }
    }
}

@Suppress("unused")
private fun ApiClient.describe() = baseUrl
