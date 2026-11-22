package id.codingserver.android.ui.editor

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.NoteAdd
import androidx.compose.material.icons.automirrored.filled.Redo
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Save
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import id.codingserver.android.data.api.ApiException
import id.codingserver.android.data.api.FileEntry
import id.codingserver.android.data.api.FileCreate
import id.codingserver.android.data.api.FileWrite
import id.codingserver.android.data.api.HistoryEntry
import id.codingserver.android.data.api.RestoreRequest
import id.codingserver.android.data.api.apiCall
import id.codingserver.android.ui.AppViewModel
import id.codingserver.android.ui.EditorTab
import id.codingserver.android.ui.common.InputDialog
import id.codingserver.android.ui.common.formatTime
import kotlinx.coroutines.launch

/** Code editor: tab, simpan, simpan sebagai, jalankan, build, cari/ganti, undo/redo, simbol, riwayat. */
@Composable
fun EditorScreen(vm: AppViewModel, editor: EditorController, onRunStarted: () -> Unit) {
    val client by vm.client.collectAsState()
    val tabs by vm.tabs.collectAsState()
    val activeId by vm.activeTab.collectAsState()
    val prefs by vm.editorPrefs.collectAsState()
    val cursor by editor.cursorFlow.collectAsState()
    val editorDiagnostic by editor.diagnostic.collectAsState()
    val scope = rememberCoroutineScope()
    var menu by remember { mutableStateOf(false) }
    var conflict by remember { mutableStateOf<EditorTab?>(null) }
    var saveAs by remember { mutableStateOf(false) }
    var gotoLine by remember { mutableStateOf(false) }
    var symbols by remember { mutableStateOf<List<Symbol>?>(null) }
    var history by remember { mutableStateOf<List<HistoryEntry>?>(null) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var newFile by remember { mutableStateOf(false) }
    var colorDialog by remember { mutableStateOf(false) }
    var textColorInput by remember(prefs) { mutableStateOf(prefs.textColor) }
    var backgroundColorInput by remember(prefs) { mutableStateOf(prefs.backgroundColor) }
    var colorError by remember { mutableStateOf<String?>(null) }
    val project by vm.project.collectAsState()
    val active = tabs.firstOrNull { it.id == activeId }

    suspend fun save(tab: EditorTab, force: Boolean = false): Boolean {
        val c = client ?: return false
        val content = editor.getDoc(tab.id) ?: return false
        val res = apiCall { c.api.write(FileWrite(tab.projectId, tab.path, content, if (force) null else tab.sha256)) }
        res.onSuccess { w ->
            vm.updateTab(tab.id) { it.copy(sha256 = w.sha256, dirty = false) }
            editor.markSaved(tab.id)
            vm.toast("Tersimpan: ${tab.name}")
        }.onFailure {
            val e = it as ApiException
            if (e.code == "write_conflict") conflict = tab else vm.toast(e.message)
        }
        return res.isSuccess
    }

    suspend fun runActive(build: Boolean) {
        val tab = active ?: return
        if (tab.dirty && !save(tab)) return
        editor.clearDiagnostics()
        vm.execute(FileEntry(tab.name, tab.path, "file"), build, projectId = tab.projectId)
            .onSuccess { onRunStarted() }
            .onFailure { vm.toast(it.message ?: "Gagal menjalankan") }
    }

    // Muat isi file ke editor saat tab aktif berubah.
    LaunchedEffect(activeId, client) {
        val tab = active ?: return@LaunchedEffect
        val c = client ?: return@LaunchedEffect
        loadError = null
        if (!editor.hasTab(tab.id)) {
            loadError = "Memuat file: " + tab.path
            apiCall { c.api.read(tab.projectId, tab.path) }
                .onSuccess { f ->
                    if (activeId != tab.id) return@onSuccess
                    if (f.binary || f.content == null) {
                        loadError = "File tidak dapat ditampilkan sebagai teks: " + tab.path
                    } else {
                        android.util.Log.d("CodingServerEditor", "File diterima: " + tab.path + ", " + f.content.length + " karakter")
                        editor.openTab(tab.id, f.content, f.name)
                        vm.updateTab(tab.id) { it.copy(sha256 = f.sha256, language = f.language, dirty = false) }
                        loadError = null
                    }
                }
                .onFailure {
                    if (activeId == tab.id) {
                        loadError = "Gagal membaca " + tab.path + ": " + (it.message ?: "kesalahan tidak diketahui")
                        android.util.Log.e("CodingServerEditor", loadError, it)
                    }
                }
        } else editor.switchTab(tab.id)
    }
    LaunchedEffect(prefs) { editor.applyPrefs(prefs.darkTheme, prefs.fontSize, prefs.wordWrap, prefs.tabSize, prefs.textColor, prefs.backgroundColor) }
    LaunchedEffect(Unit) {
        editor.eventsFlow.collect { ev ->
            when (ev) {
                is EditorEvent.Changed -> vm.updateTab(ev.tabId) { it.copy(dirty = ev.dirty) }
                is EditorEvent.SaveRequested -> vm.tabs.value.firstOrNull { it.id == ev.tabId }?.let { save(it) }
                is EditorEvent.RunRequested -> runActive(false)
            }
        }
    }

    Column(Modifier.fillMaxSize()) {
        // baris tab
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 4.dp)) {
            tabs.forEach { t ->
                FilterChip(
                    selected = t.id == activeId,
                    onClick = { vm.setActiveTab(t.id) },
                    label = { Text((if (t.dirty) "● " else "") + t.name) },
                    trailingIcon = {
                        Icon(Icons.Default.Close, "Tutup", Modifier.clickable {
                            scope.launch {
                                if (t.dirty) vm.toast("${t.name} belum disimpan — perubahan dibuang")
                                editor.closeTab(t.id); vm.closeTab(t.id)
                            }
                        })
                    },
                    modifier = Modifier.padding(end = 4.dp),
                )
            }
        }
        // toolbar
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            IconButton(enabled = project != null, onClick = { newFile = true }) { Icon(Icons.AutoMirrored.Filled.NoteAdd, "File baru") }
            IconButton(enabled = active != null, onClick = { scope.launch { active?.let { save(it) } } }) { Icon(Icons.Default.Save, "Simpan") }
            IconButton(enabled = active != null, onClick = { scope.launch { runActive(false) } }) { Icon(Icons.Default.PlayArrow, "Jalankan") }
            IconButton(enabled = active != null, onClick = { scope.launch { runActive(true) } }) { Icon(Icons.Default.Build, "Build") }
            IconButton(enabled = active != null, onClick = { scope.launch { editor.undo() } }) { Icon(Icons.AutoMirrored.Filled.Undo, "Undo") }
            IconButton(enabled = active != null, onClick = { scope.launch { editor.redo() } }) { Icon(Icons.AutoMirrored.Filled.Redo, "Redo") }
            IconButton(enabled = active != null, onClick = { scope.launch { editor.openSearch() } }) { Icon(Icons.Default.Search, "Cari & ganti") }
            Text("${cursor.first}:${cursor.second}", style = MaterialTheme.typography.labelSmall, modifier = Modifier.weight(1f))
            Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Default.MoreVert, "Lainnya") }
                DropdownMenu(menu, { menu = false }) {
                    DropdownMenuItem({ Text("Simpan sebagai…") }, enabled = active != null, onClick = { menu = false; saveAs = true })
                    DropdownMenuItem({ Text("Ke baris…") }, enabled = active != null, onClick = { menu = false; gotoLine = true })
                    DropdownMenuItem({ Text("Simbol dokumen") }, enabled = active != null, onClick = {
                        menu = false; scope.launch { symbols = editor.symbols() }
                    })
                    DropdownMenuItem({ Text("Ke definisi (kata di kursor)") }, enabled = active != null, onClick = {
                        menu = false; scope.launch { if (!editor.gotoDefinition()) vm.toast("Definisi tidak ditemukan di file ini") }
                    })
                    DropdownMenuItem({ Text("Lipat semua / buka semua") }, onClick = {
                        menu = false; scope.launch { editor.foldAll(); editor.unfoldAll() }
                    })
                    DropdownMenuItem({ Text(if (prefs.wordWrap) "Matikan word wrap" else "Aktifkan word wrap") },
                        onClick = { menu = false; vm.setEditorPrefs(prefs.copy(wordWrap = !prefs.wordWrap)) })
                    DropdownMenuItem({ Text("Font lebih besar (${prefs.fontSize + 1})") },
                        onClick = { vm.setEditorPrefs(prefs.copy(fontSize = (prefs.fontSize + 1).coerceAtMost(32))) })
                    DropdownMenuItem({ Text("Font lebih kecil (${prefs.fontSize - 1})") },
                        onClick = { vm.setEditorPrefs(prefs.copy(fontSize = (prefs.fontSize - 1).coerceAtLeast(9))) })
                    DropdownMenuItem({ Text("Pengaturan warna editor") }, onClick = { menu = false; textColorInput = prefs.textColor; backgroundColorInput = prefs.backgroundColor; colorError = null; colorDialog = true })
                    DropdownMenuItem({ Text(if (prefs.darkTheme) "Tema terang" else "Tema gelap") },
                        onClick = { menu = false; vm.setEditorPrefs(prefs.copy(darkTheme = !prefs.darkTheme)) })
                    DropdownMenuItem({ Text("Riwayat versi file") }, enabled = active != null, onClick = {
                        menu = false
                        val c = client; val t = active
                        if (c != null && t != null) scope.launch {
                            apiCall { c.api.history(t.projectId, t.path) }.onSuccess { history = it.history }.onFailure { vm.toast(it.message ?: "") }
                        }
                    })
                    DropdownMenuItem({ Text("Muat ulang dari server") }, enabled = active != null, onClick = {
                        menu = false
                        val c = client; val t = active
                        if (c != null && t != null) scope.launch {
                            apiCall { c.api.read(t.projectId, t.path) }.onSuccess { f ->
                                editor.setDoc(t.id, f.content ?: "", true)
                                vm.updateTab(t.id) { it.copy(sha256 = f.sha256, dirty = false) }
                            }
                        }
                    })
                }
            }
        }
        loadError?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(8.dp)) }
        Text(editorDiagnostic, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp))
        if (tabs.isEmpty()) {
            Text(
                if (project == null) "Belum ada proyek terbuka. Pilih proyek di menu Proyek dulu."
                else "Belum ada file terbuka. Tekan ikon + (File baru) atau buka file dari Project Explorer.",
                Modifier.padding(12.dp), style = MaterialTheme.typography.bodyMedium,
            )
        }
        Box(Modifier.fillMaxSize()) {
            AndroidView(factory = { editor.detach(); editor.webView }, modifier = Modifier.fillMaxSize())
        }
    }

    if (colorDialog) {
        AlertDialog(
            onDismissRequest = { colorDialog = false },
            title = { Text("Warna editor") },
            text = { Column {
                Text("Kosong = warna otomatis. Format HEX: #FFFFFF")
                OutlinedTextField(value = textColorInput, onValueChange = { textColorInput = it.trim(); colorError = null }, label = { Text("Warna teks") }, placeholder = { Text("#FFFFFF") }, singleLine = true)
                OutlinedTextField(value = backgroundColorInput, onValueChange = { backgroundColorInput = it.trim(); colorError = null }, label = { Text("Warna latar") }, placeholder = { Text("#282C34") }, singleLine = true)
                colorError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            } },
            confirmButton = { TextButton(onClick = {
                val hex = Regex("^#([0-9a-fA-F]{6})$")
                if ((textColorInput.isNotBlank() && !hex.matches(textColorInput)) || (backgroundColorInput.isNotBlank() && !hex.matches(backgroundColorInput))) colorError = "HEX tidak valid. Contoh: #AABBCC"
                else { vm.setEditorPrefs(prefs.copy(textColor = textColorInput, backgroundColor = backgroundColorInput)); colorDialog = false }
            }) { Text("Terapkan") } },
            dismissButton = { TextButton(onClick = { textColorInput = ""; backgroundColorInput = ""; colorError = null; vm.setEditorPrefs(prefs.copy(textColor = "", backgroundColor = "")); colorDialog = false }) { Text("Reset") } },
        )
    }

    conflict?.let { t ->
        AlertDialog(
            onDismissRequest = { conflict = null },
            title = { Text("Konflik penyimpanan") },
            text = { Text("${t.name} sudah diubah di server sejak dibuka. Timpa dengan versi di HP, atau muat ulang dari server?") },
            confirmButton = { TextButton(onClick = { conflict = null; scope.launch { save(t, force = true) } }) { Text("Timpa") } },
            dismissButton = {
                TextButton(onClick = {
                    conflict = null
                    val c = client
                    if (c != null) scope.launch {
                        apiCall { c.api.read(t.projectId, t.path) }.onSuccess { f ->
                            editor.setDoc(t.id, f.content ?: "", true)
                            vm.updateTab(t.id) { it.copy(sha256 = f.sha256, dirty = false) }
                        }
                    }
                }) { Text("Muat ulang") }
            },
        )
    }
    if (saveAs) active?.let { t ->
        InputDialog("Simpan sebagai", "Path baru di proyek", initial = t.path, confirmText = "Simpan", onConfirm = { path ->
            val c = client
            if (c != null) scope.launch {
                val content = editor.getDoc(t.id) ?: return@launch
                apiCall { c.api.write(FileWrite(t.projectId, path, content)) }.onSuccess { w ->
                    val tab = EditorTab(t.projectId, w.path, w.sha256)
                    editor.openTab(tab.id, content, w.name)
                    editor.markSaved(tab.id)
                    vm.addOrFocusTab(tab)
                    vm.toast("Disimpan sebagai ${w.path}")
                }.onFailure { vm.toast(it.message ?: "Gagal") }
            }
        }, onDismiss = { saveAs = false })
    }
    if (newFile) project?.let { p ->
        InputDialog("File baru di ${p.name}", "Nama file (mis. main.py)", confirmText = "Buat", onConfirm = { path ->
            val c = client
            if (c != null) scope.launch {
                apiCall { c.api.create(FileCreate(p.id, path, "file")) }
                    .onSuccess { w -> vm.addOrFocusTab(EditorTab(p.id, w.path, null)) }
                    .onFailure { vm.toast(it.message ?: "Gagal membuat file") }
            }
        }, onDismiss = { newFile = false })
    }
    if (gotoLine) InputDialog("Ke baris", "Nomor baris", onConfirm = { n ->
        n.toIntOrNull()?.let { scope.launch { editor.gotoLine(it) } }
    }, onDismiss = { gotoLine = false })
    symbols?.let { list ->
        AlertDialog(
            onDismissRequest = { symbols = null },
            title = { Text("Simbol dokumen") },
            text = {
                if (list.isEmpty()) Text("Tidak ada simbol terdeteksi")
                LazyColumn(Modifier.heightIn(max = 400.dp)) {
                    items(list) { s ->
                        Text("${s.line}: ${s.name}", Modifier.fillMaxWidth().clickable {
                            symbols = null; scope.launch { editor.gotoLine(s.line) }
                        }.padding(8.dp))
                    }
                }
            },
            confirmButton = { TextButton(onClick = { symbols = null }) { Text("Tutup") } },
        )
    }
    history?.let { list ->
        AlertDialog(
            onDismissRequest = { history = null },
            title = { Text("Riwayat versi") },
            text = {
                if (list.isEmpty()) Text("Belum ada versi tersimpan")
                LazyColumn(Modifier.heightIn(max = 400.dp)) {
                    items(list) { h ->
                        Column(Modifier.fillMaxWidth().clickable {
                            history = null
                            val c = client; val t = active
                            if (c != null && t != null) scope.launch {
                                apiCall { c.api.restore(RestoreRequest(t.projectId, h.id)) }.onSuccess {
                                    apiCall { c.api.read(t.projectId, t.path) }.onSuccess { f ->
                                        editor.setDoc(t.id, f.content ?: "", true)
                                        vm.updateTab(t.id) { it.copy(sha256 = f.sha256, dirty = false) }
                                        vm.toast("Versi #${h.id} dipulihkan")
                                    }
                                }.onFailure { vm.toast(it.message ?: "") }
                            }
                        }.padding(8.dp)) {
                            Text("#${h.id} · ${h.action} · ${formatTime(h.created_at)}")
                            Text("${h.actor_type} ${h.note}", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            },
            confirmButton = { TextButton(onClick = { history = null }) { Text("Tutup") } },
        )
    }
}
